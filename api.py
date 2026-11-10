from dotenv import load_dotenv
load_dotenv()

import json
import os
import contextlib
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from engine.intent_parser import parse_intent
from engine.execution_engine import ExecutionEngine
from engine.llm_nodes import build_node_for_step
from engine.database import SessionLocal, WorkflowRun, init_db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Workflow Engine", version="1.0.0")

# ─── Maintenance mode ─────────────────────────────────────────────────────────
# Set MAINTENANCE_MODE=1 in environment to block all traffic with a 503.
# /health and /metrics are always exempt so load balancers stay informed.
_MAINTENANCE = os.getenv("MAINTENANCE_MODE", "").lower() in ("1", "true", "yes")

@app.middleware("http")
async def maintenance_gate(request: Request, call_next):
    if _MAINTENANCE and request.url.path not in ("/health", "/metrics"):
        return JSONResponse(
            {"status": "maintenance", "message": "Service temporarily unavailable. Check back soon."},
            status_code=503,
        )
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Prometheus metrics ───────────────────────────────────────────────────────
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

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
    total_tokens: int
    total_time_ms: float


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Deep health check: verifies DB and Redis are reachable."""
    db_ok = False
    redis_ok = False

    with contextlib.suppress(Exception):
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True

    with contextlib.suppress(Exception):
        import redis as _redis
        r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), socket_connect_timeout=2)
        r.ping()
        redis_ok = True

    overall = "ok" if (db_ok and redis_ok) else "degraded"
    return JSONResponse(
        {"status": overall, "db": "ok" if db_ok else "error", "redis": "ok" if redis_ok else "error"},
        status_code=200 if overall == "ok" else 503,
    )


@app.get("/runs")
def get_runs(db: Session = Depends(get_db)):
    runs = db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "goal": r.goal,
            "status": r.status,
            "steps": r.steps,
            "total_tokens": r.total_tokens,
            "total_time_ms": r.total_time_ms,
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
    final_state, traces = engine.run(plan, initial_state)

    # Step 4: persist run to database
    step_results = [
        {"name": s.name, "input_key": s.input_key, "output_key": s.output_key}
        for s in plan.steps
    ]
    output = {k: v for k, v in final_state.items() if k != "document"}
    total_tokens = sum(t.input_tokens + t.output_tokens for t in traces)
    total_time_ms = sum(t.execution_time_ms for t in traces)

    run = WorkflowRun(
        goal=plan.goal,
        request=body.request,
        status="success",
        steps=plan.estimated_steps,
        steps_json=json.dumps(step_results),
        summary=final_state.get("summary"),
        output_json=json.dumps(output),
        total_tokens=total_tokens,
        total_time_ms=total_time_ms
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Step 5: return response
    return RunResponse(
        run_id=run.id,
        goal=plan.goal,
        steps=[StepResult(**s) for s in step_results],
        output=output,
        total_tokens=total_tokens,
        total_time_ms=total_time_ms
    )

@app.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run.id,
        "goal": run.goal,
        "status": run.status,
        "steps": json.loads(run.steps_json) if run.steps_json else [],
        "total_tokens": run.total_tokens,
        "total_time_ms": run.total_time_ms,
        "output": json.loads(run.output_json) if run.output_json else {},
        "created_at": run.created_at
    }
