"""Phase 18 tests: Brownfield GitHub audit, CISO/Architect diagnosis, and approval flow."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app, lifespan
from app.schemas.brownfield import (
    BrownfieldApproveRequest,
    BrownfieldAuditRequest,
)
from app.schemas.routing import AgentID
from app.services.brownfield_service import (
    BrownfieldService,
    _extract_score,
    parse_github_url,
)
from app.services.llm_gateway import LLMGatewayProtocol
from app.services.office_store import OfficeStore


class CustomAuditMockLLM(LLMGatewayProtocol):
    """Mock LLM returning diagnostic assessment for CISO and Architect."""

    async def invoke_agent(
        self, agent_id: AgentID, system_prompt: str, user_payload: str
    ) -> str:
        if agent_id == AgentID.AGENTE_10_CISO:
            return (
                "Puntuación: 75 / 100\n"
                "Dictamen CISO: Repositorio con superficie de ataque controlada.\n"
                "Recomendación: Establecer escaneo de dependencias en CI/CD."
            )
        return (
            "Puntuación: 85 / 100\n"
            "Dictamen Arquitectura: Buen desacoplamiento en routers y modelos.\n"
            "Recomendación: Extraer lógica de servicios a clases dedicadas."
        )


@pytest.fixture
async def brownfield_env(tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    """Configure isolated environment for Brownfield API testing."""
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
                "tmp_path": tmp_path,
            }


def test_parse_github_url_variants() -> None:
    """Verify URL parser handles diverse GitHub URL patterns."""
    assert parse_github_url("https://github.com/owner/my-repo") == ("owner", "my-repo")
    assert parse_github_url("https://github.com/owner/my-repo.git") == ("owner", "my-repo")
    assert parse_github_url("owner/my-repo") == ("owner", "my-repo")
    assert parse_github_url("git@github.com:owner/my-repo.git") == ("owner", "my-repo")

    with pytest.raises(ValueError, match="inválida"):
        parse_github_url("invalid_url")


def test_extract_score_patterns() -> None:
    """Verify regex extraction of 0-100 scores."""
    assert _extract_score("Puntuación: 88 / 100", default=50) == 88
    assert _extract_score("Score: 95", default=50) == 95
    assert _extract_score("Calificación: 42", default=50) == 42
    assert _extract_score("Sin notas explícitas", default=50) == 50


@pytest.mark.asyncio
async def test_brownfield_service_start_audit_and_persistence(tmp_path: Path) -> None:
    """Verify start_audit creates report, computes score, and stores in SQLite."""
    store = OfficeStore(db_path=tmp_path / "office_test.sqlite")
    await store.init_db()

    service = BrownfieldService(
        llm_gateway=CustomAuditMockLLM(),
        office_store=store,
    )

    req = BrownfieldAuditRequest(
        repo_url="https://github.com/mock-org/test-api",
        branch="main",
        depth="surface",
    )

    report = await service.start_audit(req)

    assert report.project_id.startswith("bf_")
    assert report.repo_url == "https://github.com/mock-org/test-api"
    assert report.health_score == 80  # (75 + 85) / 2
    assert report.status == "pending_approval"
    assert "CISO" in report.ciso_verdict
    assert "Arquitectura" in report.architect_verdict
    assert len(report.recommendations) > 0

    # Retrieve from DB
    loaded = await store.get_audit_report(report.project_id)
    assert loaded is not None
    assert loaded.project_id == report.project_id
    assert loaded.health_score == 80


@pytest.mark.asyncio
async def test_brownfield_approval_and_rejection_flow(tmp_path: Path) -> None:
    """Verify approval transitions status to approved, and rejection to rejected."""
    store = OfficeStore(db_path=tmp_path / "office_test_flow.sqlite")
    await store.init_db()

    service = BrownfieldService(
        llm_gateway=CustomAuditMockLLM(),
        office_store=store,
    )

    # 1. Start audit
    report = await service.start_audit(
        BrownfieldAuditRequest(repo_url="owner/app1", depth="surface")
    )

    # 2. Approve
    approve_req = BrownfieldApproveRequest(scope=["security_fixes", "tests"])
    pid = await service.approve_and_start_refactor(report.project_id, approve_req)
    assert pid == report.project_id

    approved_report = await store.get_audit_report(report.project_id)
    assert approved_report is not None
    assert approved_report.status == "approved"

    # 3. Cannot approve again
    with pytest.raises(ValueError, match="El informe ya está en estado"):
        await service.approve_and_start_refactor(report.project_id, approve_req)

    # 4. Rejection flow on second project
    report2 = await service.start_audit(
        BrownfieldAuditRequest(repo_url="owner/app2", depth="surface")
    )
    await service.reject_audit(report2.project_id)
    rejected_report = await store.get_audit_report(report2.project_id)
    assert rejected_report is not None
    assert rejected_report.status == "rejected"


@pytest.mark.asyncio
async def test_api_brownfield_endpoints(brownfield_env: dict[str, Any]) -> None:
    """Test full HTTP API lifecycle for brownfield audit, review, and approval."""
    client: AsyncClient = brownfield_env["client"]

    # 1. Start audit
    post_resp = await client.post(
        "/api/v1/office/brownfield/audit",
        json={"repo_url": "https://github.com/acme/backend", "depth": "surface"},
    )
    assert post_resp.status_code == 200, post_resp.text
    data = post_resp.json()
    project_id = data["project_id"]
    assert project_id.startswith("bf_")
    assert data["status"] == "pending_approval"
    assert "health_score" in data

    # 2. Get audit report
    get_resp = await client.get(f"/api/v1/office/brownfield/{project_id}/audit")
    assert get_resp.status_code == 200
    assert get_resp.json()["project_id"] == project_id

    # 3. Approve audit
    app_resp = await client.post(
        f"/api/v1/office/brownfield/{project_id}/approve",
        json={"scope": ["docker", "fastapi_refactor"]},
    )
    assert app_resp.status_code == 200
    assert app_resp.json()["status"] == "approved"

    # 4. Unknown audit returns 404
    missing_resp = await client.get("/api/v1/office/brownfield/bf_inexistente/audit")
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_brownfield_depth_surface_vs_deep(brownfield_env: dict[str, Any]) -> None:
    """Verify that both surface and deep audit requests execute and record their depth level."""
    client: AsyncClient = brownfield_env["client"]

    # Surface audit
    res_surface = await client.post(
        "/api/v1/office/brownfield/audit",
        json={"repo_url": "https://github.com/acme/quick-check", "depth": "surface"},
    )
    assert res_surface.status_code == 200
    data_surface = res_surface.json()
    assert data_surface["depth"] == "surface"

    # Deep audit
    res_deep = await client.post(
        "/api/v1/office/brownfield/audit",
        json={"repo_url": "https://github.com/acme/deep-check", "depth": "deep"},
    )
    assert res_deep.status_code == 200
    data_deep = res_deep.json()
    assert data_deep["depth"] == "deep"

