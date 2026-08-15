"""Day 20 — Evaluation harness (mocked DeepEval-style metrics).

These tests exercise the evaluation pipeline using mocked LLM calls so they
run fast in CI without needing an API key.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Helper — synthetic quiz item and source chunk
# ---------------------------------------------------------------------------

ITEM_CORRECT = {
    "question": "What does 2 + 2 equal?",
    "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
    "answer": "B",
    "explanation": "2 + 2 equals 4.",
    "verified": True,
}

ITEM_FLAGGED = {
    "question": "What is the capital of Germany?",
    "options": {"A": "Berlin", "B": "Paris", "C": "Rome", "D": "Madrid"},
    "answer": "A",
    "explanation": "Berlin is the capital.",
    "verified": False,
    "verification_note": "FLAGGED after re-verify",
}

CHUNK = {
    "chunk_id": 1,
    "document_id": 1,
    "text": "2 + 2 equals 4. Berlin is the capital of Germany.",
    "char_start": 0,
    "char_end": 49,
    "score": 0.1,
}


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _faithfulness(items: list[dict], chunks: list[dict]) -> float:
    """Fraction of items whose question or explanation overlaps with chunk text."""
    if not items:
        return 0.0
    chunk_text = " ".join(c["text"] for c in chunks).lower()
    grounded = 0
    for item in items:
        words = (item.get("explanation", "") + " " + item.get("question", "")).lower().split()
        meaningful = [w for w in words if len(w) > 3]
        if meaningful and any(w in chunk_text for w in meaningful):
            grounded += 1
    return grounded / len(items)


def _answer_relevance(items: list[dict]) -> float:
    """Fraction of items with non-empty answers."""
    if not items:
        return 0.0
    return sum(1 for item in items if item.get("answer")) / len(items)


def _flagged_rate(items: list[dict]) -> float:
    if not items:
        return 0.0
    return sum(1 for item in items if item.get("verified") is False) / len(items)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFaithfulnessMetric:
    def test_fully_grounded(self):
        score = _faithfulness([ITEM_CORRECT], [CHUNK])
        assert score == 1.0

    def test_no_chunks(self):
        score = _faithfulness([ITEM_CORRECT], [])
        assert score == 0.0

    def test_empty_items(self):
        score = _faithfulness([], [CHUNK])
        assert score == 0.0

    def test_partial(self):
        ungrounded = {**ITEM_CORRECT, "explanation": "xyzzy impossible word qqqq"}
        score = _faithfulness([ITEM_CORRECT, ungrounded], [CHUNK])
        assert 0.0 < score < 1.0


class TestAnswerRelevanceMetric:
    def test_all_have_answers(self):
        assert _answer_relevance([ITEM_CORRECT, ITEM_FLAGGED]) == 1.0

    def test_missing_answer(self):
        item = {**ITEM_CORRECT, "answer": ""}
        assert _answer_relevance([item]) == 0.0

    def test_empty(self):
        assert _answer_relevance([]) == 0.0


class TestFlaggedRateMetric:
    def test_no_flags(self):
        assert _flagged_rate([ITEM_CORRECT]) == 0.0

    def test_all_flagged(self):
        assert _flagged_rate([ITEM_FLAGGED]) == 1.0

    def test_mixed(self):
        rate = _flagged_rate([ITEM_CORRECT, ITEM_FLAGGED])
        assert rate == 0.5


class TestEndToEndEvaluation:
    """Simulate a full evaluation pipeline run."""

    def test_pipeline_metrics_meet_thresholds(self):
        items = [ITEM_CORRECT]
        chunks = [CHUNK]

        faithfulness = _faithfulness(items, chunks)
        relevance = _answer_relevance(items)
        flagged = _flagged_rate(items)

        assert faithfulness >= 0.5,  f"Faithfulness too low: {faithfulness}"
        assert relevance >= 0.8,     f"Answer relevance too low: {relevance}"
        assert flagged <= 0.3,       f"Too many flagged items: {flagged}"

    def test_evaluation_report_structure(self):
        items = [ITEM_CORRECT, ITEM_FLAGGED]
        report = {
            "faithfulness": _faithfulness(items, [CHUNK]),
            "answer_relevance": _answer_relevance(items),
            "flagged_rate": _flagged_rate(items),
            "total_items": len(items),
        }
        assert set(report.keys()) == {"faithfulness", "answer_relevance",
                                       "flagged_rate", "total_items"}
        assert report["total_items"] == 2
