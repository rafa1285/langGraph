"""Phase 9 tests: REST API, CEO interactive mailbox, and WebSocket real-time event bus."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from app.core.config import settings
from app.graph.nodes import FactoryNodes
from app.graph.state import create_initial_state
from app.main import app, lifespan
from app.schemas.office import AgentConversationRecord, AgentEmailRecord
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.event_bus import event_bus
from app.services.llm_gateway import MockLLMGateway
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


@pytest.fixture
async def api_env(tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    """Configure isolated environment for REST and WebSocket API testing."""
    office_db = tmp_path / "office_data.sqlite"
    checkpoint_db = tmp_path / "checkpoints.sqlite"
    workspaces_dir = tmp_path / "workspaces"
    prompts_dir = tmp_path / "prompts"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    settings.USE_MOCK_LLM = True
    settings.OFFICE_DB_PATH = str(office_db)
    settings.CHECKPOINT_DB_PATH = str(checkpoint_db)
    settings.WORKSPACES_DIR = str(workspaces_dir)
    settings.PROMPTS_DIR = str(prompts_dir)

    store = OfficeStore(db_path=office_db)
    await store.init_db()

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield {
                "client": client,
                "office_store": store,
                "workspaces_dir": workspaces_dir,
                "tmp_path": tmp_path,
            }


@pytest.mark.asyncio
async def test_list_projects_empty_and_populated(api_env: dict[str, Any]) -> None:
    """Test GET /api/v1/projects listing projects from store and workspaces."""
    client: AsyncClient = api_env["client"]
    store: OfficeStore = api_env["office_store"]
    workspaces_dir: Path = api_env["workspaces_dir"]

    # 1. Empty state
    res = await client.get("/api/v1/projects")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["projects"] == []

    # 2. Add conversations for proj_alpha
    conv1 = AgentConversationRecord(
        project_id="proj_alpha",
        step_number=1,
        agent_id=AgentID.AGENTE_01_PM,
        system_prompt="sys prompt",
        user_payload="user payload",
        raw_response="response 1",
        status=DeliverableStatus.PRE_SDD_LISTO,
        verdict="APROBADO",
        score=100,
        culprit=None,
        duration_ms=450,
        estimated_tokens_in=100,
        estimated_tokens_out=200,
    )
    conv2 = AgentConversationRecord(
        project_id="proj_alpha",
        step_number=2,
        agent_id=AgentID.AGENTE_02_ARCHITECT,
        system_prompt="sys prompt",
        user_payload="user payload",
        raw_response="response 2",
        status=DeliverableStatus.APROBADO_PARA_DESARROLLO,
        verdict="APROBADO",
        score=100,
        culprit=None,
        duration_ms=550,
        estimated_tokens_in=150,
        estimated_tokens_out=250,
    )
    await store.save_conversation(conv1)
    await store.save_conversation(conv2)

    # 3. Create workspace directory for proj_beta
    (workspaces_dir / "proj_beta").mkdir(parents=True, exist_ok=True)

    # 4. Query projects list
    res = await client.get("/api/v1/projects")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2

    projects_by_id = {p["project_id"]: p for p in data["projects"]}
    alpha = projects_by_id["proj_alpha"]
    assert alpha["steps_completed"] == 2
    assert alpha["total_tokens_in"] == 250
    assert alpha["total_tokens_out"] == 450
    assert alpha["total_duration_ms"] == 1000
    assert alpha["current_status"] == DeliverableStatus.APROBADO_PARA_DESARROLLO.value

    beta = projects_by_id["proj_beta"]
    assert beta["steps_completed"] == 0
    assert beta["current_status"] == "INITIALIZING"


@pytest.mark.asyncio
async def test_get_project_conversations_and_filter(api_env: dict[str, Any]) -> None:
    """Test GET /api/v1/projects/{project_id}/conversations with agent filtering."""
    client: AsyncClient = api_env["client"]
    store: OfficeStore = api_env["office_store"]

    conv1 = AgentConversationRecord(
        project_id="proj_convs",
        step_number=1,
        agent_id=AgentID.AGENTE_01_PM,
        system_prompt="pm prompt",
        user_payload="pm payload",
        raw_response="pm response",
        status=DeliverableStatus.PRE_SDD_LISTO,
        verdict="APROBADO",
        score=95,
        culprit=None,
        duration_ms=300,
        estimated_tokens_in=50,
        estimated_tokens_out=80,
    )
    conv2 = AgentConversationRecord(
        project_id="proj_convs",
        step_number=2,
        agent_id=AgentID.AGENTE_04_FASTAPI,
        system_prompt="fastapi prompt",
        user_payload="fastapi payload",
        raw_response="fastapi response",
        status=DeliverableStatus.IMPLEMENTADO_PARA_REVISION,
        verdict="APROBADO",
        score=90,
        culprit=None,
        duration_ms=600,
        estimated_tokens_in=120,
        estimated_tokens_out=220,
    )
    await store.save_conversation(conv1)
    await store.save_conversation(conv2)

    # Retrieve all conversations
    res = await client.get("/api/v1/projects/proj_convs/conversations")
    assert res.status_code == 200
    all_convs = res.json()
    assert len(all_convs) == 2

    # Filter by agent_id
    res_filtered = await client.get(
        "/api/v1/projects/proj_convs/conversations",
        params={"agent_id": "agente_04_fastapi"},
    )
    assert res_filtered.status_code == 200
    filtered = res_filtered.json()
    assert len(filtered) == 1
    assert filtered[0]["agent_id"] == "agente_04_fastapi"

    # 404 for unknown project
    res_404 = await client.get("/api/v1/projects/proj_unknown_convs/conversations")
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_get_project_inbox_and_filters(api_env: dict[str, Any]) -> None:
    """Test GET /api/v1/projects/{project_id}/inbox with query parameter filters."""
    client: AsyncClient = api_env["client"]
    store: OfficeStore = api_env["office_store"]

    email1 = AgentEmailRecord(
        project_id="proj_inbox",
        step_number=1,
        sender="agente_01_pm@agentoffice.local",
        recipient="agente_04_fastapi@agentoffice.local",
        cc=[],
        subject="Especificación Pre-SDD",
        body_summary="Documento entregado",
        attached_deliverable_path="",
        priority="NORMAL",
        is_read=True,
    )
    email2 = AgentEmailRecord(
        project_id="proj_inbox",
        step_number=2,
        sender="ceo@agentoffice.local",
        recipient="agente_04_fastapi@agentoffice.local",
        cc=[],
        subject="Directiva urgente del CEO",
        body_summary="Priorizar autenticación",
        attached_deliverable_path="",
        priority="HIGH",
        is_read=False,
    )
    email3 = AgentEmailRecord(
        project_id="proj_inbox",
        step_number=3,
        sender="agente_10_ciso@agentoffice.local",
        recipient="agente_07_devops@agentoffice.local",
        cc=[],
        subject="Bloqueo de seguridad",
        body_summary="Parchear Dockerfile",
        attached_deliverable_path="",
        priority="CRITICAL",
        is_read=False,
    )
    await store.save_email(email1)
    await store.save_email(email2)
    await store.save_email(email3)

    # All emails
    res_all = await client.get("/api/v1/projects/proj_inbox/inbox")
    assert res_all.status_code == 200
    assert len(res_all.json()) == 3

    # Filter by recipient
    res_rec = await client.get(
        "/api/v1/projects/proj_inbox/inbox",
        params={"recipient": "agente_04_fastapi"},
    )
    assert res_rec.status_code == 200
    assert len(res_rec.json()) == 2

    # Filter by sender
    res_sender = await client.get(
        "/api/v1/projects/proj_inbox/inbox",
        params={"sender": "ceo"},
    )
    assert res_sender.status_code == 200
    assert len(res_sender.json()) == 1
    assert res_sender.json()[0]["sender"] == "ceo@agentoffice.local"

    # Filter by priority
    res_prio = await client.get(
        "/api/v1/projects/proj_inbox/inbox",
        params={"priority": "CRITICAL"},
    )
    assert res_prio.status_code == 200
    assert len(res_prio.json()) == 1

    # Filter unread only
    res_unread = await client.get(
        "/api/v1/projects/proj_inbox/inbox",
        params={"unread_only": "true"},
    )
    assert res_unread.status_code == 200
    assert len(res_unread.json()) == 2

    # 404 for unknown project
    res_404 = await client.get("/api/v1/projects/proj_unknown_inbox/inbox")
    assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_send_ceo_email_endpoint(api_env: dict[str, Any]) -> None:
    """Test POST /api/v1/projects/{project_id}/email from CEO to an agent."""
    client: AsyncClient = api_env["client"]
    store: OfficeStore = api_env["office_store"]

    payload = {
        "recipient": "agente_04_fastapi",
        "subject": "Directiva Prioritaria: JWT Auth",
        "body": "Asegurar que todos los endpoints incorporen autenticación JWT.",
        "priority": "HIGH",
    }
    res = await client.post("/api/v1/projects/proj_ceo_mail/email", json=payload)
    assert res.status_code == 201
    email_data = res.json()

    assert email_data["project_id"] == "proj_ceo_mail"
    assert email_data["sender"] == "ceo@agentoffice.local"
    assert email_data["recipient"] == "agente_04_fastapi@agentoffice.local"
    assert email_data["subject"] == "Directiva Prioritaria: JWT Auth"
    assert email_data["is_read"] is False
    assert email_data["priority"] == "HIGH"

    # Verify persisted in store as unread
    stored = await store.get_emails("proj_ceo_mail", unread_only=True)
    assert len(stored) == 1
    assert stored[0].sender == "ceo@agentoffice.local"
    assert stored[0].is_read is False


@pytest.mark.asyncio
async def test_materialize_endpoint(api_env: dict[str, Any]) -> None:
    """Test POST /api/v1/projects/{project_id}/materialize builds code and validates compose."""
    client: AsyncClient = api_env["client"]
    workspaces_dir: Path = api_env["workspaces_dir"]

    proj_dir = workspaces_dir / "proj_mat"
    proj_dir.mkdir(parents=True, exist_ok=True)

    fastapi_md = """---
