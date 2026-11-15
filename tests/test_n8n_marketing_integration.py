"""Integration and unit tests for Phase 4: n8n Workflow Automation and Native Direct Connectors.

Validates:
1. Dynamic generation of n8n workflow JSON with Webhook node and channel output nodes.
2. Workflow provisioning against n8n REST API (and fallback) and auto-updating office_store.
3. Native direct connectors (Discord, Telegram, Dev.to) and webhook fallback.
4. REST endpoints GET /n8n-workflow and POST /n8n-provision.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.schemas.office import (
    MarketingChannelConfig,
    ProjectMarketingProfile,
    ProjectMarketingToolConfig,
)
from app.services.marketing_tools import execute_social_ads_publisher
from app.services.n8n_service import (
    generate_project_n8n_workflow,
    provision_workflow_in_n8n,
)
from app.services.office_store import OfficeStore, get_marketing_preset


def test_generate_project_n8n_workflow_structure(tmp_path: Path) -> None:
    """Verify that n8n workflow JSON is generated with proper webhook node and channel nodes."""
    profile = get_marketing_preset("saas_b2b", project_id="proj_n8n_test")
    profile.project_name = "CloudFlow AI"

    wf = generate_project_n8n_workflow(profile, workspaces_dir=tmp_path)

    assert wf["name"] == "AgentOffice Marketing - CloudFlow AI"
    assert "nodes" in wf
    assert "connections" in wf

    # 1. Webhook node
    webhook_node = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.webhook")
    assert webhook_node["parameters"]["path"] == "marketing-proj_n8n_test"
    assert webhook_node["parameters"]["httpMethod"] == "POST"

    # 2. Only active channels should have corresponding output nodes
    active_channel_ids = [c.channel_id for c in profile.channels if c.enabled]
    assert len(active_channel_ids) > 0

    channel_nodes = [n for n in wf["nodes"] if n["id"] != "node_webhook_ingest"]
    assert len(channel_nodes) == len(active_channel_ids)

    # 3. Verify connections map webhook to all channel nodes
    wb_name = webhook_node["name"]
    main_conns = wf["connections"][wb_name]["main"][0]
    connected_names = {c["node"] for c in main_conns}
    for cn in channel_nodes:
        assert cn["name"] in connected_names

    # 4. Verify file persistence in workspace
    wf_path = tmp_path / "proj_n8n_test" / "marketing" / "n8n_workflow_proj_n8n_test.json"
    assert wf_path.exists()
    saved_data = json.loads(wf_path.read_text(encoding="utf-8"))
    assert saved_data["name"] == wf["name"]


@pytest.mark.asyncio
async def test_provision_workflow_in_n8n_live_and_fallback(tmp_path: Path) -> None:
    """Verify live API provisioning with mock and fallback handling when offline."""
    db_path = tmp_path / "office_test.sqlite"
    store = OfficeStore(db_path=db_path)
    await store.init_db()

    profile = get_marketing_preset("saas_b2b", project_id="proj_prov_1")
    await store.save_project_marketing_config("proj_prov_1", profile)

    # 1. Live mock success
    mock_resp = httpx.Response(
        status_code=201,
        json={"id": "n8n_wf_9988", "name": "AgentOffice Marketing - proj_prov_1"},
        request=httpx.Request("POST", "http://localhost:5678/api/v1/workflows"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await provision_workflow_in_n8n(
            profile=profile,
            n8n_base_url="http://localhost:5678",
            n8n_api_key="api_key_xyz",
            office_store=store,
            workspaces_dir=tmp_path,
        )

    assert res["status"] == "provisioned"
    assert res["live_n8n_connected"] is True
    assert res["workflow_id"] == "n8n_wf_9988"
    assert res["webhook_url"] == "http://localhost:5678/webhook/marketing-proj_prov_1"

    # Verify auto-assignment in office_store
    updated = await store.get_project_marketing_config("proj_prov_1")
    tool = next(t for t in updated.tools if t.tool_id == "social_ads_publisher")
    assert tool.credentials["webhook_url"] == "http://localhost:5678/webhook/marketing-proj_prov_1"

    # 2. Offline fallback (connection refused)
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        res_offline = await provision_workflow_in_n8n(
            profile=profile,
            n8n_base_url="http://offline-n8n:5678",
            office_store=store,
            workspaces_dir=tmp_path,
        )

    assert res_offline["status"] == "configured_local"
    assert res_offline["live_n8n_connected"] is False
    assert res_offline["workflow_id"] == "local_wf_proj_prov_1"
    assert res_offline["webhook_url"] == "http://offline-n8n:5678/webhook/marketing-proj_prov_1"


@pytest.mark.asyncio
async def test_execute_social_ads_direct_native_connectors(tmp_path: Path) -> None:
    """Test native direct dispatch for Discord, Telegram, and Dev.to vs Webhook fallback."""
    channels = [
        MarketingChannelConfig(
            channel_id="telegram_discord",
            name="Telegram & Discord",
            enabled=True,
            credentials={"discord_webhook_url": "https://discord.com/api/webhooks/123/abc"},
        ),
        MarketingChannelConfig(
            channel_id="reddit_devto",
            name="Reddit & Dev.to",
            enabled=True,
            credentials={"devto_api_key": "devto_secret_key"},
        ),
        MarketingChannelConfig(
            channel_id="linkedin",
            name="LinkedIn",
            enabled=True,
            credentials={"webhook_url": "https://n8n.local/webhook/marketing-proj_test"},
        ),
    ]

    tool_config = ProjectMarketingToolConfig(
        tool_id="social_ads_publisher",
        name="Social Ads",
        description="Publisher",
        enabled=True,
        credentials={"webhook_url": "https://n8n.local/webhook/marketing-proj_test"},
    )

    profile = ProjectMarketingProfile(
        project_id="proj_direct_test",
        project_name="DirectApp",
        marketing_enabled=True,
        channels=channels,
        tools=[tool_config],
    )

    mock_resp = httpx.Response(
        status_code=200,
        text='{"ok": true}',
        request=httpx.Request("POST", "https://mock.url"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as m_post:
        result = await execute_social_ads_publisher(
            project_id="proj_direct_test",
            parsed_output={},
            profile=profile,
            tool_config=tool_config,
            workspaces_dir=tmp_path,
        )

    assert result["status"] == "ok"
    assert len(result["dispatched_direct"]) >= 2
    connectors = {d["connector"] for d in result["dispatched_direct"]}
    assert "discord_native" in connectors
    assert "devto_native" in connectors

    assert len(result["dispatched_webhooks"]) == 1
    assert result["dispatched_webhooks"][0]["channel_id"] == "linkedin"
    assert m_post.call_count == 3


@pytest.mark.asyncio
async def test_rest_endpoints_n8n_workflow_and_provision(tmp_path: Path) -> None:
    """Test GET /n8n-workflow and POST /n8n-provision endpoints."""
    db_path = tmp_path / "office_n8n_api.sqlite"
    store = OfficeStore(db_path=db_path)
    await store.init_db()

    profile = get_marketing_preset("saas_b2b", project_id="proj_api_n8n")
    await store.save_project_marketing_config("proj_api_n8n", profile)

    app = create_app()
    app.state.office_store = store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. GET /api/office/marketing/projects/{id}/n8n-workflow
        res_wf = await client.get("/api/office/marketing/projects/proj_api_n8n/n8n-workflow")
        assert res_wf.status_code == 200
        wf_data = res_wf.json()
        assert "nodes" in wf_data
        assert any(n["type"] == "n8n-nodes-base.webhook" for n in wf_data["nodes"])

        # 2. POST /api/office/marketing/projects/{id}/n8n-provision
        mock_resp = httpx.Response(
            status_code=201,
            json={"id": "wf_prov_456"},
            request=httpx.Request("POST", "http://localhost:5678/api/v1/workflows"),
        )
        mock_http = AsyncMock()
        mock_http.__aenter__.return_value = mock_http
        mock_http.__aexit__.return_value = None
        mock_http.post.return_value = mock_resp

        with patch("app.services.n8n_service.httpx.AsyncClient", return_value=mock_http):
            res_prov = await client.post(
                "/api/office/marketing/projects/proj_api_n8n/n8n-provision",
                json={"n8n_base_url": "http://localhost:5678", "n8n_api_key": "test_key"},
            )

        assert res_prov.status_code == 200
        prov_data = res_prov.json()
        assert prov_data["status"] == "provisioned"
        assert prov_data["workflow_id"] == "wf_prov_456"
        assert "webhook/marketing-proj_api_n8n" in prov_data["webhook_url"]
