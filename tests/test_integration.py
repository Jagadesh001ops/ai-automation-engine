"""
Integration tests — TestClient + live database, no DB mocking.

What's covered:
  - Document lifecycle: upload → list → get → delete
  - Duplicate detection: same file twice → same document_id, created=False
  - Quota enforcement: exceed MAX_DOCS_PER_USER → 429
  - Run lifecycle: POST /run (LLM mocked) → persisted → GET /runs/{id}
  - Quiz lifecycle: POST /quiz/attempt → score → GET /quiz/history
  - Export stubs: GET /runs/{id}/export/pdf and /anki return bytes for valid run
  - Search empty: GET /search returns [] when no docs exist

Runs against whatever DATABASE_URL is configured (Postgres in CI, local
Postgres dev env).  Skipped when DATABASE_URL is not set (developer hasn't
wired a local DB yet).

Mocked helpers (not what we're testing here):
  - LLM: parse_intent, build_node_for_step — no real API calls
  - Redis: api._enqueue — instant fail so sync fallback runs; embed_batch
    returns [] so sentence-transformers model is never loaded
  - Exports: generate_pdf/generate_anki return dummy bytes (export.py has
    its own unit tests in test_export.py)
"""
import io
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api import app
from engine.database import Base, Document, QuizAttempt, SessionLocal, WorkflowRun
from engine.database import engine as _db_engine

# ── Skip all tests in this module when no real DB is configured ───────────────
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — integration tests require a real database",
)

# ── Shared TestClient ─────────────────────────────────────────────────────────
client = TestClient(app, raise_server_exceptions=False)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def create_tables():
    """Ensure all tables exist and patch infrastructure before any test runs."""
    Base.metadata.create_all(_db_engine)
    # Patch Redis enqueue (instant fail → sync fallback) + embed_batch (skip
    # sentence-transformers model load) for the entire module.
    with (
        patch("api._enqueue", side_effect=Exception("no redis in tests")),
        patch("engine.embeddings.embed_batch", return_value=[]),
    ):
        yield


@pytest.fixture(autouse=True)
def clean_tables():
    """Wipe test data between tests so each is independent."""
    yield
    db = SessionLocal()
    try:
        db.query(QuizAttempt).filter_by(user_id="dev-user").delete()
        db.query(WorkflowRun).filter_by(user_id="dev-user").delete()
        db.query(Document).filter_by(user_id="dev-user").delete()
        db.commit()
    finally:
        db.close()


def _txt_file(name: str = "sample.txt", content: str = "Hello, integration test.") -> dict:
    """Build a multipart file dict for TestClient."""
    return {"file": (name, io.BytesIO(content.encode()), "text/plain")}


def _make_plan():
    from engine.schemas import WorkflowPlan, WorkflowStep
    step = WorkflowStep(
        name="summarize",
        description="Summarise",
        input_key="document",
        output_key="summary",
    )
    return WorkflowPlan(
        goal="Summarise",
        scope="single_document",
        steps=[step],
        estimated_steps=1,
        too_broad=False,
    )


def _fake_node():
    node = MagicMock()
    node.execute.return_value = MagicMock(
        success=True, output_key="summary", output_value="Integration summary.",
        input_tokens=5, output_tokens=10, execution_time_ms=20, error=None,
    )
    return node


def _post_run():
    """Helper: POST /run with LLM mocked, return parsed JSON body."""
    with (
        patch("api.parse_intent", return_value=_make_plan()),
        patch("api.build_node_for_step", return_value=_fake_node()),
    ):
        res = client.post("/run", json={"document": "Some text.", "request": "summarise"})
    assert res.status_code == 200, res.text
    return res.json()


# ── Document lifecycle ────────────────────────────────────────────────────────

def test_upload_creates_document():
    res = client.post("/documents", files=_txt_file())
    assert res.status_code == 202
    body = res.json()
    assert "document_id" in body
    assert isinstance(body["document_id"], int)
    assert body["filename"] == "sample.txt"
    assert body["created"] is True
    assert body["quota_used"] == 1


