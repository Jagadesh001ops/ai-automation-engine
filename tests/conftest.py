"""Shared pytest fixtures.

The mock_groq fixture patches the Groq client used by intent_parser and
llm_nodes so that tests never make live API calls and never hit the daily
rate limit.  Any test that calls parse_intent() or an LLMNode.execute()
should use this fixture (or a fixture that depends on it).
"""
from __future__ import annotations

import pathlib
import sys

# Ensure the worktree's engine package takes priority over the main repo's.
_worktree_root = str(pathlib.Path(__file__).parent.parent)
if _worktree_root not in sys.path:
    sys.path.insert(0, _worktree_root)

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _make_groq_response(content: str, input_tokens: int = 10, output_tokens: int = 20):
    """Build a fake Groq chat-completion response object."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=input_tokens, completion_tokens=output_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


FAKE_PLAN_JSON = """{
    "goal": "Summarise the document and generate quiz questions.",
    "estimated_steps": 2,
    "steps": [
        {
            "name": "summarize_document",
            "description": "Summarise the document.",
            "input_key": "document",
            "output_key": "summary"
        },
        {
            "name": "generate_quiz_questions",
            "description": "Generate quiz questions from the summary.",
            "input_key": "summary",
            "output_key": "quiz_questions"
        }
    ]
}"""


@pytest.fixture
def mock_groq():
    """Patch the Groq client in both intent_parser and llm_nodes.

    The fixture yields the mock so tests can inspect calls or change the
    return value for specific scenarios.
    """
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_groq_response(
        FAKE_PLAN_JSON
    )

    with (
        patch("engine.intent_parser.get_client", return_value=fake_client),
        patch("engine.llm_nodes.get_client", return_value=fake_client),
    ):
        yield fake_client


@pytest.fixture
def mock_groq_llm_response(mock_groq):
    """Convenience fixture: mock_groq pre-configured for a plain-text LLM reply."""

    def _set(content: str, input_tokens: int = 10, output_tokens: int = 20):
        mock_groq.chat.completions.create.return_value = _make_groq_response(
            content, input_tokens, output_tokens
        )

    return _set
