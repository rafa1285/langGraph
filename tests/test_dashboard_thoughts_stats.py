"""Unit and integration tests for Fase 3: Agent Thoughts (Pestaña 2) & Agent Usage (Pestaña 3)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
import uuid

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app, lifespan


@pytest.fixture
async def stats_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Provide AsyncClient with populated test SQLite database with 13 agent records."""
    db_file = tmp_path / "office_stats_test.sqlite"
    settings.USE_MOCK_LLM = True
    settings.CHECKPOINT_DB_PATH = str(tmp_path / "checkpoints_test.sqlite")
    settings.OFFICE_DB_PATH = str(db_file)
    settings.WORKSPACES_DIR = str(tmp_path / "workspaces_test")
    settings.PROMPTS_DIR = str(tmp_path / "prompts_test")

    # Create schema and sample records for testing
    async with aiosqlite.connect(str(db_file)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_conversations (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                step_number INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                system_prompt TEXT,
                user_payload TEXT,
                raw_response TEXT,
                status TEXT,
                verdict TEXT,
                score INTEGER,
                culprit TEXT,
                duration_ms INTEGER,
                estimated_tokens_in INTEGER,
                estimated_tokens_out INTEGER,
                created_at TEXT,
                is_visible INTEGER DEFAULT 1
            )
            """
        )

        # Seed 13 agents with YAML frontmatter
        official_agents = [
            ("agente_00_ceo", "LANZAMIENTO_AUTORIZADO", "APROBADO", 1000, 2500),
            ("agente_01_pm", "PRE_SDD_LISTO", "APROBADO", 500, 1200),
            ("agente_02_architect", "APROBADO_PARA_DESARROLLO", "APROBADO", 800, 1800),
            ("agente_11_ui_ux", "SISTEMA_DISENO_UI_LISTO", "APROBADO", 1200, 2400),
            ("agente_03_laravel", "IMPLEMENTADO_PARA_REVISION", "APROBADO", 1500, 3000),
            ("agente_04_fastapi", "IMPLEMENTADO_PARA_REVISION", "APROBADO", 1400, 2900),
            ("agente_05_qa_php", "APROBADO_PARA_DESPLIEGUE", "APROBADO", 600, 1100),
            ("agente_06_qa_python", "APROBADO_PARA_DESPLIEGUE", "APROBADO", 700, 1300),
            ("agente_07_devops", "INFRAESTRUCTURA_LISTA", "APROBADO", 900, 2000),
            ("agente_10_ciso", "AUDITORIA_APROBADA", "APROBADO", 750, 1600),
            ("agente_08_docs", "DOCUMENTACION_LISTA", "APROBADO", 650, 1400),
            ("agente_12_marketing", "ESTRATEGIA_LISTA", "APROBADO", 850, 1900),
            ("agente_13_sales_analytics", "METRICAS_LISTAS", "APROBADO", 950, 2100),
        ]

        for idx, (ag_id, st, vd, tok_in, tok_out) in enumerate(official_agents, start=1):
            raw = (
                f"---\n"
                f"id_proyecto: proj_test_fase3\n"
                f"version_iteracion: 1\n"
                f"agente_emisor: {ag_id}\n"
                f"agente_receptor: siguiente_fase\n"
                f"estado: {st}\n"
                f"prioridad: ALTA\n"
                f"timestamp: 2026-11-11T12:00:00Z\n"
                f"veredicto: {vd}\n"
                f"---\n\n"
                f"# Entregable de {ag_id}\n\n"
                f"Este es el entregable completo generado por `{ag_id}`.\n\n"
                f"```python\ndef test_{ag_id}():\n    return '{st}'\n```\n"
            )
            await db.execute(
                """
                INSERT INTO agent_conversations (
                    id, project_id, step_number, agent_id, system_prompt,
                    user_payload, raw_response, status, verdict, score,
                    duration_ms, estimated_tokens_in, estimated_tokens_out,
                    created_at, is_visible
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    str(uuid.uuid4()),
                    "proj_test_fase3",
                    idx,
                    ag_id,
                    f"System prompt for {ag_id}",
                    "Instruccion de prueba",
                    raw,
                    st,
                    vd,
                    100,
                    1200 + idx * 100,
                    tok_in,
                    tok_out,
                    f"2026-11-11T12:{idx:02d}:00Z",
                ),
            )
        await db.commit()

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.mark.asyncio
async def test_agent_thoughts_endpoint_frontmatter_extraction(stats_client: AsyncClient) -> None:
    """Verify that /api/v1/telemetry/thoughts extracts YAML frontmatter with the 7 required metadata fields."""
    response = await stats_client.get("/api/v1/telemetry/thoughts?project_id=proj_test_fase3")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 13
    assert len(data["thoughts"]) == 13

    # Check that every thought has the 7 required frontmatter attributes
    for item in data["thoughts"]:
        fm = item["frontmatter"]
        assert fm["id_proyecto"] == "proj_test_fase3"
        assert fm["version_iteracion"] == 1
        assert fm["agente_emisor"] == item["agent_id"]
        assert "agente_receptor" in fm
        assert "estado" in fm
        assert fm["prioridad"] == "ALTA"
        assert "timestamp" in fm
        assert "```python" in item["raw_response"]


