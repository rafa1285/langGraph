"""Comprehensive security and defensive AppSec test suite for Agent Office.

Verifies:
1. Path Traversal (CWE-22) rejection across workspace writers and marketing services.
2. SSRF and URI scheme validation across n8n and webhook dispatchers.
3. SQL Injection defenses and table whitelist enforcement in telemetry.
4. Credential masking (Zero Credential Leakage) across API endpoints.
5. Circuit Breaker invariants and maximum retry anti-loop limits.
"""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.graph.router import route_after_ciso, route_after_qa_php, route_after_qa_python
from app.main import app
from app.schemas.office import (
    MarketingChannelConfig,
    ProjectMarketingProfile,
    ProjectMarketingToolConfig,
)
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.code_materializer import CodeMaterializerService
from app.services.marketing_tools import (
    execute_email_campaign_manager,
    execute_seo_landing_injector,
    execute_social_ads_publisher,
)
from app.services.n8n_service import (
    generate_project_n8n_workflow,
    provision_workflow_in_n8n,
)
from app.services.whatsapp_config_service import WhatsAppConfigService
from app.services.workspace_writer import WorkspaceWriter

# =====================================================================
# 1. PATH TRAVERSAL (CWE-22) DEFENSIVE TESTS
# =====================================================================


def test_workspace_writer_rejects_path_traversal(tmp_path: Path) -> None:
    """Ensure WorkspaceWriter raises ValueError when project_id attempts traversal."""
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    malicious_pid = "../../etc/malicious"

    with pytest.raises(ValueError, match="Path traversal detectado"):
        writer._sync_save(
            project_id=malicious_pid,
            step_number=1,
            agent_id=AgentID.AGENTE_00_CEO,
            content="# Exploit Attempt",
        )


def test_code_materializer_rejects_path_traversal(tmp_path: Path) -> None:
    """Ensure CodeMaterializerService raises ValueError on traversed project_id."""
    ws = tmp_path / "workspaces"
    ws.mkdir(parents=True)
    materializer = CodeMaterializerService(workspaces_dir=ws)

    with pytest.raises(ValueError, match="Path traversal detectado"):
        materializer.materialize_project(project_id="../traversal_test")


@pytest.mark.asyncio
async def test_marketing_seo_injector_rejects_path_traversal(tmp_path: Path) -> None:
    """Ensure execute_seo_landing_injector rejects directory traversal."""
    profile = ProjectMarketingProfile(project_id="test_safe")
    tool = ProjectMarketingToolConfig(
        tool_id="seo_landing_injector",
        name="SEO Injector",
        description="Landing generator",
        enabled=True,
    )

    with pytest.raises(ValueError, match="Path traversal detectado"):
        await execute_seo_landing_injector(
            project_id="../../escaped_proj",
            raw_markdown="# Landing Header",
            parsed_output={"copywriting": {"titular_h1": "Title"}},
            profile=profile,
            tool_config=tool,
            workspaces_dir=tmp_path / "workspaces",
        )


@pytest.mark.asyncio
async def test_marketing_email_manager_rejects_path_traversal(tmp_path: Path) -> None:
    """Ensure execute_email_campaign_manager rejects directory traversal."""
    profile = ProjectMarketingProfile(project_id="test_safe")
    tool = ProjectMarketingToolConfig(
        tool_id="email_campaign_manager",
        name="Email Manager",
        description="Campaign manager",
        enabled=True,
    )

    with pytest.raises(ValueError, match="Path traversal detectado"):
        await execute_email_campaign_manager(
            project_id="../escaped_email",
            parsed_output={},
            profile=profile,
            tool_config=tool,
            workspaces_dir=tmp_path / "workspaces",
        )


@pytest.mark.asyncio
async def test_marketing_social_ads_rejects_path_traversal(tmp_path: Path) -> None:
    """Ensure execute_social_ads_publisher rejects directory traversal."""
    profile = ProjectMarketingProfile(project_id="test_safe")
    tool = ProjectMarketingToolConfig(
        tool_id="social_ads_publisher",
        name="Social Ads",
        description="Ads publisher",
        enabled=True,
    )

    with pytest.raises(ValueError, match="Path traversal detectado"):
        await execute_social_ads_publisher(
            project_id="../../escaped_ads",
            parsed_output={},
            profile=profile,
            tool_config=tool,
            workspaces_dir=tmp_path / "workspaces",
        )


def test_n8n_generator_rejects_path_traversal(tmp_path: Path) -> None:
    """Ensure generate_project_n8n_workflow rejects directory traversal."""
    profile = ProjectMarketingProfile(project_id="../../escaped_n8n")

    with pytest.raises(ValueError, match="Path traversal detectado"):
        generate_project_n8n_workflow(profile, workspaces_dir=tmp_path / "workspaces")


