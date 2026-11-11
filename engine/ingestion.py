"""Document ingestion: file validation, text extraction, OCR fallback.

Supported input types: PDF (.pdf) and plain text (.txt / text/plain).
Size cap: 25 MB.
OCR fallback: any PDF page whose extracted text is below OCR_MIN_CHARS
characters is re-processed with Tesseract if it is available; otherwise a
warning is recorded and the short text is kept as-is.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)

MAX_FILE_BYTES: int = 25 * 1024 * 1024  # 25 MB
OCR_MIN_CHARS: int = 100               # chars below which a page is considered image-only

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}
SUPPORTED_MIME_PREFIXES = ("application/pdf", "text/")


# ─── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    filename: str
    content_type: str
    size_bytes: int
    page_count: int
    char_count: int
    ocr_pages: List[int]      # 1-indexed page numbers that required OCR
    ocr_skipped_pages: List[int]  # pages that needed OCR but Tesseract unavailable
    text: str


# ─── Tesseract availability check ─────────────────────────────────────────────

def _tesseract_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


_TESSERACT_OK: bool | None = None  # cached after first check


def _ocr_page(pil_image) -> str:
    import pytesseract
    return pytesseract.image_to_string(pil_image)


# ─── Extraction helpers ────────────────────────────────────────────────────────

def _extract_pdf(data: bytes) -> tuple[str, int, list[int], list[int]]:
    """Return (full_text, page_count, ocr_pages, ocr_skipped_pages)."""
    global _TESSERACT_OK

    import pdfplumber

    if _TESSERACT_OK is None:
        _TESSERACT_OK = _tesseract_available()
        if not _TESSERACT_OK:
            logger.warning(
                "Tesseract not found — OCR fallback disabled. "
                "Install Tesseract to enable OCR for image-only pages."
            )

    pages_text: list[str] = []
    ocr_pages: list[int] = []
    ocr_skipped: list[int] = []

    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if len(text.strip()) < OCR_MIN_CHARS:
                    if _TESSERACT_OK:
                        try:
                            img = page.to_image(resolution=150).original
                            text = _ocr_page(img)
                            ocr_pages.append(i)
                        except Exception as exc:
                            logger.warning("OCR failed on page %d: %s", i, exc)
                            ocr_skipped.append(i)
                    else:
                        ocr_skipped.append(i)
                pages_text.append(text)
    except Exception as exc:
        raise ExtractionError(f"Could not read PDF: {exc}") from exc

    return "\n\n".join(pages_text), page_count, ocr_pages, ocr_skipped


def _extract_text_file(data: bytes) -> tuple[str, int, list[int], list[int]]:
    """Decode plain text, trying UTF-8 then latin-1 as fallback."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise ExtractionError(f"Could not decode text file: {exc}") from exc
    return text, 1, [], []


# ─── Public API ───────────────────────────────────────────────────────────────

class IngestionError(ValueError):
    """Raised for validation failures (bad type, oversized). Maps to 4xx."""

class ExtractionError(RuntimeError):
    """Raised when a valid file cannot be parsed. Maps to 422."""


def ingest(data: bytes, filename: str, content_type: str) -> ExtractionResult:
    """Validate, extract text, and return an ExtractionResult.

    Raises:
        IngestionError: unsupported type or file too large (caller should 4xx).
        ExtractionError: file is valid type but unreadable (caller should 422).
    """
    size = len(data)

    # Size check
    if size > MAX_FILE_BYTES:
        mb = size / 1024 / 1024
        raise IngestionError(f"File exceeds the 25 MB limit ({mb:.1f} MB received).")

    # Type check — use both MIME type and extension
    import os
    ext = os.path.splitext(filename)[1].lower()
    mime_ok = any(content_type.startswith(p) for p in SUPPORTED_MIME_PREFIXES)
    ext_ok = ext in SUPPORTED_EXTENSIONS

    if not mime_ok and not ext_ok:
        raise IngestionError(
            f"Unsupported file type '{content_type}' (extension: '{ext}'). "
            f"Accepted: PDF or plain text."
        )

    # Empty file check
    if size == 0:
        raise IngestionError("Uploaded file is empty.")

    # Extract
    if content_type == "application/pdf" or ext == ".pdf":
        text, page_count, ocr_pages, ocr_skipped = _extract_pdf(data)
    else:
        text, page_count, ocr_pages, ocr_skipped = _extract_text_file(data)

    return ExtractionResult(
        filename=filename,
        content_type=content_type,
        size_bytes=size,
        page_count=page_count,
        char_count=len(text),
        ocr_pages=ocr_pages,
        ocr_skipped_pages=ocr_skipped,
        text=text,
    )
