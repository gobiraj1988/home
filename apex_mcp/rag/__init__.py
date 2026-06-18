"""APEX RAG subpackage: document ingestion, chunking, and a persistent
lexical (BM25) + optional semantic retrieval index.

Public surface:
    from apex_mcp.rag.ingest import load_text, iter_documents, chunk_text
    from apex_mcp.rag.index import RagIndex
"""

from __future__ import annotations

__all__ = ["ingest", "index"]
