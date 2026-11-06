"""Phase 16 tests: 1-on-1 agent interactive chat and history endpoints."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app, lifespan
from app.schemas.chat import ChatMessageRequest
from app.schemas.routing import AgentID
from app.services.chat_service import ChatService
from app.services.llm_gateway import MockLLMGateway
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader


@pytest.fixture
async def chat_env(tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    """Configure isolated environment for Office Chat testing."""
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
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield {
                "client": client,
                "office_store": store,
                "prompts_dir": prompts_dir,
                "tmp_path": tmp_path,
            }


@pytest.mark.asyncio
async def test_office_store_chat_turns(tmp_path: Path) -> None:
    """Test saving and retrieving chat turns in SQLite."""
    db_path = tmp_path / "test_chat.sqlite"
    store = OfficeStore(db_path=db_path)
    await store.init_db()

    session_id = str(uuid4())
    t1 = str(uuid4())
    t2 = str(uuid4())

    await store.save_chat_turn(
        turn_id=t1,
        session_id=session_id,
        agent_id=AgentID.AGENTE_01_PM.value,
        project_id="proj-123",
        role="user",
        content="Hola PM, ¿puedes resumirme el alcance?",
    )

    await store.save_chat_turn(
        turn_id=t2,
        session_id=session_id,
        agent_id=AgentID.AGENTE_01_PM.value,
        project_id="proj-123",
        role="agent",
        content="Claro, el alcance cubre autenticación y dashboard.",
    )

    history = await store.get_chat_history(session_id)
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[0].content == "Hola PM, ¿puedes resumirme el alcance?"
    assert history[1].role == "agent"
    assert history[1].content == "Claro, el alcance cubre autenticación y dashboard."


@pytest.mark.asyncio
async def test_chat_service_send_message_and_history(tmp_path: Path) -> None:
    """Test ChatService message orchestration with mock LLM and history building."""
    db_path = tmp_path / "test_chat_svc.sqlite"
    store = OfficeStore(db_path=db_path)
    await store.init_db()

    mock_llm = MockLLMGateway()
    prompt_loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    chat_svc = ChatService(
        llm_gateway=mock_llm,
        prompt_loader=prompt_loader,
        office_store=store,
    )

    session_id = str(uuid4())

    req1 = ChatMessageRequest(
        message="¿Cómo estructuramos la base de datos?",
        session_id=session_id,
        project_id="p-1",
    )
    res1 = await chat_svc.send_message(AgentID.AGENTE_02_ARCHITECT, req1)
    assert res1.agent_id == AgentID.AGENTE_02_ARCHITECT.value
    assert len(res1.response) > 0

    req2 = ChatMessageRequest(
        message="¿Y qué índices recomendamos?",
        session_id=session_id,
        project_id="p-1",
    )
    res2 = await chat_svc.send_message(AgentID.AGENTE_02_ARCHITECT, req2)
    assert res2.agent_id == AgentID.AGENTE_02_ARCHITECT.value

    # Verify history via get_history
    history = await chat_svc.get_history(AgentID.AGENTE_02_ARCHITECT, session_id)
    assert history.total == 4  # 2 user + 2 agent turns
    assert history.session_id == session_id
    assert history.turns[0].role == "user"
    assert history.turns[1].role == "agent"
    assert history.turns[2].role == "user"
    assert history.turns[3].role == "agent"


@pytest.mark.asyncio
async def test_api_chat_endpoint_flow(chat_env: dict[str, Any]) -> None:
    """Test POST /api/v1/office/chat/{agent_id} and GET history."""
    client: AsyncClient = chat_env["client"]
    session_id = str(uuid4())

    payload = {
        "message": "Hola CISO, ¿qué políticas de seguridad aplicamos?",
        "project_id": "proj-abc",
        "session_id": session_id,
    }

    resp = await client.post(
        f"/api/v1/office/chat/{AgentID.AGENTE_10_CISO.value}",
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["agent_id"] == AgentID.AGENTE_10_CISO.value
    assert data["session_id"] == session_id
    assert len(data["response"]) > 0

    # Retrieve history
    hist_resp = await client.get(
        f"/api/v1/office/chat/{AgentID.AGENTE_10_CISO.value}/history",
        params={"session_id": session_id},
    )
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["total"] == 2  # 1 user + 1 agent turn
    assert hist_data["turns"][0]["role"] == "user"
    assert hist_data["turns"][1]["role"] == "agent"


@pytest.mark.asyncio
async def test_api_chat_invalid_agent(chat_env: dict[str, Any]) -> None:
    """Test 404 behavior for unknown agent or barrier pseudo-nodes."""
    client: AsyncClient = chat_env["client"]

    # Unknown agent
    resp = await client.post(
        "/api/v1/office/chat/agente_fantasma",
        json={"message": "Hola", "session_id": str(uuid4())},
    )
    assert resp.status_code == 404
    assert "Agente desconocido" in resp.json()["detail"]

    # Pseudo-node qa_sync_barrier
    resp_barrier = await client.post(
        f"/api/v1/office/chat/{AgentID.QA_SYNC_BARRIER.value}",
        json={"message": "Hola", "session_id": str(uuid4())},
    )
    assert resp_barrier.status_code == 404