def test_list_documents_includes_upload():
    client.post("/documents", files=_txt_file())
    res = client.get("/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 1
    assert docs[0]["filename"] == "sample.txt"


def test_get_document_by_id():
    upload = client.post("/documents", files=_txt_file())
    doc_id = upload.json()["document_id"]
    res = client.get(f"/documents/{doc_id}")
    assert res.status_code == 200
    assert res.json()["document_id"] == doc_id


def test_get_document_not_found():
    res = client.get("/documents/999999")
    assert res.status_code == 404


def test_delete_document():
    upload = client.post("/documents", files=_txt_file())
    doc_id = upload.json()["document_id"]

    del_res = client.delete(f"/documents/{doc_id}")
    assert del_res.status_code == 204

    get_res = client.get(f"/documents/{doc_id}")
    assert get_res.status_code == 404


def test_delete_nonexistent_document():
    res = client.delete("/documents/999999")
    assert res.status_code == 404


def test_list_empty_after_delete():
    upload = client.post("/documents", files=_txt_file())
    doc_id = upload.json()["document_id"]
    client.delete(f"/documents/{doc_id}")
    res = client.get("/documents")
    assert res.json() == []


# ── Duplicate detection ───────────────────────────────────────────────────────

def test_duplicate_upload_returns_same_id():
    r1 = client.post("/documents", files=_txt_file(content="Unique content abc123."))
    r2 = client.post("/documents", files=_txt_file(content="Unique content abc123."))
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r1.json()["document_id"] == r2.json()["document_id"]
    assert r2.json()["created"] is False


def test_different_content_different_id():
    r1 = client.post("/documents", files=_txt_file(content="Content A"))
    r2 = client.post("/documents", files=_txt_file("b.txt", content="Content B"))
    assert r1.json()["document_id"] != r2.json()["document_id"]


# ── Quota enforcement ─────────────────────────────────────────────────────────

def test_quota_exceeded_returns_429():
    """Upload MAX_DOCS_PER_USER docs, then confirm the 11th is rejected."""
    from engine.database import MAX_DOCS_PER_USER
    for i in range(MAX_DOCS_PER_USER):
        res = client.post("/documents", files=_txt_file(f"doc{i}.txt", f"quota filler {i}"))
        assert res.status_code == 202, f"upload {i} failed: {res.text}"

    res = client.post("/documents", files=_txt_file("overflow.txt", "this should be blocked"))
    assert res.status_code == 429
    assert "quota" in res.json().get("detail", "").lower()


# ── Run lifecycle ─────────────────────────────────────────────────────────────

def test_run_persisted_in_db():
    body = _post_run()
    run_id = body["run_id"]

    db = SessionLocal()
    try:
        run = db.query(WorkflowRun).filter_by(id=run_id).first()
        assert run is not None
        assert run.user_id == "dev-user"
    finally:
        db.close()


def test_get_run_by_id_returns_correct_data():
    run_id = _post_run()["run_id"]
    res = client.get(f"/runs/{run_id}")
    assert res.status_code == 200
    assert res.json()["run_id"] == run_id


def test_runs_list_includes_new_run():
    run_id = _post_run()["run_id"]
    res = client.get("/runs")
    assert res.status_code == 200
    ids = [r["id"] for r in res.json()]   # list endpoint uses "id", detail uses "run_id"
    assert run_id in ids


def test_multiple_runs_all_in_list():
    id1 = _post_run()["run_id"]
    id2 = _post_run()["run_id"]
    res = client.get("/runs")
    ids = [r["id"] for r in res.json()]
    assert id1 in ids
    assert id2 in ids


# ── Quiz lifecycle ────────────────────────────────────────────────────────────

def test_quiz_attempt_score_returned():
    run_id = _post_run()["run_id"]
    res = client.post(
        "/quiz/attempt",
        json={
            "run_id": run_id,
            "answers": [
                {"question_idx": 0, "question_text": "Q1?",
                 "chosen_answer": "A", "correct_answer": "A"},
                {"question_idx": 1, "question_text": "Q2?",
                 "chosen_answer": "B", "correct_answer": "C"},
            ],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["score"] == 1
    assert body["total"] == 2
    assert body["pct"] == 50


def test_quiz_attempt_persisted_in_history():
    run_id = _post_run()["run_id"]
    client.post(
        "/quiz/attempt",
        json={
            "run_id": run_id,
            "answers": [
                {"question_idx": 0, "question_text": "Q?",
                 "chosen_answer": "A", "correct_answer": "A"},
            ],
        },
    )
    hist = client.get("/quiz/history").json()
    run_ids = [h["run_id"] for h in hist]
    assert run_id in run_ids


def test_quiz_correct_answer_flag():
    run_id = _post_run()["run_id"]
    client.post(
        "/quiz/attempt",
        json={
            "run_id": run_id,
            "answers": [
                {"question_idx": 0, "question_text": "Q?",
                 "chosen_answer": "A", "correct_answer": "A"},
                {"question_idx": 1, "question_text": "Q2?",
                 "chosen_answer": "B", "correct_answer": "D"},
            ],
        },
    )
    hist = client.get("/quiz/history").json()
    for entry in hist:
        if entry["run_id"] == run_id and entry["question_idx"] == 0:
            assert entry["is_correct"] is True
        if entry["run_id"] == run_id and entry["question_idx"] == 1:
            assert entry["is_correct"] is False


# ── Exports ───────────────────────────────────────────────────────────────────
# generate_pdf/generate_anki have their own unit tests in test_export.py.
# Here we just verify the HTTP layer: valid run → 200, bad run → 404.

def test_export_pdf_returns_bytes():
    run_id = _post_run()["run_id"]
    with patch("engine.export.generate_pdf", return_value=b"%PDF-stub"):
        res = client.get(f"/runs/{run_id}/export/pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert len(res.content) > 0


def test_export_anki_returns_bytes():
    run_id = _post_run()["run_id"]
    with patch("engine.export.generate_anki", return_value=b"PK\x03\x04stub"):
        res = client.get(f"/runs/{run_id}/export/anki")
    assert res.status_code == 200
    assert len(res.content) > 0


def test_export_nonexistent_run():
    with patch("engine.export.generate_pdf", return_value=b"%PDF-stub"):
        res = client.get("/runs/999999/export/pdf")
    assert res.status_code == 404


# ── Search ────────────────────────────────────────────────────────────────────

def test_search_no_docs_returns_empty():
    """With no documents in the library, search must return an empty list."""
    res = client.get("/search", params={"q": "anything"})
    assert res.status_code == 200
    assert res.json()["results"] == []
