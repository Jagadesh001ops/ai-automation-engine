"""Tests for the ARQ ingest_document job — no live Redis, no live embeddings."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.jobs import ingest_document

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _make_doc(doc_id: int, filename: str = "doc.txt", content_type: str = "text/plain"):
    doc = MagicMock()
    doc.id = doc_id
    doc.filename = filename
    doc.content_type = content_type
    doc.status = "processing"
    doc.error_message = None
    return doc


def _fake_embed_batch(texts):
    return [[0.0] * 384 for _ in texts]


# ─── Success path ─────────────────────────────────────────────────────────────

_PATCHES = {
    "session": "engine.database.SessionLocal",
    "embed": "engine.embeddings.embed_batch",
    "store": "engine.database.store_chunks",
}


def test_ingest_document_sets_status_ready():
    doc = _make_doc(1)
    raw = b"Hello world. This is a test document for ingestion."

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = doc

    with (
        patch(_PATCHES["session"], return_value=db),
        patch(_PATCHES["embed"], side_effect=_fake_embed_batch),
        patch(_PATCHES["store"], return_value=2),
    ):
        result = _run(ingest_document({}, document_id=1, raw_bytes=raw))

    assert result["status"] == "ready"
    assert result["document_id"] == 1
    assert doc.status == "ready"
    db.commit.assert_called()


def test_ingest_document_returns_chunk_count():
    doc = _make_doc(1)
    raw = b"Sentence one. Sentence two. Sentence three."

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = doc

    with (
        patch(_PATCHES["session"], return_value=db),
        patch(_PATCHES["embed"], side_effect=_fake_embed_batch),
        patch(_PATCHES["store"], return_value=1),
    ):
        result = _run(ingest_document({}, document_id=1, raw_bytes=raw))

    assert "chunk_count" in result
    assert result["chunk_count"] >= 1


# ─── Failure paths ─────────────────────────────────────────────────────────────

def test_ingest_document_missing_doc_returns_failed():
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None

    with patch(_PATCHES["session"], return_value=db):
        result = _run(ingest_document({}, document_id=999, raw_bytes=b"x"))

    assert result["status"] == "failed"
    assert "not found" in result["error"]


def test_ingest_document_corrupt_pdf_sets_status_failed():
    doc = _make_doc(1, filename="bad.pdf", content_type="application/pdf")
    raw = b"%PDF-1.4 CORRUPTED GARBAGE"

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = doc

    with patch(_PATCHES["session"], return_value=db):
        result = _run(ingest_document({}, document_id=1, raw_bytes=raw))

    assert result["status"] == "failed"
    assert doc.status == "failed"
    assert doc.error_message
    db.commit.assert_called()


def test_ingest_document_unsupported_type_sets_status_failed():
    doc = _make_doc(1, filename="image.gif", content_type="image/gif")
    raw = b"GIF89a"

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = doc

    with patch(_PATCHES["session"], return_value=db):
        result = _run(ingest_document({}, document_id=1, raw_bytes=raw))

    assert result["status"] == "failed"
    assert doc.status == "failed"


def test_ingest_document_embedding_error_sets_status_failed():
    doc = _make_doc(1)
    raw = b"Valid text content that should chunk fine."

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = doc

    def boom(texts):
        raise RuntimeError("embedding service unavailable")

    with (
        patch(_PATCHES["session"], return_value=db),
        patch(_PATCHES["embed"], side_effect=boom),
    ):
        result = _run(ingest_document({}, document_id=1, raw_bytes=raw))

    assert result["status"] == "failed"
    assert doc.status == "failed"
    assert "embedding service unavailable" in doc.error_message


# ─── Dedup / idempotency ──────────────────────────────────────────────────────

def test_ingest_document_empty_text_produces_zero_chunks():
    doc = _make_doc(1)
    raw = b"   "  # whitespace-only text file

    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = doc

    with (
        patch(_PATCHES["session"], return_value=db),
        patch(_PATCHES["embed"], side_effect=_fake_embed_batch),
        patch(_PATCHES["store"], return_value=0) as mock_store,
    ):
        result = _run(ingest_document({}, document_id=1, raw_bytes=raw))

    assert result["status"] == "ready"
    assert result["chunk_count"] == 0
    mock_store.assert_not_called()
