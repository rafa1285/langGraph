"""Phase 11 tests: Serverless bundle generator and Vercel Cloud deployer service."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app as main_app
from app.main import lifespan
from app.services.office_store import OfficeStore
from app.services.vercel_deployer import (
    FALLBACK_RAG_CHUNKS,
    VercelDeployerService,
)
from app.templates.vercel.api_index import app as serverless_app
from cli import deploy_vercel_command


@pytest.fixture
def phase11_env(tmp_path: Path) -> dict[str, Any]:
    """Configure isolated environment for Phase 11 testing."""
    workspaces = tmp_path / "workspaces"
    office_db = tmp_path / "office_data.sqlite"
    workspaces.mkdir(parents=True, exist_ok=True)

    settings.WORKSPACES_DIR = str(workspaces)
    settings.OFFICE_DB_PATH = str(office_db)
    settings.VERCEL_TOKEN = "test_vercel_token_abc123"
    settings.VERCEL_TEAM_ID = "team_12345"
    settings.REAL_MAIL_ENABLED = False
    settings.NOTION_MCP_ENABLED = False

    return {
        "workspaces": workspaces,
        "office_db": office_db,
        "tmp_path": tmp_path,
    }


# =====================================================================
# 1. RAG Chunk Extraction & Bundle Generation Tests
# =====================================================================


def test_extract_rag_chunks_from_markdown(phase11_env: dict[str, Any]) -> None:
    """Test extracting structured JSON RAG knowledge base chunks from markdown deliverable."""
    workspaces = phase11_env["workspaces"]
    proj_dir = workspaces / "proj_extract"
    proj_dir.mkdir(parents=True, exist_ok=True)

    sample_json = [
        {
            "id_chunk": "KB-CUSTOM-001",
            "categoria": "Test Category",
            "intencion_usuario": ["¿Cómo probar esto?"],
            "contexto_autocontenido": "Contexto de prueba para verificación.",
            "respuesta_resolutiva": "Respuesta resolutiva de prueba.",
        }
    ]
    md_file = proj_dir / "21_agente_08_docs.md"
    md_file.write_text(
        f"# Documentación\n\n```json\n{import_json_str(sample_json)}\n```\n",
        encoding="utf-8",
    )

    deployer = VercelDeployerService()
    chunks = deployer.extract_rag_chunks("proj_extract")
    assert len(chunks) == 1
    assert chunks[0]["id_chunk"] == "KB-CUSTOM-001"

    # Non-existent or empty markdown falls back to FALLBACK_RAG_CHUNKS
    fallback_chunks = deployer.extract_rag_chunks("proj_missing")
    assert len(fallback_chunks) == len(FALLBACK_RAG_CHUNKS)
    assert fallback_chunks[0]["id_chunk"] == "KB-BILLING-001"


def import_json_str(obj: Any) -> str:
    """Helper serializer for markdown embeddings."""
    import json

    return json.dumps(obj)


def test_build_vercel_bundle_creates_expected_assets(phase11_env: dict[str, Any]) -> None:
    """Verify build_vercel_bundle outputs all landing, docs, serverless API and config files."""
    workspaces = phase11_env["workspaces"]
    proj_dir = workspaces / "proj_test_v11"
    proj_dir.mkdir(parents=True, exist_ok=True)

    # Place sample deliverable
    docs_md = proj_dir / "21_agente_08_docs.md"
    docs_md.write_text("# Docs Deliverable\nSin json para usar fallback.", encoding="utf-8")

    deployer = VercelDeployerService()
    bundle_path = deployer.build_vercel_bundle("proj_test_v11")

    assert bundle_path.exists()
    assert bundle_path.is_dir()

    # 1. Landing Page
    index_html = bundle_path / "index.html"
    assert index_html.exists()
    index_content = index_html.read_text(encoding="utf-8")
    assert "ValidatorHQ" in index_content
    assert 'id="demo"' in index_content
    assert "Alex" in index_content
    assert "$19" in index_content
    assert "$69" in index_content
    assert "$199" in index_content

    # 2. Docs Portal
    docs_html = bundle_path / "docs.html"
    assert docs_html.exists()
    docs_content = docs_html.read_text(encoding="utf-8")
    assert "ValidatorHQ" in docs_content
    assert "/api/health" in docs_content

    # 3. Serverless API
    api_file = bundle_path / "api" / "index.py"
    assert api_file.exists()
    api_content = api_file.read_text(encoding="utf-8")
    assert "FastAPI" in api_content
    assert "/api/validate-demo" in api_content
    assert "/api/rag/ask" in api_content

    # 4. RAG Chunks JSON
    rag_json = bundle_path / "rag_chunks.json"
    assert rag_json.exists()
    import json

    chunks_data = json.loads(rag_json.read_text(encoding="utf-8"))
    assert isinstance(chunks_data, list)
    assert len(chunks_data) >= 4

    # 5. Requirements
    reqs = bundle_path / "requirements.txt"
    assert reqs.exists()
    assert "fastapi" in reqs.read_text(encoding="utf-8")

    # 6. vercel.json
    vercel_cfg = bundle_path / "vercel.json"
    assert vercel_cfg.exists()
    vercel_data = json.loads(vercel_cfg.read_text(encoding="utf-8"))
    assert "rewrites" in vercel_data
    assert vercel_data["rewrites"][0]["source"] == "/api/(.*)"
    assert vercel_data["rewrites"][0]["destination"] == "/api/index.py"
    assert "builds" not in vercel_data

    # 7. Static files placed strictly in root (sibling to api/)
    assert (bundle_path / "index.html").is_file()
    assert (bundle_path / "docs.html").is_file()
    assert (bundle_path / "api").is_dir()
    assert not (bundle_path / "api" / "index.html").exists()
    assert not (bundle_path / "api" / "docs.html").exists()


def test_serverless_routes_strictly_prefixed_and_no_wildcard() -> None:
    """Verify FastAPI serverless app does not intercept static files with catch-all routes."""
    for route in serverless_app.routes:
        path = getattr(route, "path", "")
        # Only built-in docs or /api/ paths should exist, no root wildcard
        assert not path.startswith("/{path"), f"Wildcard route detected: {path}"
        assert not path.startswith("/{full_path"), f"Wildcard route detected: {path}"
        if path not in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
            assert path.startswith("/api/"), f"Route not prefixed with /api/: {path}"


# =====================================================================
# 2. Serverless FastAPI Engine Endpoint Tests
# =====================================================================


@pytest.mark.asyncio
async def test_serverless_health_endpoint() -> None:
    """Test GET /api/health on serverless FastAPI application."""
    transport = ASGITransport(app=serverless_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "UP"
        assert data["ciso_ssrf_shield"] == "ACTIVE"
        assert data["rag_engine"] == "READY"


@pytest.mark.asyncio
async def test_serverless_validate_demo_deduplication() -> None:
    """Test SHA-256 deduplication logic in /api/validate-demo."""
    transport = ASGITransport(app=serverless_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = "unique.customer@corporate.com"

        resp = await client.post(
            "/api/validate-demo",
            json={"emails": [email, email.upper()]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_emails"] == 2
        assert data["summary"]["deliverable"] == 1
        assert data["summary"]["duplicate"] == 1
        assert data["summary"]["credits_saved_by_dedup"] == 1
        assert data["items"][0]["verdict"] == "DELIVERABLE"
        assert data["items"][0]["credits"] == 1
        assert data["items"][1]["verdict"] == "DUPLICATE"
        assert data["items"][1]["credits"] == 0
        assert data["items"][1]["reason"] == "HASH_DUPLICATE_FREE"


@pytest.mark.asyncio
async def test_serverless_validate_demo_rfc5322_syntax() -> None:
    """Test RFC 5322 syntax validation rejecting malformed emails."""
    transport = ASGITransport(app=serverless_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invalid_emails = [
            "missing-at-sign.com",
            "@no-local-part.com",
            "spaces in@address.org",
            "double@@signs.com",
        ]
        for bad_email in invalid_emails:
            resp = await client.post("/api/validate-demo", json={"email": bad_email})
            assert resp.status_code == 200
            data = resp.json()
            assert data["state"] == "UNDELIVERABLE"
            assert data["reason"] == "SYNTAX_INVALID"
            assert data["credits_charged"] == 0


@pytest.mark.asyncio
async def test_serverless_validate_demo_ciso_ssrf_shield() -> None:
    """Test CISO Anti-SSRF shield blocking loopback, private IPs, and internal domains."""
    transport = ASGITransport(app=serverless_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ssrf_targets = [
            "admin@127.0.0.1",
            "root@10.0.0.1",
            "corp@192.168.1.50",
            "internal@172.16.0.5",
            "test@[::1]",
            "mapped@[::ffff:127.0.0.1]",
            "attacker@localhost",
            "cloud@metadata.google.internal",
            "probe@internal.lan",
            "cluster@service.local",
        ]
        for target in ssrf_targets:
            resp = await client.post("/api/validate-demo", json={"email": target})
            assert resp.status_code == 200
            data = resp.json()
            assert data["state"] == "UNDELIVERABLE"
            assert data["reason"] == "SSRF_REJECTED"
            assert data["credits_charged"] == 0
            assert "Escudo CISO Anti-SSRF" in data["explanation"]


@pytest.mark.asyncio
async def test_serverless_validate_demo_disposable_domain() -> None:
    """Test disposable/burner email detection returning RISKY state."""
    transport = ASGITransport(app=serverless_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        disposable_emails = [
            "throwaway@mailinator.com",
            "burner@tempmail.com",
            "junk@guerrillamail.com",
            "fake@yopmail.com",
        ]
        for disp_email in disposable_emails:
            resp = await client.post("/api/validate-demo", json={"email": disp_email})
            assert resp.status_code == 200
            data = resp.json()
            assert data["state"] == "RISKY"
            assert data["reason"] == "DISPOSABLE_DOMAIN"
            assert data["credits_charged"] == 1


@pytest.mark.asyncio
async def test_serverless_rag_ask_intent_matching() -> None:
    """Test Alex RAG chat responding accurately based on knowledge base chunks."""
    transport = ASGITransport(app=serverless_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Billing / Unknown refund intent
        resp1 = await client.post(
            "/api/rag/ask",
            json={"question": "¿Qué pasa si un correo resulta en Unknown?"},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["chunk_id"] == "KB-BILLING-001"
        assert "reembolsa" in data1["answer"].lower()
        assert data1["confidence"] >= 0.75

        # 2. Duplicate deduplication intent
        resp2 = await client.post(
            "/api/rag/ask",
            json={"question": "¿Cómo manejan los correos repetidos o duplicados?"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["chunk_id"] == "KB-BILLING-002"
        assert "deduplicación" in data2["answer"].lower()

        # 3. GDPR retention intent
        resp3 = await client.post(
            "/api/rag/ask",
            json={"question": "¿Cuánto tiempo guardan mis archivos según GDPR?"},
        )
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["chunk_id"] == "KB-GDPR-001"
        assert "15 días" in data3["answer"].lower()


# =====================================================================
# 3. Deployer Service & Cloud Integration Tests
# =====================================================================


@pytest.mark.asyncio
async def test_deploy_to_vercel_missing_token(phase11_env: dict[str, Any]) -> None:
    """Test deploy_to_vercel graceful failure when VERCEL_TOKEN is not configured."""
    settings.VERCEL_TOKEN = None
    deployer = VercelDeployerService()

    result = await deployer.deploy_to_vercel("proj_no_token")
    assert result["success"] is False
    assert "VERCEL_TOKEN" in str(result["error"])


@pytest.mark.asyncio
async def test_deploy_to_vercel_api_error(phase11_env: dict[str, Any]) -> None:
    """Test deploy_to_vercel handling upstream HTTP error from Vercel API."""
    workspaces = phase11_env["workspaces"]
    proj_dir = workspaces / "proj_api_err"
    proj_dir.mkdir(parents=True, exist_ok=True)

    mock_response = httpx.Response(
        status_code=403,
        json={"error": {"code": "forbidden", "message": "Invalid token or permissions"}},
        request=httpx.Request("POST", "https://api.vercel.com/v13/deployments"),
    )

    async def mock_post(*args: Any, **kwargs: Any) -> httpx.Response:
        return mock_response

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=mock_post)

    deployer = VercelDeployerService(client=mock_client)
    result = await deployer.deploy_to_vercel("proj_api_err", project_name="validator-hq-err")

    assert result["success"] is False
    assert "Vercel API error HTTP 403" in str(result["error"])


@pytest.mark.asyncio
async def test_deploy_to_vercel_success_and_email_notification(
    phase11_env: dict[str, Any],
) -> None:
    """Test full deployment flow with simulated 201 response and internal notification logging."""
    workspaces = phase11_env["workspaces"]
    office_db = phase11_env["office_db"]
    proj_dir = workspaces / "proj_success_v11"
    proj_dir.mkdir(parents=True, exist_ok=True)

    store = OfficeStore(db_path=office_db)
    await store.init_db()

    mock_deploy_response = httpx.Response(
        status_code=201,
        json={
            "id": "dpl_abc123456",
            "url": "validator-hq-saas.vercel.app",
            "name": "validator-hq-saas",
            "readyState": "READY",
        },
        request=httpx.Request("POST", "https://api.vercel.com/v13/deployments"),
    )
    mock_sso_response = httpx.Response(
        status_code=200,
        json={"ssoProtection": None},
        request=httpx.Request("PATCH", "https://api.vercel.com/v9/projects/validator-hq-saas"),
    )

    async def mock_post(*args: Any, **kwargs: Any) -> httpx.Response:
        return mock_deploy_response

    async def mock_patch(*args: Any, **kwargs: Any) -> httpx.Response:
        return mock_sso_response

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.patch = AsyncMock(side_effect=mock_patch)

    settings.REAL_MAIL_ENABLED = True
    settings.NOTION_MCP_ENABLED = True

    with (
        patch("app.services.vercel_deployer.RealMailBridge") as mock_mail_cls,
        patch("app.services.vercel_deployer.get_knowledge_sync_adapter") as mock_notion_fn,
    ):
        mock_bridge_instance = AsyncMock()
        mock_mail_cls.return_value = mock_bridge_instance

        mock_notion_instance = AsyncMock()
        mock_notion_fn.return_value = mock_notion_instance

        deployer = VercelDeployerService(client=mock_client)
        res = await deployer.deploy_to_vercel(
            project_id="proj_success_v11",
            project_name="validator-hq-saas",
            sync_notifications=True,
        )

        assert res["success"] is True
        assert res["deployment_url"] == "https://validator-hq-saas.vercel.app"
        assert res["email_logged"] is True
        assert res["total_files"] >= 5

        # Check internal email record in store
        inbox = await store.get_emails(project_id="proj_success_v11")
        assert len(inbox) == 1
        email = inbox[0]
        assert email.sender == "agente_07_devops@agentoffice.local"
        assert email.recipient == "ceo@agentoffice.local"
        assert email.priority == "HIGH"
        assert "validator-hq-saas.vercel.app" in email.subject

        # Check RealMailBridge call
        mock_bridge_instance.sync_email_record.assert_awaited_once()

        # Check Notion update call
        mock_notion_instance.update_project_status.assert_awaited_once_with(
            project_id="proj_success_v11",
            status_data={"status": "DESPLEGADO_VERCEL - https://validator-hq-saas.vercel.app"},
        )


# =====================================================================
# 4. CLI & REST API Route Integration Tests
# =====================================================================


@pytest.mark.asyncio
async def test_cli_deploy_vercel_command(phase11_env: dict[str, Any]) -> None:
    """Verify deploy_vercel_command executes cleanly and logs formatted CLI summary."""
    workspaces = phase11_env["workspaces"]
    proj_dir = workspaces / "proj_cli_v11"
    proj_dir.mkdir(parents=True, exist_ok=True)

    fake_result = {
        "success": True,
        "project_id": "proj_cli_v11",
        "project_name": "custom-validator-cli",
        "deployment_url": "https://custom-validator-cli.vercel.app",
        "bundle_path": str(proj_dir / "vercel_dist"),
        "total_files": 6,
        "email_logged": True,
        "error": None,
    }

    with patch.object(
        VercelDeployerService,
        "deploy_to_vercel",
        new=AsyncMock(return_value=fake_result),
    ):
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            await deploy_vercel_command("proj_cli_v11", name="custom-validator-cli")
            output = fake_out.getvalue()
            assert "Despliegue Serverless en Vercel Cloud" in output
            assert "https://custom-validator-cli.vercel.app" in output
            assert "Archivos Desplegados: 6" in output


@pytest.mark.asyncio
async def test_api_deploy_vercel_endpoint(phase11_env: dict[str, Any]) -> None:
    """Test POST /api/v1/projects/{project_id}/deploy-vercel REST endpoint."""
    workspaces = phase11_env["workspaces"]
    proj_dir = workspaces / "proj_api_route"
    proj_dir.mkdir(parents=True, exist_ok=True)

    fake_result = {
        "success": True,
        "project_id": "proj_api_route",
        "project_name": "validator-hq-saas",
        "deployment_url": "https://validator-hq-saas.vercel.app",
        "bundle_path": str(proj_dir / "vercel_dist"),
        "total_files": 6,
        "email_logged": True,
        "error": None,
    }

    async with lifespan(main_app):
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Non-existent project -> 404
            resp_404 = await client.post("/api/v1/projects/proj_non_existent/deploy-vercel")
            assert resp_404.status_code == 404

            # 2. Existing project with mocked success -> 200
            with patch.object(
                VercelDeployerService,
                "deploy_to_vercel",
                new=AsyncMock(return_value=fake_result),
            ):
                resp = await client.post(
                    "/api/v1/projects/proj_api_route/deploy-vercel",
                    json={"name": "validator-hq-saas"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["deployment_url"] == "https://validator-hq-saas.vercel.app"
                assert data["total_files"] == 6

            # 3. Existing project with failure -> 400
            fail_result = {
                "success": False,
                "project_id": "proj_api_route",
                "project_name": "validator-hq-saas",
                "deployment_url": None,
                "bundle_path": str(proj_dir / "vercel_dist"),
                "total_files": 0,
                "email_logged": False,
                "error": "Falta configurar VERCEL_TOKEN.",
            }
            with patch.object(
                VercelDeployerService,
                "deploy_to_vercel",
                new=AsyncMock(return_value=fail_result),
            ):
                resp_fail = await client.post("/api/v1/projects/proj_api_route/deploy-vercel")
                assert resp_fail.status_code == 400
                assert "VERCEL_TOKEN" in resp_fail.json()["detail"]
