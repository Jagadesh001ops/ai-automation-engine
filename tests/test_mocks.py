"""Verify that mock_groq prevents live API calls and that parse_intent works
against the fixture without hitting the rate limit."""
from engine.intent_parser import parse_intent


def test_parse_intent_uses_mock_not_live_api(mock_groq):
    plan = parse_intent("Summarise this doc and quiz me on it.")

    assert plan.goal == "Summarise the document and generate quiz questions."
    assert plan.estimated_steps == 2
    assert plan.steps[0].name == "summarize_document"
    assert plan.steps[1].name == "generate_quiz_questions"
    mock_groq.chat.completions.create.assert_called_once()


def test_mock_groq_llm_response_configures_reply(mock_groq_llm_response, mock_groq):
    mock_groq_llm_response("Hello from mock.", input_tokens=5, output_tokens=3)
    response = mock_groq.chat.completions.create(
        model="any", messages=[{"role": "user", "content": "hi"}]
    )
    assert response.choices[0].message.content == "Hello from mock."
    assert response.usage.prompt_tokens == 5
    assert response.usage.completion_tokens == 3
