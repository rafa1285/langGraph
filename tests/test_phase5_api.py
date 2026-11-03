"""End-to-end integration tests for Phase 5 FastAPI endpoints and CLI."""

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app, lifespan
from app.schemas.routing import DeliverableStatus
from app.services.orchestrator_service import OrchestratorService
from cli import resume_command, run_command


@pytest.fixture
async def api_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient configured with mock LLM and temporary SQLite checkpoints."""
    settings.USE_MOCK_LLM = True
    settings.CHECKPOINT_DB_PATH = str(tmp_path / "checkpoints.sqlite")
    settings.WORKSPACES_DIR = str(tmp_path / "workspaces")
    settings.PROMPTS_DIR = str(tmp_path / "prompts")

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.mark.asyncio
async def test_health_check(api_client: AsyncClient) -> None:
    """Test the /health status endpoint."""
    response = await api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_project_validation_failure(api_client: AsyncClient) -> None:
    """Test that ideas with fewer than 10 characters are rejected with HTTP 422."""
    response = await api_client.post(
        "/api/v1/projects",
        json={"idea_inicial": "corta"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_and_inspect_project(api_client: AsyncClient) -> None:
    """Test full asynchronous project creation, background execution, and deliverable query."""
    idea = "Plataforma SaaS para contabilidad y facturación en tiempo real."
    create_res = await api_client.post(
        "/api/v1/projects",
        json={"idea_inicial": idea},
    )
    assert create_res.status_code == 202
    data = create_res.json()
    project_id = data["project_id"]
    assert data["status"] == "RUNNING"

    # Await background completion
    orchestrator = getattr(app.state, "orchestrator", None)
    assert isinstance(orchestrator, OrchestratorService)
    task = orchestrator._background_tasks[project_id]
    await task

    # Inspect project status
    status_res = await api_client.get(f"/api/v1/projects/{project_id}/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["project_id"] == project_id
    assert status_data["ultimo_agente"] in ("agente_00_ceo", "agente_09_growth")
    assert status_data["pasos_completados"] >= 11
    assert status_data["status_qa_php"] == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert status_data["status_qa_python"] == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert status_data["status_ciso"] == DeliverableStatus.BLINDADO_APTO_PRODUCCION

    # Inspect deliverables
    deliv_res = await api_client.get(f"/api/v1/projects/{project_id}/deliverables")
    assert deliv_res.status_code == 200
    deliv_data = deliv_res.json()
    assert deliv_data["project_id"] == project_id
    assert deliv_data["pre_sdd_doc"] != ""
    assert deliv_data["sdd_arquitectura"] != ""
    assert deliv_data["codigo_php"] != ""
    assert deliv_data["codigo_python"] != ""
    assert deliv_data["reporte_qa_php"] != ""
    assert deliv_data["reporte_qa_python"] != ""
    assert deliv_data["infraestructura_docker"] != ""
    assert deliv_data["dictamen_ciso"] != ""
    assert deliv_data["documentacion_rag"] != ""
    assert (deliv_data["estrategia_growth"] != "" or deliv_data["ceo_signoff"] != "")


@pytest.mark.asyncio
async def test_non_existent_project_errors(api_client: AsyncClient) -> None:
    """Test that queries on missing project IDs return HTTP 404."""
    ghost_id = "proj_non_existent_123"

    res_status = await api_client.get(f"/api/v1/projects/{ghost_id}/status")
    assert res_status.status_code == 404

    res_deliv = await api_client.get(f"/api/v1/projects/{ghost_id}/deliverables")
    assert res_deliv.status_code == 404

    res_resume = await api_client.post(f"/api/v1/projects/{ghost_id}/resume")
    assert res_resume.status_code == 404


@pytest.mark.asyncio
async def test_resume_project_endpoint(api_client: AsyncClient) -> None:
    """Test resuming an existing project via the API."""
    idea = "Plataforma de microservicios para logística."
    create_res = await api_client.post(
        "/api/v1/projects",
        json={"idea_inicial": idea},
    )
    assert create_res.status_code == 202
    project_id = create_res.json()["project_id"]

    orchestrator = getattr(app.state, "orchestrator", None)
    assert isinstance(orchestrator, OrchestratorService)
    await orchestrator._background_tasks[project_id]

    resume_res = await api_client.post(f"/api/v1/projects/{project_id}/resume")
    assert resume_res.status_code == 202
    assert resume_res.json()["status"] == "RESUMED"


@pytest.mark.asyncio
async def test_cli_resume_command_streaming(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test CLI resume command execution and step-by-step console reporting."""
    pid = "proj_cli_stream_test"
    db_file = str(tmp_path / "cli_checkpoints.db")
    ws_dir = str(tmp_path / "workspaces")

    with patch("app.core.config.settings.CHECKPOINT_DB_PATH", db_file):
        with patch("app.core.config.settings.WORKSPACES_DIR", ws_dir):
            await run_command("Idea para prueba CLI resume", mock=True, project_id=pid)
            captured_run = capsys.readouterr()
            assert f"Proyecto {pid} finalizado con éxito" in captured_run.out

            await resume_command(pid, mock=True)
            captured_resume = capsys.readouterr()
            assert f"Reanudando proyecto: {pid}" in captured_resume.out
            assert "finalizado tras reanudación" in captured_resume.out


@pytest.mark.asyncio
async def test_orchestrator_auto_reopen_on_resume(tmp_path: Path) -> None:
    """Test automatic reopening of circuit-breaker halted CISO projects upon resume."""
    from app.schemas.routing import AgentID
    from app.services.llm_gateway import MockLLMGateway
    from app.services.prompt_loader import PromptLoader
    from app.services.workspace_writer import WorkspaceWriter

    gateway = MockLLMGateway(ciso_failures_sequence=[AgentID.AGENTE_07_DEVOPS] * 5)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")

    db_path = str(tmp_path / "reopen_checkpoints.db")
    orchestrator = OrchestratorService(
        db_path=db_path,
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
    )
    await orchestrator.initialize()

    pid = "proj_ciso_halted_reopen"
    try:
        # 1. Initial run halts at CISO circuit breaker
        state_halted = await orchestrator.run_project_to_completion(pid, "App vulnerable")
        assert state_halted["retry_counts"]["ciso"] == 3
        assert state_halted["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD

        # 2. Resuming automatically reopens as BLINDADO and finishes pipeline
        state_resumed = await orchestrator.resume_project(pid)
        history = state_resumed["execution_history"]
        assert len(history) > len(state_halted["execution_history"])
        assert history[-1].agent_id in (AgentID.AGENTE_00_CEO, AgentID.AGENTE_09_GROWTH)
        assert history[-1].status in (
            DeliverableStatus.LANZAMIENTO_AUTORIZADO,
            DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100,
        )
        assert state_resumed["status_ciso"] == DeliverableStatus.BLINDADO_APTO_PRODUCCION
    finally:
        await orchestrator.close()
