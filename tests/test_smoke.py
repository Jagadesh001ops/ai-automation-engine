"""
Smoke tests — verify every major route responds correctly.
Uses FastAPI TestClient (no real network, no LLM calls).
LLM-dependent routes mock the parse_intent / build_node_for_step calls.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api import app

client = TestClient(app, raise_server_exceptions=False)


# ─── Infrastructure ───────────────────────────────────────────────────────────

def test_health_returns_200():
    res = client.get("/health")
    assert res.status_code in (200, 503)   # 503 when DB/Redis unreachable in CI
    assert res.json()["status"] in ("ok", "degraded")


def test_health_has_db_and_redis_keys():
    res = client.get("/health")
    body = res.json()
    assert "db" in body
    assert "redis" in body


def test_metrics_endpoint_exists():
    res = client.get("/metrics")
    assert res.status_code == 200
    assert b"http_requests_total" in res.content or b"python_info" in res.content


def test_docs_endpoint_available():
    res = client.get("/docs")
    assert res.status_code == 200


# ─── Maintenance mode ─────────────────────────────────────────────────────────

def test_maintenance_mode_blocks_routes(monkeypatch):
    import api as _api
    monkeypatch.setattr(_api, "_MAINTENANCE", True)
    res = client.get("/runs")
    assert res.status_code == 503
    assert res.json()["status"] == "maintenance"


def test_maintenance_mode_exempts_health(monkeypatch):
    import api as _api
    monkeypatch.setattr(_api, "_MAINTENANCE", True)
    res = client.get("/health")
    assert res.status_code in (200, 503)   # health check itself may degrade; not blocked
    assert res.json().get("status") != "maintenance"


def test_maintenance_mode_exempts_metrics(monkeypatch):
    import api as _api
    monkeypatch.setattr(_api, "_MAINTENANCE", True)
    res = client.get("/metrics")
    assert res.status_code == 200


# ─── Runs ─────────────────────────────────────────────────────────────────────

def test_get_runs_returns_200():
    res = client.get("/runs")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_run_not_found():
    res = client.get("/runs/999999")
    assert res.status_code == 404


# ─── Run workflow (LLM mocked) ────────────────────────────────────────────────

def _make_plan():
    from engine.schemas import WorkflowPlan, WorkflowStep
    step = WorkflowStep(
        name="summarize",
        description="Summarise",
        input_key="document",
        output_key="summary",
    )
    return WorkflowPlan(
        goal="Summarise the document",
        scope="single_document",
        steps=[step],
        estimated_steps=1,
        too_broad=False,
    )


def test_post_run_returns_run_id():
    fake_node = MagicMock()
    fake_node.execute.return_value = MagicMock(
        success=True, output_key="summary", output_value="Test summary.",
        input_tokens=10, output_tokens=20, execution_time_ms=50, error=None,
    )

    with (
        patch("api.parse_intent", return_value=_make_plan()),
        patch("api.build_node_for_step", return_value=fake_node),
    ):
        res = client.post("/run", json={"document": "Some text.", "request": "summarise"})

    assert res.status_code == 200
    body = res.json()
    assert "run_id" in body
    assert isinstance(body["run_id"], int)


def test_post_run_persisted_in_get_runs():
    fake_node = MagicMock()
    fake_node.execute.return_value = MagicMock(
        success=True, output_key="summary", output_value="Persisted.",
        input_tokens=5, output_tokens=10, execution_time_ms=30, error=None,
    )

    with (
        patch("api.parse_intent", return_value=_make_plan()),
        patch("api.build_node_for_step", return_value=fake_node),
    ):
        post_res = client.post("/run", json={"document": "text", "request": "summarise"})

    run_id = post_res.json()["run_id"]
    get_res = client.get(f"/runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["run_id"] == run_id
