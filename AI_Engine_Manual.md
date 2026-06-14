# AI Workflow Engine — Project Manual

> Last updated: Phase 3 complete — FastAPI + PostgreSQL working

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
**Stack:** Python 3.12, Groq API (llama-3.3-70b-versatile), Pydantic, FastAPI, PostgreSQL, SQLAlchemy
**Goal:** Build a production-ready AI orchestration system that transforms natural language requests into structured, executable workflows — and use it to learn every skill needed for an AI Engineer role.

---

## 2. What You Are Building

A system that takes a plain English request like:

> "I have a research paper. Summarize it, extract key concepts, and generate quiz questions."

And turns it into a structured, executable pipeline exposed as a REST API:

```
POST /run
     ↓
document + request
     ↓
Intent Parser        ← LLM plans the workflow
     ↓
WorkflowPlan         ← Pydantic-validated schema
     ↓
build_node_for_step  ← routes each step to the right node class
     ↓
ExecutionEngine      ← runs each step in order
     ↓
State Dictionary     ← passes data between nodes
     ↓
PostgreSQL           ← persists every run
     ↓
JSON Response        ← structured output returned to caller
```

### Core Philosophy
- **Separate planning from execution** — LLM designs the pipeline, engine runs it
- **Use as little AI as possible** — only LLM calls where needed, deterministic logic elsewhere
- **Structured state transfer** — all data between nodes is typed and validated
- **Semi-dynamic routing** — specialist nodes for known jobs, generic fallback for unknown steps
- **Persistence** — every run saved to PostgreSQL for history and debugging

---

## 3. Skills Learned

### Phase 1 — Foundations

| Topic | What You Learned |
|-------|-----------------|
| Virtual environments | `py -3.12 -m venv venv`, activate, pip install, requirements.txt |
| Git | init, add, commit, push, .gitignore, global user config |
| Environment variables | .env files, python-dotenv, never commit secrets |
| Groq SDK | chat.completions.create, system prompt, messages array, response parsing |
| Prompt engineering | Role, few-shot, chain of thought, positive instructions, XML delimiters |
| Pydantic | BaseModel, Field, ValidationError, nested models, type enforcement |

### Phase 2 — AI System Design (complete)

| Topic | What You Learned |
|-------|-----------------|
| Node architecture | BaseNode, ABC, abstractmethod, NodeResult |
| Strategy pattern | Common interface, different behaviour per node |
| State management | Shared Dict passed through pipeline, input_key/output_key chaining |
| Chain of Responsibility | Each node processes state and passes it forward |
| Factory/Registry pattern | Registry maps step names to node objects at runtime |
| Semi-dynamic routing | Keyword matching routes to specialist nodes, falls back to generic |
| Inheritance hierarchy | LLMNode as base, specialist nodes inherit and override only the prompt |

### Phase 3 — Backend + Database (complete)

| Topic | What You Learned |
|-------|-----------------|
| FastAPI | app setup, route decorators, request/response models, auto docs |
| REST conventions | GET for reading, POST for creating/triggering, consistent response shapes |
| Pydantic in FastAPI | RunRequest, RunResponse, StepResult — request/response validation |
| SQLAlchemy ORM | Base, Column types, SessionLocal, declarative_base |
| Database dependency | get_db() with yield — opens and closes session per request |
| PostgreSQL | CREATE DATABASE, ALTER USER, psql client, pg_hba.conf |
| Run persistence | WorkflowRun model, db.add(), db.commit(), db.refresh() |
| Health endpoint | /health for infrastructure monitoring, load balancers, Docker |

---

## 4. Project Setup

### Prerequisites
- Python 3.12
- Groq API key (free at console.groq.com)
- PostgreSQL 16 or 18
- Git

### First-time setup
```bash
mkdir ai-workflow-engine
cd ai-workflow-engine
py -3.12 -m venv venv
venv\Scripts\activate
pip install groq pydantic python-dotenv fastapi uvicorn sqlalchemy psycopg2-binary
pip freeze > requirements.txt
git init
git config --global user.name "Jagades001ops"
git config --global user.email "your-email@example.com"
```

