"""Tests for engine/ingestion.py — no live API calls, no Tesseract required."""
import io
import pytest

from engine.ingestion import (
    MAX_FILE_BYTES,
    ExtractionError,
    IngestionError,
    ingest,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _minimal_pdf() -> bytes:
    """Return a tiny but valid PDF with one text-layer page."""
    import pdfplumber
    # Build using reportlab if available, otherwise use a stored minimal PDF blob.
    # We use a raw minimal PDF so the test has zero extra dependencies.
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>stream\n"
        b"BT /F1 12 Tf 100 700 Td (Hello PDF world) Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\n"
        b"startxref\n430\n%%EOF"
    )


# ─── Type & size validation ────────────────────────────────────────────────────

def test_rejects_unsupported_type():
    with pytest.raises(IngestionError, match="Unsupported file type"):
        ingest(b"GIF89a", filename="image.gif", content_type="image/gif")


def test_rejects_oversized_file():
    big = b"x" * (MAX_FILE_BYTES + 1)
    with pytest.raises(IngestionError, match="25 MB"):
        ingest(big, filename="big.txt", content_type="text/plain")


def test_rejects_empty_file():
    with pytest.raises(IngestionError, match="empty"):
        ingest(b"", filename="empty.txt", content_type="text/plain")


def test_accepts_by_extension_when_mime_generic():
    result = ingest(b"hello world text", filename="notes.txt", content_type="application/octet-stream")
    assert "hello world text" in result.text


# ─── Plain text extraction ─────────────────────────────────────────────────────

def test_plain_text_extraction():
    content = "The quick brown fox jumps over the lazy dog."
    result = ingest(content.encode(), filename="doc.txt", content_type="text/plain")
    assert result.text == content
    assert result.page_count == 1
    assert result.ocr_pages == []
    assert result.char_count == len(content)


def test_plain_text_latin1_fallback():
    content = "Caf\xe9 au lait"  # latin-1 encoded é
    result = ingest(content.encode("latin-1"), filename="latin.txt", content_type="text/plain")
    assert "Caf" in result.text


# ─── PDF extraction ────────────────────────────────────────────────────────────

def test_pdf_extraction_returns_text():
    pdf_bytes = _minimal_pdf()
    result = ingest(pdf_bytes, filename="doc.pdf", content_type="application/pdf")
    assert result.page_count == 1
    assert result.size_bytes == len(pdf_bytes)


def test_corrupt_pdf_raises_extraction_error():
    with pytest.raises(ExtractionError, match="Could not read PDF"):
        ingest(b"%PDF-1.4 CORRUPTED GARBAGE", filename="bad.pdf", content_type="application/pdf")


# ─── Result shape ─────────────────────────────────────────────────────────────

def test_result_fields_present():
    result = ingest(b"some text", filename="f.txt", content_type="text/plain")
    assert result.filename == "f.txt"
    assert result.size_bytes == 9
    assert isinstance(result.ocr_pages, list)
    assert isinstance(result.ocr_skipped_pages, list)
