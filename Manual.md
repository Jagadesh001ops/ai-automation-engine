# AI Workflow Engine — Project Manual

> Last updated: Phase 1 complete, Phase 2 in progress (Execution Engine)

---

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [What You Are Building](#2-what-you-are-building)
3. [Skills Learned](#3-skills-learned)
4. [Project Setup](#4-project-setup)
5. [Project Structure](#5-project-structure)
6. [Components Built](#6-components-built)
7. [Concepts Behind the Code](#7-concepts-behind-the-code)
8. [Interview Answers](#8-interview-answers)
9. [Changelog](#9-changelog)

---

## 1. Project Overview

**Project:** AI Workflow Automation Engine
**Stack:** Python 3.12, Groq API (llama-3.3-70b-versatile), Pydantic, FastAPI (upcoming)
**Goal:** Build a production-ready AI orchestration system that transforms natural language requests into structured, executable workflows — and use it to learn every skill needed for an AI Engineer role.

---

## 2. What You Are Building

A system that takes a plain English request like:

> "I have a research paper. Summarize it, extract key concepts, and generate quiz questions."

And turns it into a structured, executable pipeline:

```
document → extract_text → text_content → summarize → summary → extract_concepts → key_concepts → generate_quiz → quiz_questions
```

### Architecture

```
User Request
     ↓
Intent Parser        ← LLM plans the workflow
     ↓
WorkflowPlan         ← Pydantic-validated schema
     ↓
Execution Engine     ← Runs each step in order
     ↓
Node Registry        ← Looks up the right node per step
     ↓
Workflow Nodes       ← Each node does one job (LLM-powered)
     ↓
State Store          ← Passes data between nodes
     ↓
Final Output
```

### Core Philosophy
- **Separate planning from execution** — LLM designs the pipeline, engine runs it
- **Use as little AI as possible** — only LLM calls where needed, deterministic logic elsewhere
- **Structured state transfer** — all data between nodes is typed and validated

---

## 3. Skills Learned

### Phase 1 — Foundations

| Topic | What You Learned |
|-------|-----------------|
| Virtual environments | `python -m venv venv`, activate, pip install, requirements.txt |
| Git | init, add, commit, push, .gitignore, branching |
| Environment variables | .env files, python-dotenv, never commit secrets |
| Groq SDK | chat.completions.create, system prompt, messages array, response parsing |
| Prompt engineering | Role, few-shot, chain of thought, positive instructions, XML delimiters |
| Pydantic | BaseModel, Field, ValidationError, nested models, type enforcement |

### Phase 2 — AI System Design (in progress)

| Topic | What You Learned |
|-------|-----------------|
| Node architecture | BaseNode, ABC, abstractmethod, NodeResult |
| Strategy pattern | Common interface, different behaviour per node |
| State management | Shared Dict passed through pipeline, input_key/output_key chaining |

---

## 4. Project Setup

### Prerequisites
- Python 3.12
- Groq API key (free at console.groq.com)
- Git

### First-time setup
```bash
# Create project
mkdir ai-workflow-engine
cd ai-workflow-engine
py -3.12 -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install groq pydantic python-dotenv
pip freeze > requirements.txt

# Git setup
git init
git config --global user.name "Jagades001ops"
git config --global user.email "your-email@example.com"
```

### .env file
```
GROQ_API_KEY=gsk_your-key-here
```

### .gitignore file
```
venv/
.env
__pycache__/
*.pyc
```

---

## 5. Project Structure

```
ai-workflow-engine/
├── engine/
│   ├── __init__.py          # makes engine a Python package
│   ├── schemas.py           # Pydantic data models (WorkflowPlan, WorkflowStep)
│   ├── intent_parser.py     # LLM call → structured WorkflowPlan
│   ├── nodes.py             # BaseNode, NodeResult — node architecture
│   └── execution_engine.py  # runs the workflow plan step by step (upcoming)
├── tests/                   # unit tests (upcoming)
├── main.py                  # entry point
├── .env                     # secrets (never committed)
├── .gitignore
└── requirements.txt
```

---

## 6. Components Built

### 6.1 `engine/schemas.py`
Defines the data contracts for the entire engine.

```python
from pydantic import BaseModel, Field
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
```

**Why it exists:** Every LLM response is validated against this schema. Wrong type, missing field, out-of-range value — Pydantic catches it immediately with a clear error.

---

### 6.2 `engine/intent_parser.py`
Takes a plain English request, calls the LLM, returns a validated WorkflowPlan.

```python
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

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)

    return WorkflowPlan(**data)
```

**Why it exists:** The entry point for all user requests. The LLM acts as a system designer — it figures out the steps, the order, and the data flow. Pydantic validates the result.

---

### 6.3 `engine/nodes.py`
Defines the base class every workflow node inherits from.

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any, Dict

class NodeResult(BaseModel):
    success: bool
    output_key: str
    output_value: Any
    error: str = None

class BaseNode(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, state: Dict[str, Any]) -> NodeResult:
        pass

    def handle_failure(self, error: Exception) -> NodeResult:
        return NodeResult(
            success=False,
            output_key="error",
            output_value=None,
            error=str(error)
        )
```

**Why it exists:** Every node in the pipeline shares the same interface — `execute(state)` returns a `NodeResult`. This is the Strategy pattern. The execution engine doesn't need to know what each node does, only that it has an `execute()` method.

---

### 6.4 `main.py`
Entry point for running the engine.

```python
from dotenv import load_dotenv
load_dotenv()

from engine.intent_parser import parse_intent

request = """I have a research paper PDF.
I want to summarize it, extract the key concepts,
and generate 5 quiz questions for studying."""

plan = parse_intent(request)

print(f"Goal: {plan.goal}")
print(f"Total steps: {plan.estimated_steps}\n")
for i, step in enumerate(plan.steps, 1):
    print(f"Step {i}: {step.name}")
    print(f"  What: {step.description}")
    print(f"  Reads: {step.input_key} → Writes: {step.output_key}")
```

---

## 7. Concepts Behind the Code

### Why separate planning from execution?
The LLM is good at reasoning about goals and designing steps. It is bad at reliably executing deterministic logic. By separating the two, you get the best of both — LLM intelligence for planning, Python reliability for execution.

### How does state passing work?
Each node reads from and writes to a shared `state` dictionary:
```python
state = {"document": "<raw text>"}
# Step 1 reads state["document"], writes state["text_content"]
# Step 2 reads state["text_content"], writes state["summary"]
# ...and so on
```
The `input_key` and `output_key` fields in the schema define this contract. The LLM designs the chain, the engine executes it.

### Why ABC and abstractmethod?
`BaseNode` is a blueprint — it cannot be instantiated directly. Any class that inherits from it MUST implement `execute()` or Python raises an error at class definition time. This enforces the contract across every node in the system.

### Why does json parsing have a fallback?
Even with strict instructions, LLMs occasionally wrap JSON in markdown code fences. The fallback strips them cleanly rather than crashing. In production you always handle the messy reality of LLM outputs.

---

## 8. Interview Answers

**"How do you manage dependencies in a Python project?"**
> Virtual environments — one per project. I pin dependencies in requirements.txt using pip freeze for full reproducibility.

**"How do you handle secrets and config?"**
> Environment variables via python-dotenv locally, .env in .gitignore, .env.example committed for documentation. In production, secrets are injected by the deployment environment.

**"How do you make LLM outputs reliable?"**
> Pydantic schemas for every LLM response — the schema is the contract. Combined with structured prompts and fallback JSON parsing, the system handles the messy reality of LLM outputs gracefully.

**"How do you design a multi-step AI system?"**
> Separate planning from execution. An Intent Parser uses the LLM to design the workflow — steps, order, data flow. The Execution Engine runs it deterministically. The LLM never touches execution logic.

**"What patterns did you use in your engine?"**
> Strategy pattern for nodes — common interface, different behaviour per node. Chain of Responsibility for the execution pipeline — each node processes state and passes it forward. Factory pattern upcoming for the Node Registry.

**"How does state flow between nodes?"**
> Shared state dictionary. Each node declares its input_key (what it reads) and output_key (what it writes). The execution engine passes state through every node in sequence — clean, observable, debuggable.

---

## 9. Changelog

| Date | Change |
|------|--------|
| Day 1 | Project setup, venv, git, .env |
| Day 1 | schemas.py — WorkflowStep, WorkflowPlan |
| Day 1 | intent_parser.py — LLM call with Groq, JSON parsing, Pydantic validation |
| Day 1 | main.py — entry point, pipeline output verified |
| Day 2 | nodes.py — BaseNode, NodeResult, ABC pattern |
| Day 2 | execution_engine.py — in progress |