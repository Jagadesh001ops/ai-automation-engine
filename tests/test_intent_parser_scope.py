"""Day 7 — Retrieval-aware intent parser tests (mocked LLM)."""
import json
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from engine.intent_parser import parse_intent


def _mock_response(content: dict):
    msg = SimpleNamespace(content=json.dumps(content))
    choice = SimpleNamespace(message=msg)
    usage = SimpleNamespace(prompt_tokens=5, completion_tokens=10)
    return SimpleNamespace(choices=[choice], usage=usage)


def _plan(scope, steps=None, too_broad=False, too_broad_reason=None):
    steps = steps or [
        {"name": "summarize", "description": "Summarise", "input_key": "document", "output_key": "summary"}
    ]
    return {
        "goal": "test goal",
        "estimated_steps": len(steps),
        "scope": scope,
        "too_broad": too_broad,
        "too_broad_reason": too_broad_reason,
        "steps": steps,
    }


@pytest.fixture
def mock_groq_parser():
    fake = MagicMock()
    with patch("engine.intent_parser.get_client", return_value=fake):
        yield fake


def test_single_document_scope(mock_groq_parser):
    mock_groq_parser.chat.completions.create.return_value = _mock_response(
        _plan("single_document")
    )
    plan = parse_intent("Summarise this document")
    assert plan.scope == "single_document"


def test_library_scope(mock_groq_parser):
    mock_groq_parser.chat.completions.create.return_value = _mock_response(
        _plan("library", steps=[
            {"name": "retrieve_chunks", "description": "Retrieve", "input_key": "document", "output_key": "retrieved_chunks"},
            {"name": "summarize", "description": "Summarise", "input_key": "retrieved_chunks", "output_key": "summary"},
        ])
    )
    plan = parse_intent("Summarise everything in my library")
    assert plan.scope == "library"
    assert any(s.name == "retrieve_chunks" for s in plan.steps)


def test_too_broad_flag(mock_groq_parser):
    mock_groq_parser.chat.completions.create.return_value = _mock_response(
        _plan("library", too_broad=True, too_broad_reason="Request is too vague")
    )
    plan = parse_intent("Do everything with all my stuff")
    assert plan.too_broad is True
    assert plan.too_broad_reason


def test_available_nodes_injected_into_prompt(mock_groq_parser):
    mock_groq_parser.chat.completions.create.return_value = _mock_response(
        _plan("single_document")
    )
    custom_nodes = [{"name": "my_node", "description": "Does something custom"}]
    parse_intent("test request", available_nodes=custom_nodes)
    call_args = mock_groq_parser.chat.completions.create.call_args
    system_msg = call_args[1]["messages"][0]["content"]
    assert "my_node" in system_msg


def test_scope_defaults_to_single_document_on_old_response(mock_groq_parser):
    # Simulate an LLM that doesn't return scope (back-compat)
    old_style = {
        "goal": "test",
        "estimated_steps": 1,
        "steps": [{"name": "summarize", "description": "x", "input_key": "document", "output_key": "summary"}],
    }
    mock_groq_parser.chat.completions.create.return_value = _mock_response(old_style)
    plan = parse_intent("Summarise")
    assert plan.scope == "single_document"
    assert plan.too_broad is False
