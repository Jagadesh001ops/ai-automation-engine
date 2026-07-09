from typing import Any, Dict

from engine.execution_engine import ExecutionEngine
from engine.nodes import BaseNode, NodeResult
from engine.schemas import WorkflowPlan, WorkflowStep


class FakeNode(BaseNode):
    def __init__(
        self,
        name: str,
        input_key: str,
        output_key: str,
        suffix: str,
        input_tokens: int,
        output_tokens: int,
    ):
        super().__init__(name=name, description="fake node")
        self.input_key = input_key
        self.output_key = output_key
        self.suffix = suffix
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def _execute(self, state: Dict[str, Any]) -> NodeResult:
        return NodeResult(
            success=True,
            output_key=self.output_key,
            output_value=f"{state[self.input_key]} {self.suffix}",
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


def step(name, input_key, output_key):
    return WorkflowStep(
        name=name,
        description=f"{name} description",
        input_key=input_key,
        output_key=output_key,
    )


def test_execution_engine_runs_registered_nodes_and_records_traces():
    plan = WorkflowPlan(
        goal="Run fake workflow.",
        estimated_steps=2,
        steps=[
            step("first", "document", "first_output"),
            step("second", "first_output", "second_output"),
        ],
    )
    engine = ExecutionEngine()
    engine.register_node("first", FakeNode("first", "document", "first_output", "one", 3, 5))
    engine.register_node("second", FakeNode("second", "first_output", "second_output", "two", 7, 11))

    final_state, traces = engine.run(plan, {"document": "start"})

    assert final_state["first_output"] == "start one"
    assert final_state["second_output"] == "start one two"
    assert [trace.name for trace in traces] == ["first", "second"]
    assert sum(trace.input_tokens + trace.output_tokens for trace in traces) == 26