### PostgreSQL setup (Windows)
```bash
# Add to PATH: C:\Program Files\PostgreSQL\16\bin
psql -U postgres -h 127.0.0.1
```
Inside psql:
```sql
ALTER USER postgres PASSWORD 'postgres123';
CREATE DATABASE workflow_engine;
\q
```

### .env file
```
GROQ_API_KEY=gsk_your-key-here
DATABASE_URL=postgresql://postgres:postgres123@localhost:5432/workflow_engine
```

### .gitignore file
```
venv/
.env
__pycache__/
*.pyc
```

### Running the API
```bash
uvicorn api:app --reload
```
Then open: `http://127.0.0.1:8000/docs`

---

## 5. Project Structure

```
ai-workflow-engine/
├── engine/
│   ├── __init__.py             # makes engine a Python package
│   ├── schemas.py              # Pydantic data models
│   ├── intent_parser.py        # LLM call → structured WorkflowPlan
│   ├── nodes.py                # BaseNode, NodeResult — node architecture
│   ├── llm_nodes.py            # LLMNode, specialist nodes, router
│   ├── execution_engine.py     # ExecutionEngine — registry + run loop
│   └── database.py             # SQLAlchemy models, engine, session
├── tests/                      # unit tests (upcoming)
├── api.py                      # FastAPI app — routes, request/response schemas
├── main.py                     # CLI entry point
├── MANUAL.md                   # this file
├── .env                        # secrets (never committed)
├── .gitignore
└── requirements.txt
```

---

## 6. Components Built

### 6.1 `engine/schemas.py`
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

---

### 6.2 `engine/intent_parser.py`
```python
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from .schemas import WorkflowPlan
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

---

### 6.3 `engine/nodes.py`
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

---

### 6.4 `engine/llm_nodes.py`
```python
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from typing import Any, Dict
from .nodes import BaseNode, NodeResult

client = Groq()

class LLMNode(BaseNode):
    def __init__(self, name: str, description: str, input_key: str, output_key: str):
        super().__init__(name=name, description=description)
        self.input_key = input_key
        self.output_key = output_key

    def execute(self, state: Dict[str, Any]) -> NodeResult:
        text = state.get(self.input_key)
        if not text:
            return self.handle_failure(ValueError(f"'{self.input_key}' not found in state"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": f"You are an expert assistant. Your job: {self.description}. Be concise and clear."},
                {"role": "user", "content": str(text)}
            ]
        )
        return NodeResult(
            success=True,
            output_key=self.output_key,
            output_value=response.choices[0].message.content
        )

class SummarizeNode(LLMNode):
    def __init__(self, name: str, input_key: str, output_key: str):
        super().__init__(
            name=name,
            description="Summarize the given text into a clear, concise paragraph capturing only the main ideas.",
            input_key=input_key, output_key=output_key
        )

class ExtractConceptsNode(LLMNode):
    def __init__(self, name: str, input_key: str, output_key: str):
        super().__init__(
            name=name,
            description="Extract the 5 most important concepts from the text. Return a numbered list, one concept per line with a brief explanation.",
            input_key=input_key, output_key=output_key
        )

class GenerateQuizNode(LLMNode):
    def __init__(self, name: str, input_key: str, output_key: str):
        super().__init__(
            name=name,
            description="Create 5 multiple choice questions based on the given content. Each question must have 4 options (A, B, C, D) and clearly mark the correct answer.",
            input_key=input_key, output_key=output_key
        )

SPECIALIST_NODES = {
    "summarize": SummarizeNode,
    "extract":   ExtractConceptsNode,
    "quiz":      GenerateQuizNode,
    "generate":  GenerateQuizNode,
}

