"""Unit and integration tests for LangGraph real-time streaming, SSE, and 7-stage pipeline (Fase 2)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.core.config import settings
from app.main import app, lifespan
from app.services.dashboard_service import (
    PIPELINE_STAGES,
    dashboard_stream_service,
    map_node_to_pipeline_stage,
)


@pytest.fixture
def sync_client(tmp_path: Path) -> TestClient:
    """Provide a TestClient with isolated temporary databases and MockLLM."""
    settings.USE_MOCK_LLM = True
    settings.CHECKPOINT_DB_PATH = str(tmp_path / "checkpoints_stream.sqlite")
    settings.OFFICE_DB_PATH = str(tmp_path / "office_stream.sqlite")
    settings.WORKSPACES_DIR = str(tmp_path / "workspaces_stream")
    settings.PROMPTS_DIR = str(tmp_path / "prompts_stream")

    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Pipeline 7-Stage Mapping Unit Tests
# ---------------------------------------------------------------------------


def test_pipeline_stages_structure() -> None:
    """Verify that all 7 pipeline stages are defined with correct IDs and names."""
    assert len(PIPELINE_STAGES) == 7
    expected = [
        ("stage-received", "Received"),
        ("stage-ceo-charter", "CEO Charter"),
        ("stage-pm-design", "PM & Design"),
        ("stage-coding", "Coding"),
        ("stage-qa-ciso", "QA & CISO"),
        ("stage-growth-docs", "Growth & Docs"),
        ("stage-ceo-signoff", "CEO Signoff"),
    ]
    assert PIPELINE_STAGES == expected


def test_map_node_to_pipeline_stage_all_nodes() -> None:
    """Verify exact mapping of all agents and LangGraph nodes to the 7 stages."""
    # Stage 0: Received (Initial / User)
    assert map_node_to_pipeline_stage("user") == (0, "stage-received", "Received")
    assert map_node_to_pipeline_stage("") == (0, "stage-received", "Received")

    # Stage 1: CEO Charter
    assert map_node_to_pipeline_stage("node_00_ceo_charter") == (1, "stage-ceo-charter", "CEO Charter")
    assert map_node_to_pipeline_stage("agente_00_ceo") == (1, "stage-ceo-charter", "CEO Charter")
    assert map_node_to_pipeline_stage("agente_00_ceo_charter") == (1, "stage-ceo-charter", "CEO Charter")

    # Stage 2: PM & Design
    assert map_node_to_pipeline_stage("agente_01_pm") == (2, "stage-pm-design", "PM & Design")
    assert map_node_to_pipeline_stage("agente_02_architect") == (2, "stage-pm-design", "PM & Design")
    assert map_node_to_pipeline_stage("agente_11_ui_ux") == (2, "stage-pm-design", "PM & Design")

    # Stage 3: Coding
    assert map_node_to_pipeline_stage("agente_03_laravel") == (3, "stage-coding", "Coding")
    assert map_node_to_pipeline_stage("agente_04_fastapi") == (3, "stage-coding", "Coding")
    assert map_node_to_pipeline_stage("agente_07_devops") == (3, "stage-coding", "Coding")

    # Stage 4: QA & CISO
    assert map_node_to_pipeline_stage("agente_05_qa_php") == (4, "stage-qa-ciso", "QA & CISO")
    assert map_node_to_pipeline_stage("agente_06_qa_python") == (4, "stage-qa-ciso", "QA & CISO")
    assert map_node_to_pipeline_stage("qa_sync_barrier") == (4, "stage-qa-ciso", "QA & CISO")
    assert map_node_to_pipeline_stage("agente_10_ciso") == (4, "stage-qa-ciso", "QA & CISO")

    # Stage 5: Growth & Docs
    assert map_node_to_pipeline_stage("agente_08_docs") == (5, "stage-growth-docs", "Growth & Docs")
    assert map_node_to_pipeline_stage("agente_12_marketing") == (5, "stage-growth-docs", "Growth & Docs")
    assert map_node_to_pipeline_stage("agente_13_sales_analytics") == (5, "stage-growth-docs", "Growth & Docs")
    assert map_node_to_pipeline_stage("agente_09_growth") == (5, "stage-growth-docs", "Growth & Docs")

    # Stage 6: CEO Signoff
    assert map_node_to_pipeline_stage("node_00_ceo_signoff") == (6, "stage-ceo-signoff", "CEO Signoff")
    assert map_node_to_pipeline_stage("agente_00_ceo_signoff") == (6, "stage-ceo-signoff", "CEO Signoff")
    assert map_node_to_pipeline_stage("any_node", status="LANZAMIENTO_AUTORIZADO") == (
        6,
        "stage-ceo-signoff",
        "CEO Signoff",
    )


# ---------------------------------------------------------------------------
# 2. REST API Endpoints Verification
# ---------------------------------------------------------------------------


def test_dashboard_run_empty_prompt_validation(sync_client: TestClient) -> None:
    """Verify that POST /api/dashboard/run rejects empty prompts with HTTP 400."""
    resp = sync_client.post("/api/dashboard/run", json={"prompt": ""})
    assert resp.status_code == 400
    assert "vacío" in resp.json().get("detail", "").lower()

    resp_ws = sync_client.post("/api/dashboard/run", json={"prompt": "    "})
    assert resp_ws.status_code == 400


@pytest.mark.asyncio
async def test_dashboard_run_and_state(sync_client: TestClient) -> None:
    """Verify that POST /api/dashboard/run launches background execution and updates state."""
    pid = "proj_test_fase2_run"
    payload = {
        "prompt": "Construir plataforma SaaS de validación de APIs con Laravel y FastAPI",
        "id_proyecto": pid,
        "mock": True,
    }

    # 1. Trigger background run
    run_resp = sync_client.post("/api/dashboard/run", json=payload)
    assert run_resp.status_code == 202
    run_data = run_resp.json()
    assert run_data["project_id"] == pid
    assert run_data["status"] == "RUNNING"

    # 2. Query initial state
    state_resp = sync_client.get(f"/api/dashboard/state?project_id={pid}")
    assert state_resp.status_code == 200
    st_data = state_resp.json()
    assert st_data["project_id"] == pid
    assert len(st_data["events"]) >= 1

    # Check that initial Boss event was emitted
    boss_ev = st_data["events"][0]
    assert boss_ev["category"] == "user"
    assert "Request from Boss" in boss_ev["msg"]
    assert boss_ev["stage_index"] == 0
    assert boss_ev["stage_id"] == "stage-received"

    # 3. Poll until LangGraph node 1 streams its events (up to 4s)
    for _ in range(20):
        await asyncio.sleep(0.2)
        events = dashboard_stream_service._events.get(pid, [])
        if len(events) >= 2:
            break

    # 4. Re-query state to check stage progress and token accounting
    updated_state_resp = sync_client.get(f"/api/dashboard/state?project_id={pid}")
    assert updated_state_resp.status_code == 200
    updated_st = updated_state_resp.json()
    assert updated_st["tokens"] > 0
    assert len(updated_st["events"]) >= 2

    # Check categories emitted
    cats = {e.get("category") for e in updated_st["events"]}
    assert "user" in cats
    assert any(c in cats for c in ("response", "delegate", "tool", "done"))


def test_dashboard_stream_sse_endpoint(sync_client: TestClient) -> None:
    """Verify that GET /api/dashboard/stream streams SSE events formatted as data: {...}."""
    pid = "proj_test_sse_sync"
    asyncio.run(
        dashboard_stream_service.publish_event(
            pid,
            {
                "category": "user",
                "agent": "👔 Boss",
                "msg": "Request from Boss: Test SSE sync streaming",
                "stage_index": 0,
                "stage_id": "stage-received",
                "stage_name": "Received",
                "project_id": pid,
            },
        )
    )

    with sync_client.stream("GET", f"/api/dashboard/stream?project_id={pid}") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        found_event = False
        for raw_line in response.iter_lines():
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                if payload.get("category") == "user" and "Test SSE sync streaming" in payload.get("msg", ""):
                    found_event = True
                    break

        assert found_event is True
