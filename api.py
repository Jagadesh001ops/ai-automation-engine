from dotenv import load_dotenv
load_dotenv()

import hashlib
import json
import queue
import threading
from typing import List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.auth import get_current_user
from engine.database import (
    MAX_DOCS_PER_USER, Document, DocumentChunk, QuizAttempt,
    SessionLocal, WorkflowRun, get_or_create_document, init_db,
    store_chunks,
)
from engine.execution_engine import ExecutionEngine
from engine.ingestion import ExtractionError, IngestionError, ingest
from engine.intent_parser import parse_intent
from engine.llm_nodes import build_node_for_step

app = FastAPI(title="AI Workflow Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    document_id: Optional[int] = None   # if set, retrieval uses this doc's chunks
    difficulty: Optional[str] = "medium"  # easy | medium | hard (Day 15)

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

class QuizAnswerItem(BaseModel):
    question_idx: int
    question_text: str
    chosen_answer: str
    correct_answer: str

class QuizAttemptRequest(BaseModel):
    run_id: int
    answers: List[QuizAnswerItem]


# ─── Redis helper ─────────────────────────────────────────────────────────────

async def _enqueue(job_name: str, **kwargs):
    import os
    from arq.connections import RedisSettings, create_pool
    url = os.getenv("REDIS_URL", "redis://localhost:6379").removeprefix("redis://")
    host, _, port_str = url.partition(":")
    settings = RedisSettings(host=host, port=int(port_str) if port_str else 6379)
    redis = await create_pool(settings)
    await redis.enqueue_job(job_name, **kwargs)
    await redis.aclose()


# ─── Documents ────────────────────────────────────────────────────────────────

@app.post("/documents", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    data = await file.read(26 * 1024 * 1024)
    try:
        result = ingest(data=data, filename=file.filename or "upload",
                        content_type=file.content_type or "")
    except IngestionError as exc:
        raise HTTPException(status_code=413 if "25 MB" in str(exc) else 415, detail=str(exc))
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    content_hash = hashlib.sha256(data).hexdigest()

    db = SessionLocal()
    try:
        doc, created = get_or_create_document(
            db, filename=result.filename, content_type=result.content_type,
            size_bytes=result.size_bytes, page_count=result.page_count,
            char_count=result.char_count, content_hash=content_hash,
            user_id=user_id,
        )
        if created:
            doc.status = "processing"
        db.commit()
        doc_id, doc_status = doc.id, doc.status
    finally:
        db.close()

    if created:
        try:
            await _enqueue("ingest_document", document_id=doc_id, raw_bytes=data)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Redis unavailable (%s), processing sync", exc)
            from engine.chunking import chunk_text
            from engine.embeddings import embed_batch
            chunks = chunk_text(result.text)
            embeddings = embed_batch([c.text for c in chunks]) if chunks else []
            db2 = SessionLocal()
            try:
                store_chunks(db2, doc_id, chunks, embeddings)
                d = db2.query(Document).filter_by(id=doc_id).first()
                if d:
                    d.status = "ready"
                    d.page_count = result.page_count
                    d.char_count = result.char_count
                db2.commit()
                doc_status = "ready"
            finally:
                db2.close()

    return {"document_id": doc_id, "status": doc_status, "created": created,
            "filename": result.filename, "size_bytes": result.size_bytes,
            "quota_used": _doc_count(user_id), "quota_max": MAX_DOCS_PER_USER}


def _doc_count(user_id: str) -> int:
    db = SessionLocal()
    try:
        return db.query(Document).filter_by(user_id=user_id).count()
    finally:
        db.close()


@app.get("/documents")
def list_documents(user_id: str = Depends(get_current_user)):
    db = SessionLocal()
    try:
        docs = (db.query(Document)
                  .filter_by(user_id=user_id)
                  .order_by(Document.created_at.desc())
                  .all())
        return [_doc_dict(d) for d in docs]
    finally:
        db.close()


@app.get("/documents/{document_id}")
def get_document(document_id: int, user_id: str = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter_by(id=document_id, user_id=user_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return _doc_dict(doc)
    finally:
        db.close()


@app.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, user_id: str = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter_by(id=document_id, user_id=user_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        db.query(DocumentChunk).filter_by(document_id=document_id).delete()
        db.delete(doc)
        db.commit()
    finally:
        db.close()


def _doc_dict(d: Document) -> dict:
    return {
        "document_id": d.id, "filename": d.filename,
        "content_type": d.content_type, "size_bytes": d.size_bytes,
        "page_count": d.page_count, "char_count": d.char_count,
        "status": d.status, "error_message": d.error_message,
        "created_at": d.created_at,
    }


# ─── Search (Day 15) ──────────────────────────────────────────────────────────

@app.get("/search")
def search_library(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=10, ge=1, le=50),
    user_id: str = Depends(get_current_user),
):
    """Semantic search across all of the user's ready documents."""
    from engine.embeddings import embed
    from engine.retrieval_node import retrieve_chunks

    # Collect document IDs owned by this user
    db = SessionLocal()
    try:
        doc_ids = [
            d.id for d in
            db.query(Document.id).filter_by(user_id=user_id, status="ready").all()
        ]
    finally:
        db.close()

    if not doc_ids:
        return {"query": q, "results": []}

    # For multi-doc search, run one query per doc and merge by score
    from engine.retrieval_node import retrieve_chunks
    all_chunks: list[dict] = []
    for doc_id in doc_ids:
        all_chunks.extend(retrieve_chunks(query=q, document_id=doc_id, top_k=top_k))

    all_chunks.sort(key=lambda c: c["score"])
    return {"query": q, "results": all_chunks[:top_k]}


# ─── Workflow runs ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/runs")
def get_runs(user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    runs = (db.query(WorkflowRun)
              .filter_by(user_id=user_id)
              .order_by(WorkflowRun.created_at.desc())
              .all())
    return [{"id": r.id, "goal": r.goal, "status": r.status, "steps": r.steps,
             "total_tokens": r.total_tokens, "total_time_ms": r.total_time_ms,
             "created_at": r.created_at} for r in runs]


@app.post("/run", response_model=RunResponse)
def run_workflow(body: RunRequest, user_id: str = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    plan = parse_intent(body.request)
    engine = _build_engine(plan, body)
    initial_state = {"document": body.document, "query": body.request}
    final_state, traces = engine.run(plan, initial_state)

    step_results = [{"name": s.name, "input_key": s.input_key, "output_key": s.output_key}
                    for s in plan.steps]
    output = {k: v for k, v in final_state.items() if k not in ("document", "query")}
    total_tokens = sum(t.input_tokens + t.output_tokens for t in traces)
    total_time_ms = sum(t.execution_time_ms for t in traces)

    run = WorkflowRun(
        user_id=user_id, goal=plan.goal, request=body.request,
        status="success", steps=plan.estimated_steps,
        steps_json=json.dumps(step_results), summary=final_state.get("summary"),
        output_json=json.dumps(output, default=str),
        total_tokens=total_tokens, total_time_ms=total_time_ms,
    )
    db.add(run); db.commit(); db.refresh(run)

    return RunResponse(run_id=run.id, goal=plan.goal,
                       steps=[StepResult(**s) for s in step_results],
                       output=output, total_tokens=total_tokens, total_time_ms=total_time_ms)


@app.post("/run/stream")
def run_workflow_stream(body: RunRequest, user_id: str = Depends(get_current_user)):
    def event_generator():
        try:
            plan = parse_intent(body.request)
            step_metas = [{"name": s.name, "input_key": s.input_key, "output_key": s.output_key}
                          for s in plan.steps]
            yield f"data: {json.dumps({'type': 'plan', 'goal': plan.goal, 'steps': step_metas, 'scope': plan.scope, 'too_broad': plan.too_broad})}\n\n"

            if plan.too_broad:
                yield f"data: {json.dumps({'type': 'error', 'message': plan.too_broad_reason or 'Request too broad'})}\n\n"
                return

            engine = _build_engine(plan, body)
            q: queue.Queue = queue.Queue()
            container: dict = {"state": None, "traces": [], "error": None}

            def _start(name): q.put(("step_start", name, None))
            def _end(name, trace): q.put(("step", name, trace))

            def _run():
                try:
                    state, traces = engine.run(
                        plan, {"document": body.document, "query": body.request},
                        on_step_start=_start, on_step_end=_end,
                    )
                    container["state"] = state; container["traces"] = traces
                except Exception as e:
                    container["error"] = str(e)
                finally:
                    q.put(("done", None, None))

            threading.Thread(target=_run, daemon=True).start()

            while True:
                ev, name, trace = q.get()
                if ev == "done": break
                if ev == "step_start":
                    yield f"data: {json.dumps({'type': 'step_start', 'name': name})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'step', 'name': name, 'success': trace.success, 'time_ms': round(trace.execution_time_ms or 0), 'tokens': (trace.input_tokens or 0)+(trace.output_tokens or 0), 'error': trace.error})}\n\n"

            if container["error"]:
                yield f"data: {json.dumps({'type': 'error', 'message': container['error']})}\n\n"
                return

            final_state = container["state"]
            traces = container["traces"]
            output = {k: v for k, v in final_state.items() if k not in ("document", "query")}
            total_tokens = sum(t.input_tokens + t.output_tokens for t in traces)
            total_time_ms = sum(t.execution_time_ms for t in traces)

            db = SessionLocal()
            try:
                run = WorkflowRun(
                    user_id=user_id, goal=plan.goal, request=body.request,
                    status="success", steps=plan.estimated_steps,
                    steps_json=json.dumps(step_metas),
                    summary=final_state.get("summary"),
                    output_json=json.dumps(output, default=str),
                    total_tokens=total_tokens, total_time_ms=total_time_ms,
                )
                db.add(run); db.commit(); db.refresh(run)
                run_id = run.id
            finally:
                db.close()

            yield f"data: {json.dumps({'type': 'done', 'run_id': run_id, 'goal': plan.goal, 'steps': step_metas, 'output': output, 'total_tokens': total_tokens, 'total_time_ms': total_time_ms}, default=str)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/runs/{run_id}")
def get_run(run_id: int, user_id: str = Depends(get_current_user),
            db: Session = Depends(get_db)):
    run = db.query(WorkflowRun).filter_by(id=run_id, user_id=user_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run.id, "goal": run.goal, "status": run.status,
            "steps": json.loads(run.steps_json) if run.steps_json else [],
            "total_tokens": run.total_tokens, "total_time_ms": run.total_time_ms,
            "output": json.loads(run.output_json) if run.output_json else {},
            "created_at": run.created_at}


# ─── Quiz attempts (Day 13) ───────────────────────────────────────────────────

@app.post("/quiz/attempt")
def submit_quiz_attempt(
    body: QuizAttemptRequest,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record the user's answers for a quiz and return the score."""
    attempts = []
    correct_count = 0
    for item in body.answers:
        is_correct = item.chosen_answer.upper() == item.correct_answer.upper()
        if is_correct:
            correct_count += 1
        attempt = QuizAttempt(
            user_id=user_id, run_id=body.run_id,
            question_idx=item.question_idx, question_text=item.question_text,
            chosen_answer=item.chosen_answer.upper(),
            correct_answer=item.correct_answer.upper(),
            is_correct=int(is_correct),
        )
        db.add(attempt)
        attempts.append(attempt)
    db.commit()
    total = len(body.answers)
    return {
        "run_id": body.run_id,
        "score": correct_count,
        "total": total,
        "pct": round(correct_count / total * 100) if total else 0,
    }


@app.get("/quiz/history")
def quiz_history(user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    attempts = (db.query(QuizAttempt)
                  .filter_by(user_id=user_id)
                  .order_by(QuizAttempt.created_at.desc())
                  .limit(200).all())
    return [
        {"run_id": a.run_id, "question_idx": a.question_idx,
         "chosen_answer": a.chosen_answer, "correct_answer": a.correct_answer,
         "is_correct": bool(a.is_correct), "created_at": a.created_at}
        for a in attempts
    ]


# ─── Exports (Days 16–17) ─────────────────────────────────────────────────────

@app.get("/runs/{run_id}/export/pdf")
def export_pdf(run_id: int, user_id: str = Depends(get_current_user),
               db: Session = Depends(get_db)):
    run = db.query(WorkflowRun).filter_by(id=run_id, user_id=user_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    from engine.export import generate_pdf
    pdf_bytes = generate_pdf(run)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="study-kit-{run_id}.pdf"'})


@app.get("/runs/{run_id}/export/anki")
def export_anki(run_id: int, user_id: str = Depends(get_current_user),
                db: Session = Depends(get_db)):
    run = db.query(WorkflowRun).filter_by(id=run_id, user_id=user_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    from engine.export import generate_anki
    apkg_bytes = generate_anki(run)
    return Response(content=apkg_bytes, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="study-kit-{run_id}.apkg"'})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_engine(plan, body: RunRequest) -> ExecutionEngine:
    """Build an ExecutionEngine with nodes for *plan*, injecting difficulty."""
    eng = ExecutionEngine()
    for step in plan.steps:
        node = build_node_for_step(
            name=step.name, description=step.description,
            input_key=step.input_key, output_key=step.output_key,
        )
        # Inject difficulty into quiz nodes (Day 15)
        if hasattr(node, "_difficulty"):
            node._difficulty = body.difficulty or "medium"
        eng.register_node(step.name, node)
    return eng
