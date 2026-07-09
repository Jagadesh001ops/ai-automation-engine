from dotenv import load_dotenv
load_dotenv()

from typing import Any, Dict
from .nodes import BaseNode, NodeResult
from .config import LLM_MODEL

client = None


def get_client():
    global client
    if client is None:
        from groq import Groq
        client = Groq()
    return client


# ─── Generic fallback node ────────────────────────────────────────────────────

class LLMNode(BaseNode):
    """Dynamic node — behaviour driven entirely by config, not class definition."""

    def __init__(self, name: str, description: str, input_key: str, output_key: str):
        super().__init__(name=name, description=description)
        self.input_key = input_key
        self.output_key = output_key

    def _execute(self, state: Dict[str, Any]) -> NodeResult:
        text = state.get(self.input_key)

        if not text:
            return self.handle_failure(
                ValueError(f"'{self.input_key}' not found in state")
            )

        system_msg = f"You are an expert assistant. Your job: {self.description}. Be concise and clear."
        user_msg = str(text)

        response = get_client().chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg}
            ]
        )

        output = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        return NodeResult(
            success=True,
            output_key=self.output_key,
            output_value=output,
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )


# ─── Specialist nodes ─────────────────────────────────────────────────────────

class SummarizeNode(LLMNode):
    """Specialist node with a tuned prompt for summarization."""

    def __init__(self, name: str, input_key: str, output_key: str):
        super().__init__(
            name=name,
            description="Summarize the given text into a clear, concise paragraph capturing only the main ideas.",
            input_key=input_key,
            output_key=output_key
        )


class ExtractConceptsNode(LLMNode):
    """Specialist node with a tuned prompt for concept extraction."""

    def __init__(self, name: str, input_key: str, output_key: str):
        super().__init__(
            name=name,
            description="Extract the 5 most important concepts from the text. Return a numbered list, one concept per line with a brief explanation.",
            input_key=input_key,
            output_key=output_key
        )


class GenerateQuizNode(LLMNode):
    """Specialist node with a tuned prompt for quiz generation."""

    def __init__(self, name: str, input_key: str, output_key: str):
        super().__init__(
            name=name,
            description="Create 5 multiple choice questions based on the given content. Each question must have 4 options (A, B, C, D) and clearly mark the correct answer.",
            input_key=input_key,
            output_key=output_key
        )


# ─── Router — the semi-dynamic layer ─────────────────────────────────────────

SPECIALIST_NODES = {
    "summarize": SummarizeNode,
    "summarize_document": SummarizeNode,
    "summary": SummarizeNode,
    "extract": ExtractConceptsNode,
    "extract_concepts": ExtractConceptsNode,
    "extract_key_concepts": ExtractConceptsNode,
    "quiz": GenerateQuizNode,
    "generate_quiz": GenerateQuizNode,
    "generate_quiz_questions": GenerateQuizNode,
    "create_quiz": GenerateQuizNode,
}

SPECIALIST_PREFIXES = (
    ("summarize_", SummarizeNode),
    ("summary_", SummarizeNode),
    ("extract_", ExtractConceptsNode),
    ("quiz_", GenerateQuizNode),
    ("generate_quiz_", GenerateQuizNode),
    ("create_quiz_", GenerateQuizNode),
)


def build_node_for_step(name: str, description: str,
                         input_key: str, output_key: str) -> LLMNode:
    """
    Routes a step to the right node class.
    Uses exact aliases and specific prefixes for specialist nodes.
    Falls back to generic LLMNode if no match found.
    """
    normalized_name = name.strip().lower().replace("-", "_")

    NodeClass = SPECIALIST_NODES.get(normalized_name)
    if NodeClass is None:
        for prefix, PrefixNodeClass in SPECIALIST_PREFIXES:
            if normalized_name.startswith(prefix):
                NodeClass = PrefixNodeClass
                break

    if NodeClass is not None:
        return NodeClass(
            name=name,
            input_key=input_key,
            output_key=output_key
        )

    print(f"  → No specialist for '{name}', using generic LLMNode")
    return LLMNode(
        name=name,
        description=description,
        input_key=input_key,
        output_key=output_key
    )
