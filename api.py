from dotenv import load_dotenv
load_dotenv()

import json
import queue
import threading
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from engine.intent_parser import parse_intent
from engine.execution_engine import ExecutionEngine
from engine.llm_nodes import build_node_for_step
from engine.database import SessionLocal, WorkflowRun, init_db, get_or_create_document, store_chunks
from engine.ingestion import ingest, IngestionError, ExtractionError
from engine.chunking import chunk_text
from engine.embeddings import embed_batch
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Workflow Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173",
                   "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    data = await file.read(26 * 1024 * 1024)  # read up to 26 MB to detect oversize
    try:
        result = ingest(
            data=data,
            filename=file.filename or "upload",
            content_type=file.content_type or "",
        )
    except IngestionError as exc:
        status = 413 if "25 MB" in str(exc) else 415
        raise HTTPException(status_code=status, detail=str(exc))
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Chunk + embed + store (deduped by content hash)
    import hashlib
    content_hash = hashlib.sha256(data).hexdigest()
    chunks = chunk_text(result.text)
    texts = [c.text for c in chunks]
    embeddings = embed_batch(texts) if texts else []

    db = SessionLocal()
    try:
        doc, created = get_or_create_document(
            db,
            filename=result.filename,
            content_type=result.content_type,
            size_bytes=result.size_bytes,
            page_count=result.page_count,
            char_count=result.char_count,
            content_hash=content_hash,
        )
        new_chunks = store_chunks(db, doc.id, chunks, embeddings) if created else 0
        db.commit()
        doc_id = doc.id
    finally:
        db.close()

    return {
        "document_id": doc_id,
        "created": created,
        "filename": result.filename,
        "content_type": result.content_type,
        "size_bytes": result.size_bytes,
        "page_count": result.page_count,
        "char_count": result.char_count,
        "chunk_count": len(chunks),
        "new_chunks": new_chunks,
        "ocr_pages": result.ocr_pages,
        "ocr_skipped_pages": result.ocr_skipped_pages,
    }


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

@app.post("/run/stream")
def run_workflow_stream(body: RunRequest):
    def event_generator():
        try:
            plan = parse_intent(body.request)
            step_metas = [
                {"name": s.name, "input_key": s.input_key, "output_key": s.output_key}
                for s in plan.steps
            ]
            yield f"data: {json.dumps({'type': 'plan', 'goal': plan.goal, 'steps': step_metas})}\n\n"

            engine = ExecutionEngine()
            for step in plan.steps:
                node = build_node_for_step(
                    name=step.name, description=step.description,
                    input_key=step.input_key, output_key=step.output_key
                )
                engine.register_node(step.name, node)

            result_queue = queue.Queue()
            container = {"state": None, "traces": [], "error": None}

            def on_step_start(step_name):
                result_queue.put(("step_start", step_name, None))

            def on_step_end(step_name, trace):
                result_queue.put(("step", step_name, trace))

            def run_engine():
                try:
                    state, traces = engine.run(
                        plan, {"document": body.document},
                        on_step_start=on_step_start,
                        on_step_end=on_step_end,
                    )
                    container["state"] = state
                    container["traces"] = traces
                except Exception as e:
                    container["error"] = str(e)
                finally:
                    result_queue.put(("done", None, None))

            thread = threading.Thread(target=run_engine, daemon=True)
            thread.start()

            while True:
                event_type, step_name, trace = result_queue.get()
                if event_type == "done":
                    break
                if event_type == "step_start":
                    yield f"data: {json.dumps({'type': 'step_start', 'name': step_name})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'step', 'name': step_name, 'success': trace.success, 'time_ms': round(trace.execution_time_ms or 0), 'tokens': (trace.input_tokens or 0) + (trace.output_tokens or 0), 'error': trace.error})}\n\n"

            thread.join()

            if container["error"]:
                yield f"data: {json.dumps({'type': 'error', 'message': container['error']})}\n\n"
                return

            final_state = container["state"]
            traces = container["traces"]
            output = {k: v for k, v in final_state.items() if k != "document"}
            total_tokens = sum(t.input_tokens + t.output_tokens for t in traces)
            total_time_ms = sum(t.execution_time_ms for t in traces)

            db = SessionLocal()
            try:
                run = WorkflowRun(
                    goal=plan.goal, request=body.request,
                    status="success", steps=plan.estimated_steps,
                    steps_json=json.dumps(step_metas),
                    summary=final_state.get("summary"),
                    output_json=json.dumps(output),
                    total_tokens=total_tokens,
                    total_time_ms=total_time_ms,
                )
                db.add(run)
                db.commit()
                db.refresh(run)
                run_id = run.id
            finally:
                db.close()

            yield f"data: {json.dumps({'type': 'done', 'run_id': run_id, 'goal': plan.goal, 'steps': step_metas, 'output': output, 'total_tokens': total_tokens, 'total_time_ms': total_time_ms})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
