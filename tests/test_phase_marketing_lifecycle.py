"""Unit and integration tests for Phase 1: Configurable Multi-Project Marketing Lifecycle.

Validates:
1. Default presets generation across all archetypes.
2. OfficeStore persistence, multi-project isolation, and credential preservation across presets.
3. API project creation with and without marketing suite.
4. Real-time LangGraph routing decisions when toggling marketing on/off mid-execution.
5. Office REST API endpoints (/api/office/marketing/*).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.graph.router import (
    NODE_CEO_SIGNOFF,
    route_after_ceo_signoff,
    route_after_docs,
    route_after_growth,
    route_after_marketing,
    route_after_sales_analytics,
)
from app.graph.state import create_initial_state
from app.main import create_app
from app.schemas.office import ProjectMarketingProfile
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.office_store import OfficeStore, get_marketing_preset
from app.services.orchestrator_service import OrchestratorService


def test_presets_generation_and_archetypes() -> None:
    """Verify channel and tool defaults for each marketing archetype."""
    # 1. "none" preset
    none_preset = get_marketing_preset("none", project_id="proj_none")
    assert none_preset.marketing_enabled is False
    assert none_preset.include_growth_agent is False
    assert none_preset.include_sales_analytics_agent is False
    assert all(not ch.enabled for ch in none_preset.channels)
    assert all(not t.enabled for t in none_preset.tools)

    # 2. "saas_b2b" preset
    saas_preset = get_marketing_preset("saas_b2b", project_id="proj_saas")
    assert saas_preset.marketing_enabled is True
    assert saas_preset.include_growth_agent is True
    assert saas_preset.include_sales_analytics_agent is True
    active_channels_saas = {ch.channel_id for ch in saas_preset.channels if ch.enabled}
    assert active_channels_saas == {
        "linkedin",
        "x_twitter",
        "producthunt",
        "google_ads",
        "email_newsletter",
    }
    active_tools_saas = {t.tool_id for t in saas_preset.tools if t.enabled}
    assert active_tools_saas == {
        "market_research_seo",
        "seo_landing_injector",
        "email_campaign_manager",
        "social_ads_publisher",
    }

    # 3. "b2c_app_ecommerce" preset
    b2c_preset = get_marketing_preset("b2c_app_ecommerce", project_id="proj_b2c")
    assert b2c_preset.marketing_enabled is True
    active_channels_b2c = {ch.channel_id for ch in b2c_preset.channels if ch.enabled}
    assert active_channels_b2c == {
        "instagram_meta",
        "tiktok",
        "google_ads",
        "email_newsletter",
        "x_twitter",
    }

    # 4. "devtools_api" preset
    dev_preset = get_marketing_preset("devtools_api", project_id="proj_dev")
    assert dev_preset.marketing_enabled is True
    active_channels_dev = {ch.channel_id for ch in dev_preset.channels if ch.enabled}
    assert active_channels_dev == {
        "producthunt",
        "reddit_devto",
        "x_twitter",
        "linkedin",
        "telegram_discord",
    }
    active_tools_dev = {t.tool_id for t in dev_preset.tools if t.enabled}
    assert "email_campaign_manager" not in active_tools_dev
    assert "market_research_seo" in active_tools_dev

    # 5. "internal_rollout" preset
    internal_preset = get_marketing_preset("internal_rollout", project_id="proj_internal")
    assert internal_preset.marketing_enabled is True
    assert internal_preset.include_growth_agent is False
    assert internal_preset.include_sales_analytics_agent is False
    active_channels_internal = {ch.channel_id for ch in internal_preset.channels if ch.enabled}
    assert active_channels_internal == {"email_newsletter", "telegram_discord"}
    active_tools_internal = {t.tool_id for t in internal_preset.tools if t.enabled}
    assert active_tools_internal == {"email_campaign_manager"}


@pytest.mark.asyncio
async def test_office_store_multi_project_credential_isolation(tmp_path: Path) -> None:
    """Verify distinct projects maintain strict isolation of channels and credentials in SQLite."""
    db_file = tmp_path / "marketing_isolation.db"
    store = OfficeStore(db_path=db_file)
    await store.init_db()

    # Project Alpha
    alpha = get_marketing_preset("saas_b2b", project_id="proj_alpha", project_name="Alpha SaaS")
    for ch in alpha.channels:
        if ch.channel_id == "linkedin":
            ch.account_handle_or_url = "company/alpha-saas"
            ch.credentials = {"client_id": "alpha_linkedin_key"}
    for t in alpha.tools:
        if t.tool_id == "market_research_seo":
            t.credentials = {"search_api_key": "alpha_search_key"}
    await store.save_project_marketing_config("proj_alpha", alpha)

    # Project Beta
    beta = get_marketing_preset(
        "b2c_app_ecommerce", project_id="proj_beta", project_name="Beta Shop"
    )
    for ch in beta.channels:
        if ch.channel_id == "instagram_meta":
            ch.account_handle_or_url = "@beta_official"
            ch.credentials = {"access_token": "beta_instagram_token"}
    for t in beta.tools:
        if t.tool_id == "market_research_seo":
            t.credentials = {"search_api_key": "beta_search_key"}
    await store.save_project_marketing_config("proj_beta", beta)

    # Fetch and verify isolation
    retrieved_alpha = await store.get_project_marketing_config("proj_alpha")
    retrieved_beta = await store.get_project_marketing_config("proj_beta")

    assert retrieved_alpha.project_name == "Alpha SaaS"
    assert retrieved_beta.project_name == "Beta Shop"

    alpha_li = next(c for c in retrieved_alpha.channels if c.channel_id == "linkedin")
    assert alpha_li.credentials.get("client_id") == "alpha_linkedin_key"
    assert alpha_li.account_handle_or_url == "company/alpha-saas"

    beta_ig = next(c for c in retrieved_beta.channels if c.channel_id == "instagram_meta")
    assert beta_ig.credentials.get("access_token") == "beta_instagram_token"
    assert beta_ig.account_handle_or_url == "@beta_official"

    alpha_tool = next(t for t in retrieved_alpha.tools if t.tool_id == "market_research_seo")
    beta_tool = next(t for t in retrieved_beta.tools if t.tool_id == "market_research_seo")
    assert alpha_tool.credentials.get("search_api_key") == "alpha_search_key"
    assert beta_tool.credentials.get("search_api_key") == "beta_search_key"

    # List marketing projects
    proj_list = await store.list_marketing_projects()
    assert len(proj_list) == 2
    pids = {p["project_id"] for p in proj_list}
    assert pids == {"proj_alpha", "proj_beta"}


@pytest.mark.asyncio
async def test_apply_preset_preserves_existing_credentials(tmp_path: Path) -> None:
    """Verify that applying a new preset preserves customized credentials, URLs and instructions."""
    db_file = tmp_path / "marketing_presets_preserve.db"
    store = OfficeStore(db_path=db_file)
    await store.init_db()

    project_id = "proj_transform"
    initial = get_marketing_preset("devtools_api", project_id=project_id)
    for ch in initial.channels:
        if ch.channel_id == "x_twitter":
            ch.account_handle_or_url = "@devtools_hq"
            ch.credentials = {"bearer_token": "token_x_secret"}
            ch.custom_instructions = "Tono para hackers"
    for t in initial.tools:
        if t.tool_id == "social_ads_publisher":
            t.credentials = {"ads_api_key": "ads_secret_999"}

    await store.save_project_marketing_config(project_id, initial)

    # Apply "saas_b2b" preset
    updated = await store.apply_preset_to_project(project_id, "saas_b2b")
    assert updated.marketing_type == "saas_b2b"
    assert updated.marketing_enabled is True

    # Check preserved X / Twitter credentials
    x_ch = next(c for c in updated.channels if c.channel_id == "x_twitter")
    assert x_ch.account_handle_or_url == "@devtools_hq"
    assert x_ch.credentials.get("bearer_token") == "token_x_secret"
    assert x_ch.custom_instructions == "Tono para hackers"

    # Check preserved ads credentials
    ads_t = next(t for t in updated.tools if t.tool_id == "social_ads_publisher")
    assert ads_t.credentials.get("ads_api_key") == "ads_secret_999"


@pytest.mark.asyncio
async def test_realtime_routing_marketing_toggle(tmp_path: Path) -> None:
    """Verify LangGraph router reacts to real-time marketing configuration in SQLite."""
    db_file = tmp_path / "marketing_router_test.db"
    store = OfficeStore(db_path=db_file)
    await store.init_db()

    project_id = "proj_dynamic_routing"
    state = create_initial_state(
        project_id=project_id,
        idea_inicial="SaaS con activación bajo demanda de marketing.",
    )
    state["_office_db_path"] = str(db_file)

    # 1. Project starts with marketing disabled
    profile_off = get_marketing_preset("none", project_id=project_id)
    profile_off.marketing_enabled = False
    await store.save_project_marketing_config(project_id, profile_off)

    # Router must bypass all marketing agents directly to CEO signoff
    next_node = route_after_docs(state)
    assert next_node == NODE_CEO_SIGNOFF

    # 2. User enables marketing dynamically mid-process (e.g. via Office UI)
    profile_on = get_marketing_preset("saas_b2b", project_id=project_id)
    profile_on.marketing_enabled = True
    profile_on.include_growth_agent = True
    profile_on.include_sales_analytics_agent = True
    await store.save_project_marketing_config(project_id, profile_on)

    # Router now routes to 09_growth
    next_node_updated = route_after_docs(state)
    assert next_node_updated == AgentID.AGENTE_09_GROWTH.value

    # From growth, route to 12_marketing
    next_after_growth = route_after_growth(state)
    assert next_after_growth == AgentID.AGENTE_12_MARKETING.value

    # From marketing, route to 13_sales_analytics
    next_after_marketing = route_after_marketing(state)
    assert next_after_marketing == AgentID.AGENTE_13_SALES_ANALYTICS.value

    # From sales analytics, route to CEO Signoff
    next_after_sales = route_after_sales_analytics(state)
    assert next_after_sales == NODE_CEO_SIGNOFF

    # 3. If user disables sales analytics agent, router skips to CEO Signoff
    profile_on.include_sales_analytics_agent = False
    await store.save_project_marketing_config(project_id, profile_on)
    assert route_after_marketing(state) == NODE_CEO_SIGNOFF

    # 4. If CEO signoff blocks due to marketing culprit, check config enforcement
    state["ceo_blocked"] = True
    state["status_ceo"] = DeliverableStatus.LANZAMIENTO_BLOQUEADO_REWORK
    state["ceo_culprit"] = AgentID.AGENTE_12_MARKETING
    state["version_iteracion"] = 1

    # While marketing is enabled, loops to Agent 12
    assert route_after_ceo_signoff(state) == AgentID.AGENTE_12_MARKETING.value

    # If marketing is turned off, CEO signoff does not route to disabled marketing agent
    profile_on.marketing_enabled = False
    await store.save_project_marketing_config(project_id, profile_on)
    from langgraph.graph import END
    assert route_after_ceo_signoff(state) == END


@pytest.mark.asyncio
async def test_create_project_with_marketing_payload(tmp_path: Path) -> None:
    """Verify CreateProjectRequest accepts marketing_enabled and marketing_type and saves preset."""
    db_file = tmp_path / "marketing_create_project.db"
    store = OfficeStore(db_path=db_file)
    await store.init_db()

    app = create_app()
    mock_orchestrator = MagicMock(spec=OrchestratorService)
    mock_orchestrator.start_project = AsyncMock()
    app.state.orchestrator = mock_orchestrator

    with patch("app.api.routes.OfficeStore", return_value=store):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create project without marketing
            resp1 = await client.post(
                "/api/v1/projects",
                json={
                    "idea_inicial": "Herramienta interna de CLI sin componentes de marketing.",
                    "marketing_enabled": False,
                    "marketing_type": "none",
                },
            )
            assert resp1.status_code == 202
            pid1 = resp1.json()["project_id"]
            cfg1 = await store.get_project_marketing_config(pid1)
            assert cfg1.marketing_enabled is False
            assert cfg1.marketing_type == "none"

            # 2. Create project with B2C marketing suite
            resp2 = await client.post(
                "/api/v1/projects",
                json={
                    "idea_inicial": "E-commerce para venta de calzado deportivo inteligente.",
                    "marketing_enabled": True,
                    "marketing_type": "b2c_app_ecommerce",
                },
            )
            assert resp2.status_code == 202
            pid2 = resp2.json()["project_id"]
            cfg2 = await store.get_project_marketing_config(pid2)
            assert cfg2.marketing_enabled is True
            assert cfg2.marketing_type == "b2c_app_ecommerce"


@pytest.mark.asyncio
async def test_marketing_office_rest_endpoints(tmp_path: Path) -> None:
    """Verify all marketing REST endpoints in routes_office.py."""
    db_file = tmp_path / "marketing_rest_api.db"
    store = OfficeStore(db_path=db_file)
    await store.init_db()

    app = create_app()

    with patch("app.api.routes_office._get_office_store", return_value=store):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. GET /api/office/marketing/presets
            res_presets = await client.get("/api/office/marketing/presets")
            assert res_presets.status_code == 200
            data_presets = res_presets.json()
            assert "available_types" in data_presets
            assert "channels_catalog" in data_presets
            assert "tools_catalog" in data_presets
            assert len(data_presets["channels_catalog"]) == 9
            assert len(data_presets["tools_catalog"]) == 4

            # 2. GET /api/office/marketing/projects (empty initially)
            res_list = await client.get("/api/office/marketing/projects")
            assert res_list.status_code == 200
            assert res_list.json() == []

            # 3. GET /api/office/marketing/projects/{id} (returns default preset)
            res_proj = await client.get("/api/office/marketing/projects/proj_demo_99")
            assert res_proj.status_code == 200
            proj_data = res_proj.json()
            assert proj_data["project_id"] == "proj_demo_99"
            assert proj_data["marketing_enabled"] is True

            # 4. PUT /api/office/marketing/projects/{id} (hot reload update)
            proj_data["brand_voice"] = "audaz-disruptivo"
            proj_data["target_audience"] = "Startups Serie A en Silicon Valley"
            for ch in proj_data["channels"]:
                if ch["channel_id"] == "x_twitter":
                    ch["account_handle_or_url"] = "@startup_demo"
                    ch["credentials"] = {"bearer_token": "token123"}
            res_put = await client.put(
                "/api/office/marketing/projects/proj_demo_99",
                json=proj_data,
            )
            assert res_put.status_code == 200
            assert res_put.json()["brand_voice"] == "audaz-disruptivo"

            # 5. POST /api/office/marketing/projects/{id}/apply-preset/devtools_api
            res_apply = await client.post(
                "/api/office/marketing/projects/proj_demo_99/apply-preset/devtools_api"
            )
            assert res_apply.status_code == 200
            applied = res_apply.json()
            assert applied["marketing_type"] == "devtools_api"
            # Preserved handle and credentials
            x_ch = next(c for c in applied["channels"] if c["channel_id"] == "x_twitter")
            assert x_ch["account_handle_or_url"] == "@startup_demo"
            assert x_ch["credentials"]["bearer_token"] == "token123"

            # 6. POST /api/office/marketing/projects/{id}/tools/{tool_id}/test
            # Missing credentials test
            res_test_fail = await client.post(
                "/api/office/marketing/projects/proj_demo_99/tools/market_research_seo/test"
            )
            assert res_test_fail.status_code == 200
            assert res_test_fail.json()["success"] is False
            assert res_test_fail.json()["status"] == "missing_credentials"

            # Supply credentials and re-test
            applied_tools = applied["tools"]
            for t in applied_tools:
                if t["tool_id"] == "market_research_seo":
                    t["credentials"] = {"search_api_key": "valid_key_123"}
            await store.save_project_marketing_config(
                "proj_demo_99",
                ProjectMarketingProfile.model_validate(applied),
            )

            res_test_ok = await client.post(
                "/api/office/marketing/projects/proj_demo_99/tools/market_research_seo/test"
            )
            assert res_test_ok.status_code == 200
            assert res_test_ok.json()["success"] is True
            assert res_test_ok.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_marketing_frontend_ui_contracts_and_static_assets() -> None:
    """Validate Phase 3 Frontend contracts: HTML selectors, static JS and CSS rules."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Main SPA HTML check (/office)
        res_html = await client.get("/office")
        assert res_html.status_code == 200
        html = res_html.text
        # Launch selector
        assert 'id="launch-marketing-type"' in html
        assert 'value="saas_b2b"' in html
        assert 'value="b2c_app_ecommerce"' in html
        assert 'value="devtools_api"' in html
        assert 'value="internal_rollout"' in html
        assert 'value="custom"' in html
        # Panel Tab and Content
        assert 'id="tab-btn-marketing"' in html
        assert 'data-tab="marketing"' in html
        assert 'id="tab-marketing"' in html
        # Control elements
        assert 'id="mkt-project-select"' in html
        assert 'id="btn-mkt-toggle-status"' in html
        assert 'id="btn-mkt-execute-now"' in html
        assert 'id="mkt-strategy-preset"' in html
        assert 'id="btn-mkt-apply-preset"' in html
        assert 'id="mkt-channels-matrix"' in html
        assert 'id="mkt-tools-container"' in html
        assert 'id="btn-save-marketing-profile"' in html
        # Dock button
        assert 'id="dock-btn-marketing"' in html

        # 2. Static api.js check
        res_api_js = await client.get("/static/js/api.js")
        assert res_api_js.status_code == 200
        api_js = res_api_js.text
        assert "getMarketingPresets" in api_js
        assert "getMarketingProjects" in api_js
        assert "getProjectMarketingConfig" in api_js
        assert "saveProjectMarketingConfig" in api_js
        assert "applyProjectMarketingPreset" in api_js
        assert "testProjectMarketingTool" in api_js
        assert "executeProjectMarketingNow" in api_js

        # 3. Static panel.js check
        res_panel_js = await client.get("/static/js/panel.js")
        assert res_panel_js.status_code == 200
        panel_js = res_panel_js.text
        assert "_loadMarketingTab" in panel_js
        assert "_renderMarketingProfile" in panel_js
        assert "_renderMarketingChannels" in panel_js
        assert "_renderMarketingTools" in panel_js
        assert "MARKETING_CHANNELS_META" in panel_js
        assert "MARKETING_TOOLS_META" in panel_js

        # 4. Static pixel.css check
        res_css = await client.get("/static/css/pixel.css")
        assert res_css.status_code == 200
        css = res_css.text
        assert "#tab-marketing" in css
        assert ".mkt-panel-container" in css
        assert ".mkt-channel-card" in css
        assert ".mkt-tool-card" in css
