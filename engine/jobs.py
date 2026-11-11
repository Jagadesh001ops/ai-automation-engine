"""ARQ background worker — ingestion pipeline.

Tasks:
  ping           — trivial health-check task (Day 2)
  ingest_document — full extract → chunk → embed → store pipeline (Day 5)

Run locally:
    python -m arq engine.jobs.WorkerSettings

Via docker-compose:
    docker-compose up worker
"""
from __future__ import annotations

import logging
import os

from arq.connections import RedisSettings

logger = logging.getLogger(__name__)


def _redis_settings() -> RedisSettings:
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    url = url.removeprefix("redis://")
    host, _, port_str = url.partition(":")
    return RedisSettings(host=host, port=int(port_str) if port_str else 6379)


async def ping(ctx: dict, message: str = "pong") -> str:
    """Trivial task — returns the message back. Confirms ARQ end-to-end."""
    return message


async def ingest_document(ctx: dict, document_id: int, raw_bytes: bytes) -> dict:
    """Extract text, chunk, embed, and store chunks for *document_id*.

    Updates Document.status to 'ready' on success or 'failed' (with
    error_message) on any unhandled error.  Always returns a summary dict
    so the ARQ result store has something useful.
    """
    from engine.chunking import chunk_text
    from engine.database import Document, SessionLocal, store_chunks
    from engine.embeddings import embed_batch
    from engine.ingestion import ExtractionError, IngestionError, ingest

    db = SessionLocal()
    try:
        doc = db.query(Document).filter_by(id=document_id).first()
        if doc is None:
            logger.error("ingest_document: document %d not found", document_id)
            return {"document_id": document_id, "status": "failed", "error": "document not found"}

        try:
            result = ingest(
                data=raw_bytes,
                filename=doc.filename,
                content_type=doc.content_type,
            )
        except (IngestionError, ExtractionError) as exc:
            doc.status = "failed"
            doc.error_message = str(exc)
            db.commit()
            logger.warning("ingest_document %d failed: %s", document_id, exc)
            return {"document_id": document_id, "status": "failed", "error": str(exc)}

        chunks = chunk_text(result.text)
        texts = [c.text for c in chunks]
        embeddings = embed_batch(texts) if texts else []
        new_chunks = store_chunks(db, document_id, chunks, embeddings) if chunks else 0

        doc.status = "ready"
        doc.page_count = result.page_count
        doc.char_count = result.char_count
        doc.error_message = None
        db.commit()

        logger.info(
            "ingest_document %d done: %d chunks (%d new)",
            document_id, len(chunks), new_chunks,
        )
        return {
            "document_id": document_id,
            "status": "ready",
            "chunk_count": len(chunks),
            "new_chunks": new_chunks,
        }

    except Exception as exc:
        db.rollback()
        try:
            doc = db.query(Document).filter_by(id=document_id).first()
            if doc:
                doc.status = "failed"
                doc.error_message = str(exc)
                db.commit()
        except Exception:
            pass
        logger.exception("ingest_document %d unexpected error", document_id)
        return {"document_id": document_id, "status": "failed", "error": str(exc)}
    finally:
        db.close()


class WorkerSettings:
    functions = [ping, ingest_document]
    redis_settings = _redis_settings()