def build_node_for_step(name: str, description: str,
                         input_key: str, output_key: str) -> LLMNode:
    for keyword, NodeClass in SPECIALIST_NODES.items():
        if keyword in name.lower():
            return NodeClass(name=name, input_key=input_key, output_key=output_key)
    print(f"  → No specialist for '{name}', using generic LLMNode")
    return LLMNode(name=name, description=description, input_key=input_key, output_key=output_key)
```

---

### 6.5 `engine/execution_engine.py`
```python
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
            node = self.registry.get(step.name)
            if node is None:
                print(f"  ✗ No node registered for '{step.name}' — skipping")
                continue
            try:
                result: NodeResult = node.execute(state)
            except Exception as e:
                result = node.handle_failure(e)
            if result.success:
                state[result.output_key] = result.output_value
                print(f"  ✓ {step.name} → wrote '{result.output_key}' to state")
            else:
                print(f"  ✗ {step.name} failed: {result.error}")
                break
        return state
```

---

### 6.6 `engine/database.py`
```python
import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/workflow_engine")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class WorkflowRun(Base):
    __tablename__ = "runs"
    id         = Column(Integer, primary_key=True, index=True)
    goal       = Column(String)
    request    = Column(Text)
    status     = Column(String, default="success")
    steps      = Column(Integer)
    summary    = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
```

---

### 6.7 `api.py`
```python
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from engine.intent_parser import parse_intent
from engine.execution_engine import ExecutionEngine
from engine.llm_nodes import build_node_for_step
from engine.database import SessionLocal, WorkflowRun, init_db

app = FastAPI(title="AI Workflow Engine", version="1.0.0")
init_db()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class RunRequest(BaseModel):
    document: str
    request: str

class StepResult(BaseModel):
    name: str
    input_key: str
    output_key: str

class RunResponse(BaseModel):
    run_id: int
    goal: str
    steps: list[StepResult]
    output: dict

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/runs")
def get_runs(db: Session = Depends(get_db)):
    runs = db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).all()
    return [
        {"id": r.id, "goal": r.goal, "status": r.status,
         "steps": r.steps, "created_at": r.created_at}
        for r in runs
    ]

