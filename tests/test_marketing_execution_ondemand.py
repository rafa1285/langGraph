"""Integration tests for Phase 2: On-demand marketing execution and multi-project tools."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.services.marketing_tools import (
    execute_email_campaign_manager,
    execute_market_research_seo,
    execute_seo_landing_injector,
    execute_social_ads_publisher,
)
from app.services.office_store import OfficeStore, get_marketing_preset


@pytest.mark.asyncio
async def test_marketing_tools_execution_distinct_archetypes(tmp_path: Path) -> None:
    """Validate that devtools_api and b2c produce strictly distinct marketing artifacts."""
    ws_dir = tmp_path / "workspaces"

    # 1. DevTools/API Project
    dev_profile = get_marketing_preset("devtools_api", project_id="proj_devtools_01")
    dev_profile.project_name = "KubeFlow CLI"
    dev_profile.brand_voice = "tecnico-minimalista"
    dev_profile.target_audience = "DevOps Platform Engineers"

    # Set up devtools tools
    landing_tool_dev = next(t for t in dev_profile.tools if t.tool_id == "seo_landing_injector")
    landing_tool_dev.settings["domain_url"] = "https://kubeflow-cli.dev"
    landing_tool_dev.settings["generate_landing_html"] = True

    social_tool_dev = next(t for t in dev_profile.tools if t.tool_id == "social_ads_publisher")
    email_tool_dev = next(t for t in dev_profile.tools if t.tool_id == "email_campaign_manager")

    parsed_dev = {"marketing_spec": "# KubeFlow CLI Docs"}
    raw_md_dev = "# KubeFlow CLI Marketing Masterplan"

    await execute_seo_landing_injector(
        project_id="proj_devtools_01",
        parsed_output=parsed_dev,
        raw_markdown=raw_md_dev,
        profile=dev_profile,
        tool_config=landing_tool_dev,
        workspaces_dir=ws_dir,
    )
    await execute_social_ads_publisher(
        project_id="proj_devtools_01",
        parsed_output=parsed_dev,
        profile=dev_profile,
        tool_config=social_tool_dev,
        workspaces_dir=ws_dir,
    )
    await execute_email_campaign_manager(
        project_id="proj_devtools_01",
        parsed_output=parsed_dev,
        profile=dev_profile,
        tool_config=email_tool_dev,
        workspaces_dir=ws_dir,
    )

    # 2. B2C App / E-commerce Project
    b2c_profile = get_marketing_preset("b2c_app_ecommerce", project_id="proj_b2c_01")
    b2c_profile.project_name = "GlowFit Mobile"
    b2c_profile.brand_voice = "energetico-aspiracional"
    b2c_profile.target_audience = "Millennials & Gen Z Fitness Enthusiasts"

    landing_tool_b2c = next(t for t in b2c_profile.tools if t.tool_id == "seo_landing_injector")
    landing_tool_b2c.settings["domain_url"] = "https://glowfit.app"
    landing_tool_b2c.settings["generate_landing_html"] = True
    landing_tool_b2c.credentials = {
        "meta_pixel_id": "meta_pixel_888999",
        "tiktok_pixel_id": "tiktok_pixel_111222",
    }

    social_tool_b2c = next(t for t in b2c_profile.tools if t.tool_id == "social_ads_publisher")
    email_tool_b2c = next(t for t in b2c_profile.tools if t.tool_id == "email_campaign_manager")

    parsed_b2c = {"marketing_spec": "# GlowFit App"}
    raw_md_b2c = "# GlowFit App Marketing Masterplan"

    await execute_seo_landing_injector(
        project_id="proj_b2c_01",
        parsed_output=parsed_b2c,
        raw_markdown=raw_md_b2c,
        profile=b2c_profile,
        tool_config=landing_tool_b2c,
        workspaces_dir=ws_dir,
    )
    await execute_social_ads_publisher(
        project_id="proj_b2c_01",
        parsed_output=parsed_b2c,
        profile=b2c_profile,
        tool_config=social_tool_b2c,
        workspaces_dir=ws_dir,
    )
    await execute_email_campaign_manager(
        project_id="proj_b2c_01",
        parsed_output=parsed_b2c,
        profile=b2c_profile,
        tool_config=email_tool_b2c,
        workspaces_dir=ws_dir,
    )

    # 3. Assertions on DevTools artifacts
    dev_marketing_dir = ws_dir / "proj_devtools_01" / "marketing"
    assert (dev_marketing_dir / "marketing_master_plan.md").exists()
    assert (dev_marketing_dir / "landing_page.html").exists()
    assert (dev_marketing_dir / "channels_payload.json").exists()

    dev_landing_html = (dev_marketing_dir / "landing_page.html").read_text(encoding="utf-8")
    assert "Developer-First Infrastructure" in dev_landing_html
    assert "bg-black" in dev_landing_html
    assert "curl -X POST" in dev_landing_html
    assert "meta_pixel_888999" not in dev_landing_html
    assert "tiktok_pixel_111222" not in dev_landing_html

    dev_channels = json.loads(
        (dev_marketing_dir / "channels_payload.json").read_text(encoding="utf-8")
    )
    dev_channel_ids = [c["channel_id"] for c in dev_channels["channels"]]
    assert "producthunt" in dev_channel_ids
    assert "reddit_devto" in dev_channel_ids
    assert "tiktok" not in dev_channel_ids
    assert "instagram_meta" not in dev_channel_ids

    # 4. Assertions on B2C App artifacts
    b2c_marketing_dir = ws_dir / "proj_b2c_01" / "marketing"
    assert (b2c_marketing_dir / "marketing_master_plan.md").exists()
    assert (b2c_marketing_dir / "landing_page.html").exists()
    assert (b2c_marketing_dir / "channels_payload.json").exists()

    b2c_landing_html = (b2c_marketing_dir / "landing_page.html").read_text(encoding="utf-8")
    assert "Meta Pixel Code" in b2c_landing_html
    assert "meta_pixel_888999" in b2c_landing_html
    assert "TikTok Pixel Code" in b2c_landing_html
    assert "tiktok_pixel_111222" in b2c_landing_html
    assert "Claim 30-Day Risk-Free Trial" in b2c_landing_html
    assert "Developer-First" not in b2c_landing_html

    b2c_channels = json.loads(
        (b2c_marketing_dir / "channels_payload.json").read_text(encoding="utf-8")
    )
    b2c_channel_ids = [c["channel_id"] for c in b2c_channels["channels"]]
    assert "instagram_meta" in b2c_channel_ids
    assert "tiktok" in b2c_channel_ids
    assert "reddit_devto" not in b2c_channel_ids
    assert "producthunt" not in b2c_channel_ids


@pytest.mark.asyncio
async def test_market_research_seo_active_channels_filtering() -> None:
    """Verify market research only produces recommendations for active channels."""
    profile = get_marketing_preset("saas_b2b", project_id="proj_research_test")
    # Leave only 2 channels enabled
    for c in profile.channels:
        c.enabled = c.channel_id in ("linkedin", "email_newsletter")

    tool_config = next(t for t in profile.tools if t.tool_id == "market_research_seo")
    tool_config.settings["seed_keywords"] = ["crm enterprise", "sales sync"]

    res = await execute_market_research_seo(
        project_context="Automated B2B CRM data pipeline",
        profile=profile,
        tool_config=tool_config,
    )

    assert "keywords_research" in res
    assert len(res["keywords_research"]) >= 2
    rec_channel_ids = [r["channel_id"] for r in res["channel_recommendations"]]
    assert set(rec_channel_ids) == {"linkedin", "email_newsletter"}
    assert "tiktok" not in rec_channel_ids
    assert "reddit_devto" not in rec_channel_ids


@pytest.mark.asyncio
async def test_live_tool_diagnosis_endpoint(tmp_path: Path) -> None:
    """Verify live tool diagnosis returns ok or missing_credentials with latency metrics."""
    db_file = tmp_path / "marketing_diagnosis.db"
    store = OfficeStore(db_path=db_file)
    await store.init_db()

    profile = get_marketing_preset("saas_b2b", project_id="proj_diag_01")
    await store.save_project_marketing_config("proj_diag_01", profile)

    app = create_app()

    with patch("app.api.routes_office._get_office_store", return_value=store):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. SEO research without search_api_key -> missing_credentials
            res_fail = await client.post(
                "/api/office/marketing/projects/proj_diag_01/test-tool/market_research_seo"
            )
            assert res_fail.status_code == 200
            data_fail = res_fail.json()
            assert data_fail["success"] is False
            assert data_fail["status"] == "missing_credentials"
            assert data_fail["latency_ms"] is not None

            # 2. Configure credentials and test again -> ok
            tool = next(t for t in profile.tools if t.tool_id == "market_research_seo")
            tool.credentials = {"search_api_key": "tavily_test_key_123"}
            await store.save_project_marketing_config("proj_diag_01", profile)

            res_ok = await client.post(
                "/api/office/marketing/projects/proj_diag_01/test-tool/market_research_seo"
            )
            assert res_ok.status_code == 200
            data_ok = res_ok.json()
            assert data_ok["success"] is True
            assert data_ok["status"] == "ok"
            assert data_ok["latency_ms"] is not None

            # 3. Test landing page injector
            res_landing = await client.post(
                "/api/office/marketing/projects/proj_diag_01/test-tool/seo_landing_injector"
            )
            assert res_landing.status_code == 200
            assert res_landing.json()["success"] is True


@pytest.mark.asyncio
async def test_marketing_execution_ondemand_after_project_completed(tmp_path: Path) -> None:
    """Verify projects without marketing can launch on-demand marketing at any point."""
    db_file = tmp_path / "ondemand_test.db"
    store = OfficeStore(db_path=db_file)
    await store.init_db()

    ws_dir = tmp_path / "workspaces"
    project_id = "proj_legacy_zero_mkt"

    # Simulate completed deliverables in workspace
    deliv_dir = ws_dir / project_id / "deliverables"
    deliv_dir.mkdir(parents=True, exist_ok=True)
    (deliv_dir / "01_agente_01_pm.md").write_text(
        "# Pre-SDD Doc: High-performance Rust WebAssembly parser", encoding="utf-8"
    )
    (deliv_dir / "02_agente_02_architect.md").write_text(
        "# SDD: Modular WebAssembly and REST bridge", encoding="utf-8"
    )
    (deliv_dir / "08_agente_08_docs.md").write_text(
        "# RAG Docs: Integration snippets and benchmark results", encoding="utf-8"
    )

    # Initialize project with marketing disabled
    profile = get_marketing_preset("none", project_id=project_id)
    profile.marketing_enabled = False
    await store.save_project_marketing_config(project_id, profile)

    app = create_app()

    with (
        patch("app.api.routes_office._get_office_store", return_value=store),
        patch("app.core.config.settings.WORKSPACES_DIR", str(ws_dir)),
        patch("app.core.config.settings.USE_MOCK_LLM", True),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Check initial marketing status is disabled
            res_initial = await client.get(f"/api/office/marketing/projects/{project_id}")
            assert res_initial.status_code == 200
            assert res_initial.json()["marketing_enabled"] is False
            assert res_initial.json()["marketing_type"] == "none"

            # Execute on-demand marketing, activating devtools_api preset
            exec_payload = {
                "marketing_type": "devtools_api",
                "brand_voice": "ultratecnico-hacker",
                "target_audience": "Rust and WebAssembly Developers",
                "force_all_nodes": True,
            }
            res_exec = await client.post(
                f"/api/office/marketing/projects/{project_id}/execute",
                json=exec_payload,
            )
            assert res_exec.status_code == 200
            exec_data = res_exec.json()

            assert exec_data["status"] == "COMPLETED"
            assert exec_data["marketing_type"] == "devtools_api"
            assert "agente_09_growth" in exec_data["executed_nodes"]
            assert "agente_12_marketing" in exec_data["executed_nodes"]
            assert "agente_13_sales_analytics" in exec_data["executed_nodes"]

            # Verify files were generated in workspace
            mkt_folder = ws_dir / project_id / "marketing"
            assert (mkt_folder / "marketing_master_plan.md").exists()
            assert (mkt_folder / "landing_page.html").exists()
            assert (mkt_folder / "sitemap.xml").exists()
            assert (mkt_folder / "robots.txt").exists()
            assert (mkt_folder / "channels_payload.json").exists()
            # devtools_api by default disables email_campaign_manager
            assert not (mkt_folder / "email_campaigns.json").exists()

            # Now re-execute applying saas_b2b (which activates email_campaign_manager)
            res_saas = await client.post(
                f"/api/office/marketing/projects/{project_id}/execute",
                json={"marketing_type": "saas_b2b", "force_all_nodes": True},
            )
            assert res_saas.status_code == 200
            assert (mkt_folder / "email_campaigns.json").exists()

            # Check that marketing profile is now permanently updated in DB
            res_updated = await client.get(f"/api/office/marketing/projects/{project_id}")
            assert res_updated.status_code == 200
            up_data = res_updated.json()
            assert up_data["marketing_enabled"] is True
            assert up_data["marketing_type"] == "saas_b2b"
            assert up_data["last_execution_status"] == "COMPLETED"
            assert up_data["last_executed_at"] is not None
