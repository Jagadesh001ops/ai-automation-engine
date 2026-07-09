from engine.llm_nodes import (
    ExtractConceptsNode,
    GenerateQuizNode,
    LLMNode,
    SummarizeNode,
    build_node_for_step,
)


def build(name):
    return build_node_for_step(
        name=name,
        description="Do the requested work.",
        input_key="document",
        output_key="result",
    )


def test_routes_known_specialist_steps():
    assert isinstance(build("summarize_document"), SummarizeNode)
    assert isinstance(build("extract_key_concepts"), ExtractConceptsNode)
    assert isinstance(build("generate_quiz_questions"), GenerateQuizNode)


def test_generate_summary_does_not_route_to_quiz_node():
    node = build("generate_summary")

    assert isinstance(node, LLMNode)
    assert not isinstance(node, GenerateQuizNode)
    assert type(node) is LLMNode
