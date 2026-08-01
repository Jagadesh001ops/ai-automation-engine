"""pgvector similarity search for retrieved-chunk retrieval (Day 8).

retrieve_chunks() embeds the query with the same model used at ingest time
(all-MiniLM-L6-v2) then runs a cosine-distance search over DocumentChunk rows.
"""
from __future__ import annotations

from typing import List, Optional

from .database import DocumentChunk, SessionLocal
from .embeddings import embed


def retrieve_chunks(
    query: str,
    document_id: Optional[int] = None,
    top_k: int = 5,
) -> List[dict]:
    """Return the *top_k* most relevant chunks for *query*.

    Args:
        query:       Natural-language query to embed and search.
        document_id: If given, restrict search to chunks from this document.
        top_k:       Maximum number of chunks to return.

    Returns:
        List of dicts ordered by relevance (closest first):
        {chunk_id, document_id, text, char_start, char_end, score}
        where score is cosine distance (lower = more similar).
    """
    try:
        from pgvector.sqlalchemy import Vector
        _HAS_PGVECTOR = True
    except ImportError:
        _HAS_PGVECTOR = False

    query_vec = embed(query)

    db = SessionLocal()
    try:
        if _HAS_PGVECTOR:
            q = db.query(
                DocumentChunk,
                DocumentChunk.embedding.cosine_distance(query_vec).label("score"),
            )
            if document_id is not None:
                q = q.filter(DocumentChunk.document_id == document_id)
            q = q.filter(DocumentChunk.embedding.isnot(None))
            rows = q.order_by("score").limit(top_k).all()
            return [
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "score": float(score),
                }
                for chunk, score in rows
            ]
        else:
            # Fallback when pgvector not available: return most recent chunks
            q = db.query(DocumentChunk)
            if document_id is not None:
                q = q.filter(DocumentChunk.document_id == document_id)
            rows = q.order_by(DocumentChunk.id).limit(top_k).all()
            return [
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "score": 0.0,
                }
                for chunk in rows
            ]
    finally:
        db.close()
