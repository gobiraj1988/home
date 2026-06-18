"""APEX RAG MCP server.

A FastMCP (stdio) server that lets Claude browse, read, and semantically search
the APEX research-docs folder, plus inspect CSV datasets. All filesystem access
is sandboxed to ``settings.data_dir`` via ``safe_resolve``.

Run:
    python -m apex_mcp.rag_server
or via the console entry point ``main()``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .common import (
    PathOutsideSandboxError,
    get_logger,
    human_bytes,
    markdown_table,
    safe_resolve,
)
from .config import settings
from .rag import ingest
from .rag.index import RagIndex

logger = get_logger(__name__)

mcp = FastMCP("apex-rag")


# --------------------------------------------------------------------------- #
# Lazy index singleton
# --------------------------------------------------------------------------- #

_INDEX: RagIndex | None = None


def _get_index() -> RagIndex:
    """Return the process-wide :class:`RagIndex`, constructing it once.

    Construction loads any persisted corpus from disk; it does NOT trigger a full
    ingest, so importing/starting the server stays fast. The first
    ``search_documents`` call auto-builds if the index is empty.
    """
    global _INDEX
    if _INDEX is None:
        _INDEX = RagIndex(settings.resolved_index_dir)
    return _INDEX


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
def list_documents(subdir: str = "") -> str:
    """List research documents stored under the APEX data directory.

    Args:
        subdir: Optional sub-folder (relative to the data directory) to list.
                Leave empty to list the root research folder.

    Returns:
        A markdown table of files with name, relative path, size, and last
        modified timestamp. The persistent index folder and hidden files are
        omitted.
    """
    try:
        base = safe_resolve(subdir) if subdir else settings.data_dir.resolve()
    except PathOutsideSandboxError as exc:
        return f"Error: {exc}"

    if not base.exists():
        return f"Error: directory does not exist: {subdir or base}"
    if not base.is_dir():
        return f"Error: not a directory: {subdir or base}"

    wanted = {
        e.lower() if e.startswith(".") else f".{e.lower()}"
        for e in settings.rag_extensions
    }
    root = settings.data_dir.resolve()
    rows: list[dict] = []

    try:
        for entry in sorted(base.rglob("*")):
            if not entry.is_file():
                continue
            # Skip the index dir and any hidden path component.
            parts = entry.relative_to(root).parts if root in entry.parents else entry.parts
            if any(p == ingest.INDEX_DIR_NAME or p.startswith(".") for p in parts):
                continue
            if entry.suffix.lower() not in wanted:
                continue
            try:
                st = entry.stat()
                rel = str(entry.relative_to(root))
            except (OSError, ValueError):
                continue
            rows.append(
                {
                    "name": entry.name,
                    "path": rel,
                    "size": human_bytes(st.st_size),
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                }
            )
    except OSError as exc:
        return f"Error listing documents: {exc}"

    if not rows:
        return f"_No documents found under '{subdir or '.'}'._"

    header = f"Found {len(rows)} document(s) under '{subdir or '.'}':\n\n"
    return header + markdown_table(rows, ["name", "path", "size", "modified"])


@mcp.tool()
def read_document(path: str) -> str:
    """Read the full text of a single research document.

    Supports .txt, .md, .pdf, .docx, and .csv (CSV is returned as a structured
    text summary). The path is resolved inside the sandboxed data directory.

    Args:
        path: Path to the document, relative to the data directory (or absolute
              within it).

    Returns:
        The extracted document text, or a clear error message.
    """
    try:
        resolved = safe_resolve(path)
    except PathOutsideSandboxError as exc:
        return f"Error: {exc}"

    if not resolved.exists():
        return f"Error: file does not exist: {path}"
    if not resolved.is_file():
        return f"Error: not a file: {path}"

    try:
        text = ingest.load_text(resolved)
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        logger.exception("Failed to read %s", resolved)
        return f"Error reading '{path}': {exc}"

    if not text.strip():
        return f"_Document '{path}' is empty or contained no extractable text._"
    return text


@mcp.tool()
def search_documents(query: str, k: int = 5) -> str:
    """Search the research-docs corpus and return the most relevant passages.

    Uses BM25 lexical retrieval (optionally blended with semantic embeddings when
    enabled). The index is built automatically on the first call if it is empty.

    Args:
        query: Natural-language search query.
        k:     Number of passages to return (default 5).

    Returns:
        Markdown listing the top passages with their source file, relevance
        score, and a text snippet.
    """
    if not query or not query.strip():
        return "Error: query must not be empty."

    index = _get_index()
    try:
        if index.is_empty():
            logger.info("Index empty; auto-building before first search.")
            index.build(settings.data_dir, settings.rag_extensions)

        results = index.search(query, k=k)
    except Exception as exc:
        logger.exception("Search failed")
        return f"Error during search: {exc}"

    if not results:
        return (
            f"_No results for '{query}'. The corpus may be empty -- "
            f"add documents under the data directory and run reindex._"
        )

    lines = [f"Top {len(results)} result(s) for **{query}**:\n"]
    for rank, r in enumerate(results, start=1):
        snippet = r["text"].strip().replace("\n", " ")
        if len(snippet) > 500:
            snippet = snippet[:500].rstrip() + "..."
        lines.append(
            f"**{rank}. {r['source']}** "
            f"(chunk {r['chunk_index']}, score {r['score']:.3f})\n\n"
            f"> {snippet}\n"
        )
    return "\n".join(lines)


@mcp.tool()
def reindex() -> str:
    """Force a full re-ingest of the research-docs folder and rebuild the index.

    Use this after adding, editing, or removing documents.

    Returns:
        A markdown summary of the rebuilt index statistics.
    """
    index = _get_index()
    try:
        stats = index.build(settings.data_dir, settings.rag_extensions)
    except Exception as exc:
        logger.exception("Reindex failed")
        return f"Error during reindex: {exc}"
    return "Index rebuilt successfully.\n\n" + _format_stats(stats)


@mcp.tool()
def index_status() -> str:
    """Report the current state of the RAG index.

    Returns:
        Markdown with document count, chunk count, last-built timestamp, the
        index directory, and whether semantic mode is active.
    """
    try:
        stats = _get_index().stats()
    except Exception as exc:
        logger.exception("Failed to read index status")
        return f"Error reading index status: {exc}"
    return _format_stats(stats)


@mcp.tool()
def query_csv(path: str, question: str = "", max_rows: int = 20) -> str:
    """Load a CSV dataset and return a structured overview for analysis.

    Returns the shape, column dtypes, the first ``max_rows`` rows as a markdown
    table, and ``describe()`` statistics for numeric columns. This gives Claude
    the structure and a sample needed to reason about the data.

    Args:
        path:     Path to the CSV file, relative to the data directory.
        question: Optional free-text note about what you want to learn (echoed
                  back for context; the full data overview is always returned).
        max_rows: Number of head rows to include in the preview (default 20).

    Returns:
        Markdown describing the dataset, or a clear error message.
    """
    try:
        resolved = safe_resolve(path)
    except PathOutsideSandboxError as exc:
        return f"Error: {exc}"

    if not resolved.exists():
        return f"Error: file does not exist: {path}"
    if resolved.suffix.lower() != ".csv":
        return f"Error: not a CSV file: {path}"

    try:
        import pandas as pd

        df = pd.read_csv(resolved)
    except Exception as exc:
        logger.exception("Failed to load CSV %s", resolved)
        return f"Error reading CSV '{path}': {exc}"

    max_rows = max(1, max_rows)
    parts: list[str] = [f"# CSV: {path}"]
    if question.strip():
        parts.append(f"_Question: {question.strip()}_")
    parts.append(f"\n**Shape:** {df.shape[0]} rows x {df.shape[1]} columns\n")

    # Columns + dtypes table.
    dtype_rows = [{"column": c, "dtype": str(t)} for c, t in df.dtypes.items()]
    parts.append("**Columns & dtypes:**\n")
    parts.append(markdown_table(dtype_rows, ["column", "dtype"]))

    # Head preview as a markdown table.
    head = df.head(max_rows)
    head_rows = head.to_dict(orient="records")
    cols = [str(c) for c in df.columns]
    parts.append(f"\n**Head ({len(head)} rows):**\n")
    parts.append(markdown_table(head_rows, cols))

    # Numeric describe().
    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        desc = numeric.describe().reset_index().rename(columns={"index": "stat"})
        desc_rows = desc.to_dict(orient="records")
        desc_cols = [str(c) for c in desc.columns]
        parts.append("\n**Numeric summary (describe):**\n")
        parts.append(markdown_table(desc_rows, desc_cols))
    else:
        parts.append("\n_No numeric columns to summarise._")

    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _format_stats(stats: dict) -> str:
    """Render an index-stats dict as a small markdown table."""
    rows = [
        {"metric": "documents", "value": stats.get("n_docs", 0)},
        {"metric": "chunks", "value": stats.get("n_chunks", 0)},
        {"metric": "last built", "value": stats.get("last_built", "never")},
        {"metric": "index dir", "value": stats.get("index_dir", "")},
        {"metric": "semantic mode", "value": stats.get("semantic", False)},
    ]
    return markdown_table(rows, ["metric", "value"])


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    """Run the APEX RAG MCP server over stdio."""
    logger.info("Starting APEX RAG MCP server (data_dir=%s)", settings.data_dir)
    mcp.run()


if __name__ == "__main__":
    main()
