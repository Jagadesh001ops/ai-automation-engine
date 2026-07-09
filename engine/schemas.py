from pydantic import BaseModel, Field, model_validator
from typing import List

class WorkflowStep(BaseModel):
    name: str = Field(description="snake_case step name e.g. summarize_document")
    description: str = Field(description="One sentence describing what this step does")
    input_key: str = Field(description="State key this step reads from")
    output_key: str = Field(description="State key this step writes to")

class WorkflowPlan(BaseModel):
    goal: str = Field(description="The user's intent in one clear sentence")
    steps: List[WorkflowStep] = Field(description="Ordered list of workflow steps")
    estimated_steps: int = Field(ge=1, le=10, description="Total number of steps")

    @model_validator(mode="after")
    def estimated_steps_matches_steps(self):
        if self.estimated_steps != len(self.steps):
            raise ValueError("estimated_steps must match the number of steps")
        return self
