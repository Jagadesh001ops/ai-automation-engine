from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from typing import Any, Dict
from .nodes import BaseNode, NodeResult

client = Groq()


# ─── Generic fallback node ────────────────────────────────────────────────────

class LLMNode(BaseNode):
    """Dynamic node — behaviour driven entirely by config, not class definition."""

    def __init__(self, name: str, description: str, input_key: str, output_key: str):
        super().__init__(name=name, description=description)
        self.input_key = input_key
        self.output_key = output_key

    def execute(self, state: Dict[str, Any]) -> NodeResult:
        text = state.get(self.input_key)

        if not text:
            return self.handle_failure(
                ValueError(f"'{self.input_key}' not found in state")
            )

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": f"You are an expert assistant. Your job: {self.description}. Be concise and clear."
                },
                {
                    "role": "user",
                    "content": str(text)
                }
            ]
        )

        return NodeResult(
            success=True,
            output_key=self.output_key,
            output_value=response.choices[0].message.content
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
    "extract":   ExtractConceptsNode,
    "quiz":      GenerateQuizNode,
    "generate":  GenerateQuizNode,
}

def build_node_for_step(name: str, description: str,
                         input_key: str, output_key: str) -> LLMNode:
    """
    Routes a step to the right node class.
    Checks if the step name contains a known keyword → specialist node.
    Falls back to generic LLMNode if no match found.
    """
    for keyword, NodeClass in SPECIALIST_NODES.items():
        if keyword in name.lower():
            return NodeClass(
                name=name,
                input_key=input_key,
                output_key=output_key
            )

    # No specialist match — use generic node with step description as prompt
    print(f"  → No specialist for '{name}', using generic LLMNode")
    return LLMNode(
        name=name,
        description=description,
        input_key=input_key,
        output_key=output_key
    )