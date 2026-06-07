from typing import Any, Dict
from .schemas import WorkflowPlan
from .nodes import BaseNode, NodeResult


class ExecutionEngine:
    def __init__(self):
        self.registry: Dict[str, BaseNode] = {}

    def register_node(self, step_name: str, node: BaseNode):
        self.registry[step_name] = node

    def run(self, plan: WorkflowPlan, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        state = initial_state.copy()

        print(f"\nExecuting: {plan.goal}")
        print(f"Steps: {plan.estimated_steps}\n")

        for step in plan.steps:
            print(f"Running: {step.name}...")

            # Look up the node for this step
            node = self.registry.get(step.name)

            if node is None:
                print(f"  ✗ No node registered for '{step.name}' — skipping")
                continue

            # Run the node
            try:
                result: NodeResult = node.execute(state)
            except Exception as e:
                result = node.handle_failure(e)

            # Handle result
            if result.success:
                state[result.output_key] = result.output_value
                print(f"  ✓ {step.name} → wrote '{result.output_key}' to state")
            else:
                print(f"  ✗ {step.name} failed: {result.error}")
                break

        return state