import pytest
from pydantic import ValidationError

from engine.schemas import WorkflowPlan, WorkflowStep


def make_step(name="summarize_document"):
    return WorkflowStep(
        name=name,
        description="Summarize the document.",
        input_key="document",
        output_key="summary",
    )


def test_workflow_plan_accepts_matching_step_count():
    plan = WorkflowPlan(
        goal="Summarize the document.",
        estimated_steps=1,
        steps=[make_step()],
    )

    assert plan.estimated_steps == 1
    assert plan.steps[0].name == "summarize_document"


def test_workflow_plan_rejects_mismatched_step_count():
    with pytest.raises(ValidationError, match="estimated_steps must match"):
        WorkflowPlan(
            goal="Summarize then quiz.",
            estimated_steps=2,
            steps=[make_step()],
        )


def test_workflow_plan_rejects_out_of_range_estimated_steps():
    with pytest.raises(ValidationError):
        WorkflowPlan(
            goal="No steps.",
            estimated_steps=0,
            steps=[],
        )
