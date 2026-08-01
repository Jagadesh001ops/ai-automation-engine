"""Day 10 — Verification node tests (mocked LLM)."""
import json
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from engine.verification_node import verify_quiz_items, VerifyQuizNode


def _llm_verdict(correct: bool, reason: str = "test reason"):
    msg = SimpleNamespace(content=json.dumps({"correct": correct, "reason": reason}))
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _llm_regen(answer: str = "B", explanation: str = "corrected explanation"):
    msg = SimpleNamespace(content=json.dumps({"answer": answer, "explanation": explanation}))
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


SAMPLE_ITEM = {
    "question": "What is the capital of France?",
    "options": {"A": "Berlin", "B": "Paris", "C": "Rome", "D": "Madrid"},
    "answer": "B",
    "explanation": "Paris is the capital of France.",
    "citation": None,
}

SAMPLE_CHUNK = {"chunk_id": 1, "document_id": 1, "text": "Paris is the capital of France.", "char_start": 0, "char_end": 31}


def test_verify_correct_item_passes():
    with patch("engine.verification_node._llm") as mock_llm:
        mock_llm.return_value.chat.completions.create.return_value = _llm_verdict(True)
        results = verify_quiz_items([SAMPLE_ITEM], [SAMPLE_CHUNK])
    assert results[0]["verified"] is True


def test_verify_wrong_item_triggers_regen_and_reflag():
    responses = [
        _llm_verdict(False, "Answer is wrong"),   # first verify: fail
        _llm_regen("C", "corrected explanation"), # regen
        _llm_verdict(False, "Still wrong"),        # re-verify: fail again
    ]
    with patch("engine.verification_node._llm") as mock_llm:
        mock_llm.return_value.chat.completions.create.side_effect = responses
        results = verify_quiz_items([SAMPLE_ITEM], [SAMPLE_CHUNK])
    assert results[0]["verified"] is False
    assert "FLAGGED" in results[0]["verification_note"]


def test_verify_wrong_then_fixed():
    responses = [
        _llm_verdict(False, "Answer was wrong"),  # first verify: fail
        _llm_regen("B", "Paris is correct"),       # regen
        _llm_verdict(True, "Correct after regen"), # re-verify: pass
    ]
    with patch("engine.verification_node._llm") as mock_llm:
        mock_llm.return_value.chat.completions.create.side_effect = responses
        results = verify_quiz_items([SAMPLE_ITEM], [SAMPLE_CHUNK])
    assert results[0]["verified"] is True


def test_verify_no_chunks_skips():
    results = verify_quiz_items([SAMPLE_ITEM], [])
    assert results[0]["verified"] is None
    assert "no source chunks" in results[0]["verification_note"]


def test_verify_multiple_items():
    items = [SAMPLE_ITEM, {**SAMPLE_ITEM, "question": "Question 2"}]
    with patch("engine.verification_node._llm") as mock_llm:
        mock_llm.return_value.chat.completions.create.return_value = _llm_verdict(True)
        results = verify_quiz_items(items, [SAMPLE_CHUNK])
    assert len(results) == 2
    assert all(r["verified"] is True for r in results)


def test_verify_quiz_node_accepts_json_string():
    node = VerifyQuizNode()
    items_json = json.dumps([SAMPLE_ITEM])
    state = {"quiz_items": items_json, "retrieved_chunks": [SAMPLE_CHUNK]}
    with patch("engine.verification_node._llm") as mock_llm:
        mock_llm.return_value.chat.completions.create.return_value = _llm_verdict(True)
        result = node.execute(state)
    assert result.success
    assert isinstance(result.output_value, list)


def test_verify_quiz_node_fails_on_empty():
    node = VerifyQuizNode()
    result = node.execute({"quiz_items": [], "retrieved_chunks": [SAMPLE_CHUNK]})
    assert not result.success


def test_verify_quiz_node_handles_list_input():
    node = VerifyQuizNode()
    state = {"quiz_items": [SAMPLE_ITEM], "retrieved_chunks": [SAMPLE_CHUNK]}
    with patch("engine.verification_node._llm") as mock_llm:
        mock_llm.return_value.chat.completions.create.return_value = _llm_verdict(True)
        result = node.execute(state)
    assert result.success
    assert result.output_value[0]["verified"] is True
