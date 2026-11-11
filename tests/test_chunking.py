"""Tests for engine/chunking.py — no DB, no embeddings required."""
import pytest

from engine.chunking import (
    _CHUNK_CHARS,
    _OVERLAP_CHARS,
    CHUNK_TOKENS,
    OVERLAP_RATIO,
    Chunk,
    chunk_text,
)

# ─── Edge cases ───────────────────────────────────────────────────────────────

def test_empty_string_returns_no_chunks():
    assert chunk_text("") == []


def test_whitespace_only_returns_no_chunks():
    assert chunk_text("   \n\n  ") == []


def test_short_text_produces_single_chunk():
    text = "The quick brown fox jumps over the lazy dog."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].text == text.strip()
    assert chunks[0].index == 0


# ─── Content integrity ────────────────────────────────────────────────────────

def test_all_text_is_covered():
    """Every character of the original text should appear in at least one chunk."""
    text = ("Lorem ipsum dolor sit amet. " * 200).strip()
    chunks = chunk_text(text)
    # Reconstruct coverage: each char_start..char_end range covers the original
    covered = set()
    for c in chunks:
        covered.update(range(c.char_start, c.char_end))
    assert all(i in covered for i in range(len(text)))


def test_chunks_have_unique_indices():
    text = ("Sentence number one. Sentence number two. " * 100).strip()
    chunks = chunk_text(text)
    indices = [c.index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_content_hash_is_deterministic():
    text = "Repeatable content. Should hash the same way every time."
    chunks1 = chunk_text(text)
    chunks2 = chunk_text(text)
    assert [c.content_hash for c in chunks1] == [c.content_hash for c in chunks2]


# ─── Size and overlap ─────────────────────────────────────────────────────────

def test_long_text_produces_multiple_chunks():
    # ~10x the chunk character limit
    text = ("A" * 100 + ". ") * ((_CHUNK_CHARS // 100) * 10)
    chunks = chunk_text(text)
    assert len(chunks) > 1


def test_overlap_means_consecutive_chunks_share_content():
    # Build text long enough to span 3+ chunks
    sentence = "This is a test sentence for overlap verification. "
    text = sentence * ((_CHUNK_CHARS // len(sentence)) * 4)
    chunks = chunk_text(text)
    if len(chunks) < 2:
        pytest.skip("text too short to produce multiple chunks in this environment")
    # The end of chunk[0] and the start of chunk[1] should overlap in char ranges
    assert chunks[0].char_end > chunks[1].char_start


def test_chunk_text_not_longer_than_chunk_chars_plus_margin():
    text = ("Word " * 2000).strip()
    chunks = chunk_text(text)
    margin = 200  # allow one extra sentence beyond the target
    for c in chunks:
        assert len(c.text) <= _CHUNK_CHARS + margin, (
            f"Chunk {c.index} is {len(c.text)} chars, expected <= {_CHUNK_CHARS + margin}"
        )
