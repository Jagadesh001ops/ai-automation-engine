from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class WorkflowStep(BaseModel):
    name: str = Field(description="snake_case step name e.g. summarize_document")
    description: str = Field(description="One sentence describing what this step does")
    input_key: str = Field(description="State key this step reads from")
    output_key: str = Field(description="State key this step writes to")


class WorkflowPlan(BaseModel):
    goal: str = Field(description="The user's intent in one clear sentence")
    steps: List[WorkflowStep] = Field(description="Ordered list of workflow steps")
    estimated_steps: int = Field(ge=1, le=10, description="Total number of steps")
    scope: Literal["single_document", "multi_document", "library"] = Field(
        default="single_document",
        description="Scope of document access required for this plan",
    )
    too_broad: bool = Field(
        default=False,
        description="True when the request is too broad to plan reliably",
    )
    too_broad_reason: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of why the request is too broad",
    )

    @model_validator(mode="after")
    def estimated_steps_matches_steps(self):
        if self.estimated_steps != len(self.steps):
            raise ValueError("estimated_steps must match the number of steps")
        return self


# ─── Citation & quiz output schemas ──────────────────────────────────────────

class Citation(BaseModel):
    chunk_id: Optional[int] = None
    document_id: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    excerpt: Optional[str] = None   # short quoted text from the source chunk


class QuizOption(BaseModel):
    A: str
    B: str
    C: str
    D: str


class QuizItem(BaseModel):
    question: str
    options: QuizOption
    answer: Literal["A", "B", "C", "D"]
    explanation: str
    citation: Optional[Citation] = None
    verified: Optional[bool] = None          # set by Day 10 verification pass
    verification_note: Optional[str] = None  # set when verified=False


class QuizOutput(BaseModel):
    items: List[QuizItem]
