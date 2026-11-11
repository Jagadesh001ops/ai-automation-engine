"""pgvector similarity search for retrieved-chunk retrieval (Day 8)."""
from __future__ import annotations

from typing import List, Optional

from .database import DocumentChunk, SessionLocal
from .embeddings import embed

try:
    from pgvector.sqlalchemy import Vector as _Vec  # noqa: F401
    _HAS_PGVECTOR = True
except ImportError:
    _HAS_PGVECTOR = False


def retrieve_chunks(
    query: str,
    document_id: Optional[int] = None,
    top_k: int = 5,
) -> List[dict]:
    """Return the top_k most relevant chunks for query.

    Returns list of {chunk_id, document_id, text, char_start, char_end, score}.
    score is cosine distance (lower = more similar), 0.0 in fallback mode.
    """
    import engine.retrieval_node as _self
    has_pgvec = getattr(_self, "_HAS_PGVECTOR", _HAS_PGVECTOR)

    query_vec = embed(query)
    db = SessionLocal()
    try:
        if has_pgvec:
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