@pytest.mark.asyncio
async def test_agent_stats_endpoint_13_agents_and_graph_kpis(stats_client: AsyncClient) -> None:
    """Verify that /api/v1/telemetry/agent-stats computes Graph KPIs and returns exactly the 13 official agents."""
    response = await stats_client.get("/api/v1/telemetry/agent-stats?project_id=proj_test_fase3")
    assert response.status_code == 200
    data = response.json()

    # 1. KPIs de Rendimiento del Grafo
    assert data["total_agents"] == 13
    assert data["total_nodes_executed"] == 13
    assert data["current_iteration"] == 1
    assert data["avg_node_duration_ms"] > 0
    assert data["qa_success_rate"] == 100.0
    assert data["total_tokens"] > 0

    # 2. Grid de los 13 Agentes Oficiales
    agents = data["agents"]
    assert len(agents) == 13

    official_ids = [
        "agente_00_ceo",
        "agente_01_pm",
        "agente_02_architect",
        "agente_11_ui_ux",
        "agente_03_laravel",
        "agente_04_fastapi",
        "agente_05_qa_php",
        "agente_06_qa_python",
        "agente_07_devops",
        "agente_10_ciso",
        "agente_08_docs",
        "agente_12_marketing",
        "agente_13_sales_analytics",
    ]

    retrieved_ids = [a["agent_id"] for a in agents]
    assert retrieved_ids == official_ids

    # Check card metadata per agent
    for a in agents:
        assert a["tasks_count"] == 1
        assert a["total_tokens"] > 0
        assert a["status_badge"] == "APPROVED"
        assert a["token_share_pct"] > 0.0
        assert a["role_desc"] != ""


@pytest.mark.asyncio
async def test_agent_stats_veracity_and_no_spurious_working_markers(stats_client: AsyncClient) -> None:
    """Verify that in an authorized completed project, no agents are stuck in WORKING or falsely BLOCKED."""
    response = await stats_client.get("/api/v1/telemetry/agent-stats?project_id=proj_test_fase3")
    assert response.status_code == 200
    data = response.json()
    agents = data["agents"]

    # In a completed project where CEO issued LANZAMIENTO_AUTORIZADO, no agent is WORKING
    working_agents = [a["agent_id"] for a in agents if a["status_badge"] == "WORKING"]
    assert len(working_agents) == 0, f"Agents unexpectedly in WORKING: {working_agents}"

    blocked_agents = [a["agent_id"] for a in agents if a["status_badge"] == "BLOCKED"]
    assert len(blocked_agents) == 0, f"Agents unexpectedly in BLOCKED: {blocked_agents}"

    # All participating agents must be APPROVED
    approved_agents = [a["agent_id"] for a in agents if a["status_badge"] == "APPROVED"]
    assert len(approved_agents) == 13


@pytest.mark.asyncio
async def test_dashboard_state_exposes_agent_outputs_and_usage(stats_client: AsyncClient) -> None:
    """Verify that /api/dashboard/state exposes historical events and valid counters."""
    response = await stats_client.get("/api/dashboard/state?project_id=proj_test_fase3")
    assert response.status_code == 200
    state = response.json()

    assert state["project_id"] == "proj_test_fase3"
    assert state["status"] == "COMPLETED"
    assert state["stage_index"] == 6
    assert state["tokens"] > 0
    assert len(state["events"]) > 0