origen: agente_04_fastapi
destino_siguiente: agente_06_qa_python
estado_entregable: CODIGO_PYTHON_LISTO
veredicto: APROBADO
puntuacion: 100
culpable_detectado: null
---
# Código Python FastAPI
#### app/main.py
```python
from fastapi import FastAPI

app = FastAPI(title="Materialized Service")

@app.get("/ping")
def ping():
    return {"status": "pong"}
```
"""
    (proj_dir / "01_agente_04_fastapi.md").write_text(fastapi_md, encoding="utf-8")

    devops_md = """---
origen: agente_07_devops
destino_siguiente: agente_10_ciso
estado_entregable: INFRAESTRUCTURA_DOCKER_LISTA
veredicto: APROBADO
puntuacion: 100
culpable_detectado: null
---
# Infraestructura DevOps
#### docker-compose.prod.yml
```yaml
version: '3.8'
services:
  web:
    image: python:3.12-slim
    ports:
      - "8000:8000"
```
"""
    (proj_dir / "02_agente_07_devops.md").write_text(devops_md, encoding="utf-8")

    res = await client.post("/api/v1/projects/proj_mat/materialize")
    assert res.status_code == 200
    data = res.json()

    assert data["project_id"] == "proj_mat"
    assert data["total_files"] >= 2
    assert data["compose_file"] == "docker-compose.prod.yml"
    assert data["compose_valid"] is True
    assert "start_local.ps1" in data["scripts"]
    assert "start_local.sh" in data["scripts"]

    # Check files on disk
    build_path = proj_dir / "build"
    assert (build_path / "app" / "main.py").exists()
    assert (build_path / "docker-compose.prod.yml").exists()
    assert (build_path / "start_local.ps1").exists()
    assert (build_path / "MANIFEST.json").exists()

    # 404 for non-existent project
    res_404 = await client.post("/api/v1/projects/proj_non_existent/materialize")
    assert res_404.status_code == 404


def test_websocket_realtime_broadcast(tmp_path: Path) -> None:
    """Test real-time event streaming to connected WebSocket clients."""
    settings.USE_MOCK_LLM = True
    settings.OFFICE_DB_PATH = str(tmp_path / "office_data.sqlite")
    settings.CHECKPOINT_DB_PATH = str(tmp_path / "checkpoints.sqlite")
    settings.WORKSPACES_DIR = str(tmp_path / "workspaces")
    settings.PROMPTS_DIR = str(tmp_path / "prompts")

    with TestClient(app) as test_client:
        with test_client.websocket_connect("/ws/projects/proj_ws_live") as ws:
            # Broadcast AGENT_STARTED
            asyncio.run(
                event_bus.broadcast(
                    project_id="proj_ws_live",
                    event_type="AGENT_STARTED",
                    data={"agent_id": "agente_01_pm", "step_number": 1},
                )
            )
            msg1 = ws.receive_json()
            assert msg1["project_id"] == "proj_ws_live"
            assert msg1["event_type"] == "AGENT_STARTED"
            assert msg1["data"]["agent_id"] == "agente_01_pm"

            # Broadcast GATE_REJECTED
            asyncio.run(
                event_bus.broadcast(
                    project_id="proj_ws_live",
                    event_type="GATE_REJECTED",
                    data={
                        "agent_id": "agente_10_ciso",
                        "verdict": "BLOQUEADO",
                        "culprit": "agente_04_fastapi",
                    },
                )
            )
            msg2 = ws.receive_json()
            assert msg2["event_type"] == "GATE_REJECTED"
            assert msg2["data"]["culprit"] == "agente_04_fastapi"


def test_ceo_email_triggers_websocket_event(tmp_path: Path) -> None:
    """Test that POST /email automatically broadcasts EMAIL_SENT event over WebSocket."""
    settings.USE_MOCK_LLM = True
    settings.OFFICE_DB_PATH = str(tmp_path / "office_data.sqlite")
    settings.CHECKPOINT_DB_PATH = str(tmp_path / "checkpoints.sqlite")
    settings.WORKSPACES_DIR = str(tmp_path / "workspaces")
    settings.PROMPTS_DIR = str(tmp_path / "prompts")

    with TestClient(app) as test_client:
        with test_client.websocket_connect("/ws/projects/proj_ws_ceo") as ws:
            # Trigger CEO email via REST endpoint
            res = test_client.post(
                "/api/v1/projects/proj_ws_ceo/email",
                json={
                    "recipient": "agente_01_pm",
                    "subject": "Modificar especificación",
                    "body": "Añadir soporte para cobro con Stripe",
                    "priority": "HIGH",
                },
            )
            assert res.status_code == 201

            msg = ws.receive_json()
            assert msg["project_id"] == "proj_ws_ceo"
            assert msg["event_type"] == "EMAIL_SENT"
            assert msg["data"]["sender"] == "ceo@agentoffice.local"
            assert msg["data"]["recipient"] == "agente_01_pm@agentoffice.local"
            assert msg["data"]["subject"] == "Modificar especificación"


@pytest.mark.asyncio
async def test_node_execution_broadcasts_websocket_events(tmp_path: Path) -> None:
    """Test that executing an agent step publishes AGENT_STARTED, EMAIL_SENT, STEP_COMPLETED."""
    settings.USE_MOCK_LLM = True
    office_db = tmp_path / "office_data.sqlite"
    workspaces_dir = tmp_path / "workspaces"
    prompts_dir = tmp_path / "prompts"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    settings.OFFICE_DB_PATH = str(office_db)
    settings.CHECKPOINT_DB_PATH = str(tmp_path / "checkpoints.sqlite")
    settings.WORKSPACES_DIR = str(workspaces_dir)
    settings.PROMPTS_DIR = str(prompts_dir)

    store = OfficeStore(db_path=office_db)
    await store.init_db()
    mail_svc = MailService(store)
    loader = PromptLoader(prompts_dir=prompts_dir)
    writer = WorkspaceWriter(base_dir=workspaces_dir)
    mock_llm = MockLLMGateway()

    nodes = FactoryNodes(
        llm_gateway=mock_llm,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=store,
        mail_service=mail_svc,
        event_bus=event_bus,
    )

    state = create_initial_state(
        idea_inicial="App de microservicios para streaming musical.",
        project_id="proj_ws_node",
    )

    # Mock a dummy WebSocket connection into event_bus to record broadcasts
    class DummyWS:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def accept(self) -> None:
            pass

        async def send_text(self, text: str) -> None:
            self.sent.append(text)

    dummy_ws = cast(Any, DummyWS())
    await event_bus.connect("proj_ws_node", dummy_ws)

    try:
        # Run node_01_pm
        result = await nodes.node_01_pm(state)
        assert "pre_sdd_doc" in result
        assert len(dummy_ws.sent) >= 3

        import json
        parsed_events = [json.loads(s) for s in dummy_ws.sent]
        event_types = [e["event_type"] for e in parsed_events]
        assert "AGENT_STARTED" in event_types
        assert "EMAIL_SENT" in event_types
        assert "STEP_COMPLETED" in event_types
    finally:
        await event_bus.disconnect("proj_ws_node", dummy_ws)