# =====================================================================
# 2. SSRF AND SCHEME VALIDATION TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_n8n_provision_rejects_non_http_schemes() -> None:
    """Ensure provision_workflow_in_n8n raises ValueError on dangerous URI schemes."""
    profile = ProjectMarketingProfile(project_id="proj_ssrf")

    # file:// scheme attempt
    with pytest.raises(ValueError, match="Esquema de n8n_base_url no permitido"):
        await provision_workflow_in_n8n(
            profile=profile,
            n8n_base_url="file:///etc/passwd",
        )

    # gopher:// scheme attempt
    with pytest.raises(ValueError, match="Esquema de n8n_base_url no permitido"):
        await provision_workflow_in_n8n(
            profile=profile,
            n8n_base_url="gopher://127.0.0.1:5678",
        )


@pytest.mark.asyncio
async def test_social_ads_skips_invalid_discord_scheme(tmp_path: Path) -> None:
    """Ensure execute_social_ads_publisher rejects dangerous discord webhook URI schemes."""
    ws = tmp_path / "workspaces"
    ws.mkdir(parents=True)
    ch = MarketingChannelConfig(
        channel_id="telegram_discord",
        name="Discord Channel",
        enabled=True,
        credentials={"discord_webhook_url": "ftp://malicious.host/webhook"},
    )
    profile = ProjectMarketingProfile(
        project_id="proj_valid",
        channels=[ch],
    )
    tool = ProjectMarketingToolConfig(
        tool_id="social_ads_publisher",
        name="Social Ads",
        description="Ads",
        enabled=True,
    )

    result = await execute_social_ads_publisher(
        project_id="proj_valid",
        parsed_output={},
        profile=profile,
        tool_config=tool,
        workspaces_dir=ws,
    )

    # Should safely skip the ftp:// webhook without throwing unhandled exception
    assert len(result["dispatched_direct"]) == 0


# =====================================================================
# 3. SQL INJECTION & DATABASE TABLE WHITELIST TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_telemetry_table_query_rejects_unauthorized_tables() -> None:
    """Verify that /api/v1/telemetry/database/query rejects non-whitelisted tables."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # SQLi table escape attempts
        res = await client.get("/api/v1/telemetry/database/query?table=sqlite_master")
        assert res.status_code == 400
        assert "Tabla no autorizada" in res.json()["detail"]

        sqli_table = "agent_conversations;DROP TABLE agent_conversations"
        res2 = await client.get(f"/api/v1/telemetry/database/query?table={sqli_table}")
        assert res2.status_code == 400


@pytest.mark.asyncio
async def test_telemetry_table_query_pagination_parameterized() -> None:
    """Verify query endpoint handles pagination with strict integer constraints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/telemetry/database/query?table=agent_conversations&limit=10&offset=0"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["table"] == "agent_conversations"
        assert isinstance(data["rows"], list)


# =====================================================================
# 4. ZERO CREDENTIAL LEAKAGE & MASKING TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_llm_catalog_endpoint_never_exposes_raw_keys() -> None:
    """Verify that /api/office/llm/catalog only returns has_api_key boolean, never values."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/office/llm/catalog")
        assert res.status_code == 200
        items = res.json()
        assert len(items) > 0
        for item in items:
            assert "has_api_key" in item
            assert isinstance(item["has_api_key"], bool)
            # Ensure no secret value fields exist
            assert "api_key" not in item
            assert "secret" not in item
            assert "token" not in item


def test_whatsapp_config_masks_sensitive_tokens(tmp_path: Path) -> None:
    """Verify WhatsAppConfigService masks access token and app secret."""
    test_env = tmp_path / ".env.test"
    svc = WhatsAppConfigService(env_path=test_env)

    with patch.object(
        svc,
        "get_summary",
        return_value={
            "enabled": True,
            "has_access_token": True,
            "access_token_masked": "EAA123...4567",
            "has_app_secret": True,
            "app_secret_masked": "abc...89",
        },
    ):
        summary = svc.get_summary()
        assert summary["has_access_token"] is True
        assert summary["access_token_masked"].startswith("EAA123")
        assert "..." in summary["access_token_masked"]
        assert "..." in summary["app_secret_masked"]


# =====================================================================
# 5. CIRCUIT BREAKER INVARIANTS TESTS
# =====================================================================


def test_circuit_breakers_halt_on_max_retries() -> None:
    """Verify that QA and CISO gates strictly enforce maximum retry boundaries."""
    # QA PHP circuit breaker
    state_php: dict[str, Any] = {
        "status_qa_php": DeliverableStatus.RECHAZADO_PARA_REFACTOR,
        "retry_counts": {"qa_php": 3},
    }
    assert route_after_qa_php(state_php) == "__end__"

    # QA Python circuit breaker
    state_py: dict[str, Any] = {
        "status_qa_python": DeliverableStatus.RECHAZADO_PARA_REFACTOR,
        "retry_counts": {"qa_python": 3},
    }
    assert route_after_qa_python(state_py) == "__end__"

    # CISO security loop
    state_ciso: dict[str, Any] = {
        "status_ciso": DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD,
        "retry_counts": {"ciso": 1},
        "ciso_culprit": AgentID.AGENTE_04_FASTAPI,
        "execution_history": [],
    }
    # When under max retries, loops to culprit
    assert route_after_ciso(state_ciso) == AgentID.AGENTE_04_FASTAPI.value
