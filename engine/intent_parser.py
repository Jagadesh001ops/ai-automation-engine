from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from .schemas import WorkflowPlan, WorkflowStep
import json

client = Groq()

SYSTEM_PROMPT = """You are an AI workflow planner.
Analyse the user's document-processing request and break it into an ordered sequence of workflow steps.

Return ONLY a JSON object with this exact structure, no extra text:
{
    "goal": "user's intent in one sentence",
    "estimated_steps": 3,
    "steps": [
        {
            "name": "snake_case_step_name",
            "description": "One sentence describing what this step does",
            "input_key": "key this step reads from",
            "output_key": "key this step writes to"
        }
    ]
}

Rules:
- Each step must be atomic — one job only
- Use snake_case for all step names
- First step always reads from "document"
- Each step's input_key should match the previous step's output_key
- estimated_steps must match the actual number of steps"""


def parse_intent(user_request: str) -> WorkflowPlan:
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_request}
        ]
    )

    raw = response.choices[0].message.content

    data = json.loads(raw)

    return WorkflowPlan(**data)