"""Persistent retrieval index for the APEX RAG server.

Design:
    * The chunk corpus is persisted to ``<index_dir>/chunks.jsonl`` (one JSON
      object per line) so it survives process restarts.
    * Metadata (last build time, source doc count) lives in
      ``<index_dir>/meta.json``.
    * The BM25 index is *rebuilt in memory* from the corpus on load -- we never
      pickle BM25 itself (rank_bm25 objects are not a stable on-disk format).
    * OPTIONAL semantic mode: when ``sentence-transformers`` is importable AND
      ``APEX_RAG_SEMANTIC=1``, we additionally compute embeddings and blend a
      cosine-similarity score with the BM25 score (hybrid retrieval). When the
      library is missing we degrade silently to pure BM25.

The class is intentionally self-contained so callers (the MCP server) can keep a
single lazy singleton and never rebuild on every request.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..common import get_logger
from . import ingest

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Tokenisation (shared by BM25 build + query)
# --------------------------------------------------------------------------- #


def _tokenize(text: str) -> list[str]:
    """Lowercase whitespace tokenisation -- simple, dependency-free, good enough
    for BM25 lexical matching over research prose."""
    return text.lower().split()


# --------------------------------------------------------------------------- #
# Optional semantic backend
# --------------------------------------------------------------------------- #


def _semantic_enabled() -> bool:
    """True only if the user opted in via env AND the library is importable."""
    if os.getenv("APEX_RAG_SEMANTIC", "") != "1":
        return False
    try:
        import sentence_transformers  # noqa: F401  (probe only)
    except Exception:
        logger.info("APEX_RAG_SEMANTIC=1 but sentence-transformers unavailable; "
                    "falling back to BM25-only.")
        return False
    return True


class RagIndex:
    """A persistent BM25 (+ optional semantic) retrieval index over a doc tree."""

    CHUNKS_FILE = "chunks.jsonl"
    META_FILE = "meta.json"
    EMBED_FILE = "embeddings.npy"
    EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, index_dir: Path) -> None:
        self.index_dir = Path(index_dir)
        self._chunks: list[dict] = []
        self._bm25 = None  # rank_bm25.BM25Okapi | None, rebuilt from corpus
        self._meta: dict[str, Any] = {}

        # Semantic state (only populated when enabled).
        self._semantic = _semantic_enabled()
        self._embeddings = None  # numpy.ndarray | None
        self._model = None       # SentenceTransformer | None

        self._load()

    # ------------------------------------------------------------------ #
    # Paths
    # ------------------------------------------------------------------ #

    @property
    def _chunks_path(self) -> Path:
        return self.index_dir / self.CHUNKS_FILE

    @property
    def _meta_path(self) -> Path:
        return self.index_dir / self.META_FILE

    @property
    def _embed_path(self) -> Path:
        return self.index_dir / self.EMBED_FILE

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        """Load the persisted corpus from disk (if any) and rebuild BM25."""
        if self._chunks_path.exists():
            chunks: list[dict] = []
            try:
                with self._chunks_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            chunks.append(json.loads(line))
                self._chunks = chunks
                logger.info("Loaded %d chunks from %s", len(chunks), self._chunks_path)
            except Exception as exc:
                logger.warning("Failed to load chunk corpus (%s); starting empty.", exc)
                self._chunks = []

        if self._meta_path.exists():
            try:
                self._meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to load meta.json (%s).", exc)
                self._meta = {}

        self._rebuild_bm25()
        if self._semantic:
            self._load_or_clear_embeddings()

    def _persist(self) -> None:
        """Write the corpus + metadata (+ embeddings if semantic) to disk."""
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Atomic-ish write: write to a temp file then replace.
        tmp = self._chunks_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for chunk in self._chunks:
                fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
        tmp.replace(self._chunks_path)

        self._meta_path.write_text(
            json.dumps(self._meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        if self._semantic and self._embeddings is not None:
            try:
                import numpy as np

                np.save(self._embed_path, self._embeddings)
            except Exception as exc:
                logger.warning("Failed to persist embeddings (%s).", exc)

    # ------------------------------------------------------------------ #
    # BM25
    # ------------------------------------------------------------------ #

    def _rebuild_bm25(self) -> None:
        """(Re)build the in-memory BM25 index from the current corpus."""
        if not self._chunks:
            self._bm25 = None
            return
        try:
            from rank_bm25 import BM25Okapi

            corpus_tokens = [_tokenize(c["text"]) for c in self._chunks]
            self._bm25 = BM25Okapi(corpus_tokens)
        except Exception as exc:
            logger.error("Failed to build BM25 index: %s", exc)
            self._bm25 = None

    # ------------------------------------------------------------------ #
    # Semantic embeddings (optional)
    # ------------------------------------------------------------------ #

    def _get_model(self):
        """Lazily instantiate the sentence-transformers model (heavy)."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.EMBED_MODEL)
        return self._model

    def _load_or_clear_embeddings(self) -> None:
        """Load cached embeddings if their row count matches the corpus."""
        if not self._chunks or not self._embed_path.exists():
            self._embeddings = None
            return
        try:
            import numpy as np

            arr = np.load(self._embed_path)
            if arr.shape[0] == len(self._chunks):
                self._embeddings = arr
            else:
                logger.info("Cached embeddings stale; will recompute on next build.")
                self._embeddings = None
        except Exception as exc:
            logger.warning("Failed to load embeddings (%s).", exc)
            self._embeddings = None

    def _compute_embeddings(self) -> None:
        """Encode the whole corpus into a normalised embedding matrix."""
        if not self._semantic or not self._chunks:
            self._embeddings = None
            return
        try:
            import numpy as np

            model = self._get_model()
            texts = [c["text"] for c in self._chunks]
            emb = model.encode(
                texts, convert_to_numpy=True, show_progress_bar=False
            ).astype("float32")
            # L2-normalise so a dot product is cosine similarity.
            norms = np.linalg.norm(emb, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._embeddings = emb / norms
        except Exception as exc:
            logger.warning("Embedding computation failed (%s); BM25-only.", exc)
            self._embeddings = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def build(self, root: Path, extensions: list[str]) -> dict:
        """Full re-ingest: walk ``root``, chunk everything, persist, rebuild.

        Returns the resulting :meth:`stats` dict.
        """
        logger.info("Building RAG index from %s (extensions=%s)", root, extensions)
        chunks: list[dict] = []
        sources: set[str] = set()

        for path, text in ingest.iter_documents(root, extensions):
            try:
                rel = str(path.relative_to(root.resolve()))
            except ValueError:
                rel = str(path)
            sources.add(rel)
            chunks.extend(ingest.chunk_text(text, source=rel))

        self._chunks = chunks
        self._meta = {
            "n_docs": len(sources),
            "n_chunks": len(chunks),
            "last_built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "root": str(root),
            "semantic": self._semantic,
        }

        self._rebuild_bm25()
        if self._semantic:
            self._compute_embeddings()

        self._persist()
        logger.info("Index built: %d docs, %d chunks", len(sources), len(chunks))
        return self.stats()

    def add_or_update(self, root: Path, extensions: list[str]) -> dict:
        """Convenience alias for a full rebuild.

        The corpus is content-addressed and cheap to rebuild for a research-docs
        folder, so we re-ingest rather than maintaining a fragile incremental
        delta. Kept as a distinct method for API clarity / future optimisation.
        """
        return self.build(root, extensions)

    def is_empty(self) -> bool:
        """True when no chunks are indexed yet (used for lazy auto-build)."""
        return not self._chunks

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Return the top-``k`` chunks for ``query``, each with a ``score`` key.

        Uses BM25 lexical scoring, optionally blended with cosine similarity over
        sentence-transformer embeddings (hybrid) when semantic mode is active.
        """
        if not self._chunks or self._bm25 is None:
            return []
        k = max(1, min(k, len(self._chunks)))

        import numpy as np

        query_tokens = _tokenize(query)
        bm25_scores = np.asarray(self._bm25.get_scores(query_tokens), dtype="float32")
        scores = self._normalise(bm25_scores)

        # Blend in semantic similarity when available.
        if self._semantic and self._embeddings is not None:
            try:
                model = self._get_model()
                q_emb = model.encode(
                    [query], convert_to_numpy=True, show_progress_bar=False
                ).astype("float32")[0]
                q_norm = np.linalg.norm(q_emb) or 1.0
                q_emb = q_emb / q_norm
                cosine = self._embeddings @ q_emb  # already row-normalised
                scores = 0.5 * scores + 0.5 * self._normalise(cosine)
            except Exception as exc:
                logger.warning("Semantic scoring failed (%s); using BM25 only.", exc)

        top_idx = np.argsort(scores)[::-1][:k]
        results: list[dict] = []
        for i in top_idx:
            chunk = dict(self._chunks[int(i)])
            chunk["score"] = round(float(scores[int(i)]), 6)
            results.append(chunk)
        return results

    @staticmethod
    def _normalise(arr) -> Any:
        """Min-max scale an array to [0, 1] so heterogeneous scores can blend."""
        import numpy as np

        arr = np.asarray(arr, dtype="float32")
        if arr.size == 0:
            return arr
        lo, hi = float(arr.min()), float(arr.max())
        if hi - lo < 1e-12:
            return np.zeros_like(arr)
        return (arr - lo) / (hi - lo)

    def stats(self) -> dict:
        """Return summary statistics about the current index."""
        return {
            "n_docs": self._meta.get("n_docs", 0),
            "n_chunks": self._meta.get("n_chunks", len(self._chunks)),
            "last_built": self._meta.get("last_built", "never"),
            "index_dir": str(self.index_dir),
            "semantic": self._semantic,
        }