@app.post("/run", response_model=RunResponse)
def run_workflow(body: RunRequest, db: Session = Depends(get_db)):
    plan = parse_intent(body.request)
    engine = ExecutionEngine()
    for step in plan.steps:
        node = build_node_for_step(
            name=step.name, description=step.description,
            input_key=step.input_key, output_key=step.output_key
        )
        engine.register_node(step.name, node)
    initial_state = {"document": body.document}
    final_state = engine.run(plan, initial_state)
    run = WorkflowRun(
        goal=plan.goal, request=body.request,
        status="success", steps=plan.estimated_steps,
        summary=final_state.get("summary")
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return RunResponse(
        run_id=run.id, goal=plan.goal,
        steps=[StepResult(name=s.name, input_key=s.input_key, output_key=s.output_key) for s in plan.steps],
        output={k: v for k, v in final_state.items() if k != "document"}
    )
```

---

## 7. Concepts Behind the Code

### Why separate planning from execution?
The LLM reasons about goals and designs steps. Python handles deterministic execution. Combining both gives you LLM intelligence for planning and Python reliability for running.

### How does state passing work?
Shared `state` dictionary flows through every node:
```python
state = {"document": "<raw text>"}
# Step 1 reads state["document"], writes state["summary"]
# Step 2 reads state["summary"], writes state["key_concepts"]
# Step 3 reads state["key_concepts"], writes state["quiz_questions"]
```

### What is the semi-dynamic routing pattern?
`build_node_for_step()` checks if the step name contains a known keyword and routes to a specialist node. If no keyword matches, it falls back to the generic `LLMNode` using the step description as the system prompt.

### Why use ABC for BaseNode?
It enforces the contract at class definition time. Any node missing `execute()` fails immediately — not at runtime.

### What is the SQLAlchemy session pattern?
`get_db()` uses Python's `yield` to open a session before the request and close it after — even if an error occurs. FastAPI's `Depends()` injects it into route functions automatically.

### Why does init_db() run on startup?
`Base.metadata.create_all()` creates all tables defined as SQLAlchemy models if they don't exist yet. Safe to run multiple times — it never drops existing tables.

### What is the health endpoint for?
Infrastructure monitoring — Docker health checks, load balancers, and uptime monitoring tools all ping `/health` to verify the service is alive. Returns 200 if up, used to route or alert automatically.

### POST vs GET
POST creates or triggers something — state changes on the server. GET reads existing data — nothing changes. Your API uses POST for running workflows and GET for reading history.

---

## 8. Interview Answers

**"How do you manage dependencies?"**
> Virtual environments per project, pinned in requirements.txt via pip freeze.

**"How do you handle secrets?"**
> Environment variables via python-dotenv locally, .env in .gitignore. In production, injected by the deployment environment.

**"How do you make LLM outputs reliable?"**
> Pydantic schemas for every response, structured prompts, fallback JSON parsing for markdown-wrapped responses.

**"How do you design a multi-step AI system?"**
> Separate planning from execution. Intent Parser uses LLM to design the workflow. Execution Engine runs it deterministically.

**"What patterns did you use?"**
> Strategy pattern for nodes. Chain of Responsibility for the pipeline. Registry/Factory for runtime node lookup. Inheritance hierarchy to avoid duplicating execute() logic.

**"How does state flow between nodes?"**
> Shared state dictionary. Each node declares input_key and output_key. Engine passes state through every node in sequence.

**"How do you expose AI as an API?"**
> FastAPI with Pydantic request/response models. POST /run accepts document and request, returns structured JSON. GET /runs returns history. All validated by Pydantic automatically.

**"Have you worked with SQL in an AI project?"**
> Yes — SQLAlchemy ORM with PostgreSQL. Every workflow run is persisted to a runs table with goal, status, steps, summary, and timestamp. Used db.add(), db.commit() for writes and db.query() for reads.

**"What is the health endpoint for?"**
> Infrastructure monitoring — Docker health checks, load balancers, and uptime tools ping /health to verify the service is alive. One of the first things you add when thinking about production deployment.

**"What is the semi-dynamic routing pattern?"**
> A keyword router checks the LLM-generated step name against known specialists. Matched steps get a tuned system prompt. Unmatched steps fall back to a generic node using the step description as its prompt.

---

## 9. Changelog

| Date | Change |
|------|--------|
| Day 1 | Project setup — venv (Python 3.12), git, .env, .gitignore, requirements.txt |
| Day 1 | schemas.py — WorkflowStep and WorkflowPlan Pydantic models |
| Day 1 | intent_parser.py — Groq LLM call, JSON parsing with fallback, Pydantic validation |
| Day 1 | main.py — entry point, pipeline output verified with correct state chaining |
| Day 1 | Verified: 4-step pipeline with clean state chaining |
| Day 2 | nodes.py — BaseNode (ABC), NodeResult, handle_failure |
| Day 2 | execution_engine.py — ExecutionEngine with registry dict and run loop |
| Day 2 | llm_nodes.py — LLMNode base, specialist nodes, build_node_for_step router |
| Day 2 | main.py — full end-to-end pipeline wired and verified |
| Day 2 | Verified: full run — 3 nodes auto-routed, pipeline executed, output generated |
| Day 3 | database.py — SQLAlchemy WorkflowRun model, init_db, SessionLocal |
| Day 3 | api.py — FastAPI app, POST /run, GET /runs, GET /health, DB persistence |
| Day 3 | PostgreSQL setup — workflow_engine database created, password configured |
| Day 3 | Verified: POST /run returns run_id + output, GET /runs returns persisted history |

---

## Next Session

Pick up from here:
- Phase 4: Observability — token tracking per node, execution time logging
- Phase 4: Error handling improvements — persist failed runs with error message
- Phase 4: Docker — containerize the app + PostgreSQL together
- Phase 4: Deploy to VPS (DigitalOcean / Hetzner) behind HTTPS
