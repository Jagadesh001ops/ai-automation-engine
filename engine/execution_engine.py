from typing import Any, Dict, List
from .schemas import WorkflowPlan
from .nodes import BaseNode, NodeResult


class StepTrace:
    def __init__(self, name: str, success: bool, execution_time_ms: float,
                 input_tokens: int, output_tokens: int, error: str = None):
        self.name = name
        self.success = success
        self.execution_time_ms = execution_time_ms or 0
        self.input_tokens = input_tokens or 0
        self.output_tokens = output_tokens or 0
        self.error = error

    def __repr__(self):
        return (f"  {self.name}: {self.execution_time_ms}ms | "
                f"in={self.input_tokens} out={self.output_tokens} tokens")


class ExecutionEngine:
    def __init__(self):
        self.registry: Dict[str, BaseNode] = {}

    def register_node(self, step_name: str, node: BaseNode):
        self.registry[step_name] = node

    def run(self, plan: WorkflowPlan,
            initial_state: Dict[str, Any]) -> tuple[Dict[str, Any], List[StepTrace]]:
        state = initial_state.copy()
        traces: List[StepTrace] = []

        print(f"\nExecuting: {plan.goal}")
        print(f"Steps: {plan.estimated_steps}\n")

        for step in plan.steps:
            print(f"Running: {step.name}...")
            node = self.registry.get(step.name)

            if node is None:
                print(f"  ✗ No node registered for '{step.name}' — skipping")
                continue

            result: NodeResult = node.execute(state)

            trace = StepTrace(
                name=step.name,
                success=result.success,
                execution_time_ms=result.execution_time_ms,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                error=result.error
            )
            traces.append(trace)

            if result.success:
                state[result.output_key] = result.output_value
                print(f"  ✓ {step.name} → {result.execution_time_ms}ms | "
                      f"tokens in={result.input_tokens} out={result.output_tokens}")
            else:
                print(f"  ✗ {step.name} failed: {result.error}")
                break

        # Print summary
        total_time = sum(t.execution_time_ms for t in traces)
        total_in = sum(t.input_tokens for t in traces)
        total_out = sum(t.output_tokens for t in traces)
        print(f"\n── Trace Summary ──────────────────────────")
        for t in traces:
            print(repr(t))
        print(f"  Total: {total_time}ms | {total_in + total_out} tokens")

        return state, traces