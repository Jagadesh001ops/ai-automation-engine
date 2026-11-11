"""Text chunking with token-aware sliding window.

Splits extracted text into overlapping chunks suitable for embedding and
retrieval.  Chunks are delimited by sentence or paragraph boundaries where
possible so that embeddings represent coherent units of meaning.

Default parameters (tune against Psychology 2e once real output is visible):
  CHUNK_TOKENS  = 600   target chunk size in tokens
  OVERLAP_RATIO = 0.15  fraction of chunk size used as look-back overlap
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List

CHUNK_TOKENS: int = 600
OVERLAP_RATIO: float = 0.15

# Rough chars-per-token ratio for English prose (good enough for splitting;
# exact token counts are not needed here).
_CHARS_PER_TOKEN: float = 4.0

_CHUNK_CHARS: int = int(CHUNK_TOKENS * _CHARS_PER_TOKEN)          # ~2400
_OVERLAP_CHARS: int = int(_CHUNK_CHARS * OVERLAP_RATIO)            # ~360

# Split text into sentences (preserve delimiter).
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    index: int           # 0-based position within document
    text: str
    char_start: int      # inclusive offset in original text
    char_end: int        # exclusive offset in original text
    content_hash: str    # SHA-256 of stripped text — used for deduplication


def _sentence_boundaries(text: str) -> List[int]:
    """Return list of character offsets where sentences end (exclusive)."""
    boundaries = [m.end() for m in _SENTENCE_RE.finditer(text)]
    if not boundaries or boundaries[-1] < len(text):
        boundaries.append(len(text))
    return boundaries


def chunk_text(text: str) -> List[Chunk]:
    """Split *text* into overlapping Chunks.

    Strategy:
      1. Split on sentence boundaries to avoid cutting mid-sentence.
      2. Accumulate sentences until the window reaches CHUNK_CHARS.
      3. Slide forward by (CHUNK_CHARS - OVERLAP_CHARS) before starting the
         next window so consecutive chunks share roughly OVERLAP_RATIO content.
    """
    text = text.strip()
    if not text:
        return []

    boundaries = _sentence_boundaries(text)
    chunks: List[Chunk] = []
    start = 0
    idx = 0

    while start < len(text):
        # Find the furthest boundary that keeps the window <= CHUNK_CHARS
        end = start
        for b in boundaries:
            if b <= start:
                continue
            if b - start <= _CHUNK_CHARS:
                end = b
            else:
                break

        # If no sentence boundary was found within the window (e.g. a very
        # long paragraph), hard-cut at CHUNK_CHARS.
        if end == start:
            end = min(start + _CHUNK_CHARS, len(text))

        chunk_text_str = text[start:end].strip()
        if chunk_text_str:
            content_hash = hashlib.sha256(chunk_text_str.encode()).hexdigest()
            chunks.append(Chunk(
                index=idx,
                text=chunk_text_str,
                char_start=start,
                char_end=end,
                content_hash=content_hash,
            ))
            idx += 1

        if end >= len(text):
            break

        # Slide forward, leaving overlap
        advance = max(1, end - start - _OVERLAP_CHARS)
        start += advance

    return chunks
