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

# Create tables on startup
init_db()


# ─── DB dependency ────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Request / Response schemas ───────────────────────────────────────────────

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


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/runs")
def get_runs(db: Session = Depends(get_db)):
    runs = db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "goal": r.goal,
            "status": r.status,
            "steps": r.steps,
            "created_at": r.created_at
        }
        for r in runs
    ]


@app.post("/run", response_model=RunResponse)
def run_workflow(body: RunRequest, db: Session = Depends(get_db)):
    # Step 1: parse intent
    plan = parse_intent(body.request)

    # Step 2: build and register nodes
    engine = ExecutionEngine()
    for step in plan.steps:
        node = build_node_for_step(
            name=step.name,
            description=step.description,
            input_key=step.input_key,
            output_key=step.output_key
        )
        engine.register_node(step.name, node)

    # Step 3: run pipeline
    initial_state = {"document": body.document}
    final_state = engine.run(plan, initial_state)

    # Step 4: persist run to database
    run = WorkflowRun(
        goal=plan.goal,
        request=body.request,
        status="success",
        steps=plan.estimated_steps,
        summary=final_state.get("summary")
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Step 5: return response
    return RunResponse(
        run_id=run.id,
        goal=plan.goal,
        steps=[
            StepResult(
                name=s.name,
                input_key=s.input_key,
                output_key=s.output_key
            )
            for s in plan.steps
        ],
        output={
            k: v for k, v in final_state.items()
            if k != "document"
        }
    )