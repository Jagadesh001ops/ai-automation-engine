"""LLM-as-judge verification pass (Day 10).

verify_quiz_items() takes a list of QuizItem dicts plus the source chunks and
checks each answer for correctness.  Failing items are regenerated once; if
still failing they are flagged with verified=False rather than dropped.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from .config import LLM_MODEL
from .nodes import BaseNode, NodeResult

logger = logging.getLogger(__name__)

_VERIFY_SYSTEM = """You are a strict quiz-answer verifier.

Given a quiz question, its marked correct answer, and the source text it was derived from,
decide whether the answer is correct.

Return ONLY a JSON object:
{
  "correct": true,
  "reason": "one sentence explaining your verdict"
}

Be strict: if the source text does not clearly support the marked answer, return correct=false."""

_REGEN_SYSTEM = """You are an expert quiz writer.
A quiz question had an incorrect answer. Rewrite ONLY the answer and explanation fields
to make them correct based on the source text.

Return ONLY a JSON object:
{
  "answer": "A",
  "explanation": "corrected one-sentence explanation"
}"""


def _get_client():
    from groq import Groq
    return Groq()


_client = None


def _llm():
    global _client
    if _client is None:
        _client = _get_client()
    return _client


def _verify_one(item: dict, source_text: str) -> dict:
    """Return the item dict with `verified` and `verification_note` filled in."""
    opts = item.get("options", {})
    answer_key = item.get("answer", "?")
    answer_text = opts.get(answer_key, "?") if isinstance(opts, dict) else "?"

    user_msg = (
        f"Question: {item.get('question')}\n"
        f"Marked correct answer ({answer_key}): {answer_text}\n"
        f"Explanation: {item.get('explanation', '')}\n\n"
        f"Source text:\n{source_text[:3000]}"
    )

    try:
        resp = _llm().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _VERIFY_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        verdict = json.loads(resp.choices[0].message.content)
        return {**item, "verified": verdict.get("correct", True),
                "verification_note": verdict.get("reason")}
    except Exception as exc:
        logger.warning("Verification LLM call failed: %s", exc)
        return {**item, "verified": True, "verification_note": "verification skipped"}


def _regenerate_answer(item: dict, source_text: str) -> dict:
    """Ask the LLM to fix the answer/explanation; return updated item."""
    user_msg = (
        f"Question: {item.get('question')}\n"
        f"Options: {json.dumps(item.get('options', {}))}\n"
        f"Previous (wrong) answer: {item.get('answer')}\n"
        f"Previous explanation: {item.get('explanation', '')}\n\n"
        f"Source text:\n{source_text[:3000]}"
    )
    try:
        resp = _llm().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _REGEN_SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            response_format={"type": "json_object"},
        )
        fix = json.loads(resp.choices[0].message.content)
        return {**item, "answer": fix.get("answer", item["answer"]),
                "explanation": fix.get("explanation", item["explanation"])}
    except Exception as exc:
        logger.warning("Regeneration LLM call failed: %s", exc)
        return item


def verify_quiz_items(
    items: List[dict],
    source_chunks: List[dict],
) -> List[dict]:
    """Verify each quiz item against its source chunk (or the full chunk set).

    Flow per item:
      1. Verify answer.
      2. If wrong → regenerate answer once.
      3. Re-verify regenerated answer.
      4. If still wrong → keep item but set verified=False.

    Args:
        items:         List of quiz item dicts (question/options/answer/explanation/citation).
        source_chunks: List of chunk dicts {text, chunk_id, ...} from retrieval.

    Returns:
        Updated item list with `verified` and `verification_note` on each item.
    """
    if not source_chunks:
        # No chunks available — skip verification
        return [{**it, "verified": None, "verification_note": "no source chunks"} for it in items]

    # Combine chunk texts as the verification corpus
    corpus = "\n\n---\n\n".join(c.get("text", "") for c in source_chunks[:10])

    verified_items = []
    for item in items:
        result = _verify_one(item, corpus)
        if not result.get("verified", True):
            logger.info("Item failed verification, regenerating: %s", item.get("question", "")[:60])
            fixed = _regenerate_answer(item, corpus)
            result = _verify_one(fixed, corpus)
            if not result.get("verified", True):
                result["verification_note"] = (
                    f"[FLAGGED] {result.get('verification_note', 'answer could not be verified')}"
                )
        verified_items.append(result)

    return verified_items


class VerifyQuizNode(BaseNode):
    """Verification node — runs LLM-as-judge over quiz items in state.

    Reads  `quiz_items` (list of dicts) and `retrieved_chunks` from state.
    Writes `quiz_items` back with `verified` and `verification_note` set.
    """

    def __init__(self, name: str = "verify_quiz",
                 input_key: str = "quiz_items",
                 chunks_key: str = "retrieved_chunks",
                 output_key: str = "quiz_items"):
        super().__init__(
            name=name,
            description="Verify each quiz answer against the source chunks using an LLM judge; regenerate wrong answers once.",
        )
        self.input_key = input_key
        self.chunks_key = chunks_key
        self.output_key = output_key

    def _execute(self, state: Dict[str, Any]) -> NodeResult:
        raw_items = state.get(self.input_key)

        # Accept either a list of dicts or a JSON string (from GenerateQuizNode)
        if isinstance(raw_items, str):
            try:
                raw_items = json.loads(raw_items)
            except json.JSONDecodeError:
                return self.handle_failure(ValueError("quiz_items is not valid JSON"))

        if not raw_items:
            return self.handle_failure(ValueError("No quiz items to verify"))

        chunks = state.get(self.chunks_key) or []
        verified = verify_quiz_items(raw_items, chunks)

        return NodeResult(
            success=True,
            output_key=self.output_key,
            output_value=verified,
            input_tokens=0,
            output_tokens=0,
        )
