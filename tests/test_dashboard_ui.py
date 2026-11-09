"""Tests for the Operations & Telemetry Dashboard UI and real telemetry verification."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app, lifespan


@pytest.fixture
async def dashboard_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Provide an AsyncClient instance with isolated temporary directories and zero fake data."""
    settings.USE_MOCK_LLM = True
    settings.CHECKPOINT_DB_PATH = str(tmp_path / "checkpoints_dash.sqlite")
    settings.OFFICE_DB_PATH = str(tmp_path / "office_dash.sqlite")
    settings.WORKSPACES_DIR = str(tmp_path / "workspaces_dash")
    settings.PROMPTS_DIR = str(tmp_path / "prompts_dash")

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.mark.asyncio
async def test_main_root_serves_dashboard_and_contains_no_fake_numbers(
    dashboard_client: AsyncClient,
) -> None:
    """Verify that root '/' serves the dashboard, contains all 6 tabs, and zero fake numbers."""
    response = await dashboard_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")

    html = response.text

    # 1. Verify Top Status Bar & Telemetry elements
    assert "AgentOffice — AI Factory Dashboard" in html
    assert "LIVE" in html
    assert "Projects:" in html
    assert "Tokens:" in html
    assert "Cost:" in html
    assert "Today:" in html
    assert "Saved:" in html
    assert "kpi-agents" in html
    assert "kpi-health" in html
    assert "live-clock" in html
    # Tarea 1: Sound toggle button eliminated
    assert "sound-toggle-btn" not in html

    # Verify loose '2D Office' link in header is ELIMINATED
    assert '<a href="/office"' not in html

    # 2. Strict check: ZERO hardcoded fake metrics in HTML
    for fake in ("42,500", "18,320", "$0.048", "$4,850.00", "1.82s", "142"):
        assert fake not in html, f"Found prohibited fake data '{fake}' in HTML!"

    # 3. Verify all 7 Consolidated Navigation Tabs in exact order (2D Office first)
    assert 'data-target="tab-office"' in html
    assert "2D Office" in html
    assert "Interaction &amp; Pipeline" in html or "Interaction & Pipeline" in html
    assert "Agent Thoughts" in html
    assert "Agent Usage &amp; Stats" in html or "Agent Usage & Stats" in html
    assert "Token &amp; Cost Monitor" in html or "Token & Cost Monitor" in html
    assert "Security &amp; Circuit Breakers" in html or "Security & Circuit Breakers" in html
    assert "Database &amp; Artifacts" in html or "Database & Artifacts" in html

    # 4. Verify Pestaña 1 (tab-office) Sub-toolbar & 2D Office Components per Mockup
    assert 'id="tab-office"' in html
    assert 'id="office-sub-toolbar"' in html
    # Tarea 2: Duplicate KPIs removed from sub-bar
    assert 'id="kpi-tasks-val"' not in html
    assert 'id="hud-kpis"' not in html
    assert 'data-mode="greenfield"' in html
    assert 'data-mode="brownfield"' in html
    assert 'id="idea-input"' in html
    assert 'id="btn-launch"' in html
    assert 'id="project-selector"' in html
    assert 'id="btn-refresh-projects"' in html
    assert 'id="btn-resume"' in html

    # Canvas & Viewport
    assert 'id="office-viewport"' in html
    assert 'id="office-stage"' in html
    assert 'id="office-canvas"' in html
    # Tarea 3: Camera controls positioned outside canvas frame
    assert 'id="camera-controls"' in html
    assert 'id="cam-zoom-in"' in html
    assert 'id="cam-zoom-out"' in html
    assert 'id="cam-reset"' in html
    assert 'id="cam-edit-mode"' in html

    # Right Ops Panel (Pipeline Stepper + Activity Log)
    assert 'id="right-ops-panel"' in html
    assert 'id="pipeline-stepper-widget"' in html
    assert 'id="activity-log-widget"' in html

    # Bottom Command Dock & Drawers
    # Tarea 4: Footer centered, system status texts removed
    assert 'id="bottom-command-dock"' in html
    assert 'dock-system-info' not in html
    assert 'SIN CONEXIÓN' not in html
    assert 'id="dock-btn-files"' in html
    assert 'id="dock-btn-chat"' in html
    assert 'id="dock-btn-telemetry"' in html
    assert 'id="dock-btn-decor"' in html
    assert 'id="dock-btn-brownfield"' in html
    assert 'id="side-panel"' in html
    assert 'id="decor-tray"' in html
    assert 'id="telemetry-drawer"' in html
    assert 'id="modal-overlay"' in html
    assert 'id="fab-chat"' in html

    # 5. Verify Pestaña 2 (tab-interaction) Components
    assert "Request from Boss" in html
    assert "project-idea-input" in html
    assert "Launch Factory" in html
    assert "Request Pipeline" in html
    assert "Activity Log" in html
    for filter_tag in ("User", "Tool", "Response", "Delegate", "Done"):
        assert filter_tag in html

    # 6. Verify Content Containers for Tabs 3 through 7
    assert "agent-thoughts-stream" in html
    assert "agent-stats-grid" in html
    assert "agent-cost-tbody" in html
    assert "circuit-breakers-container" in html
    assert "db-table-select" in html
    assert "artifacts-project-select" in html


@pytest.mark.asyncio
async def test_dashboard_telemetry_endpoint_real_values(
    dashboard_client: AsyncClient,
) -> None:
    """Verify that /api/dashboard/telemetry computes real metrics from zero state without mocks."""
    response = await dashboard_client.get("/api/dashboard/telemetry")
    assert response.status_code == 200
    data = response.json()

    # In clean isolated tmp_path, metrics must reflect real zero state
    assert data["projects"] == 0
    assert data["tokens"] == 0
    assert data["tokens_in"] == 0
    assert data["tokens_out"] == 0
    assert data["cost"] == "$0.0000"
    assert data["today"] == "$0.0000"
    assert data["saved"] == "$0.00"
    assert data["health_score"] == 100
    assert data["circuit_breakers_tripped"] == 0

    # Agents ready must reflect compiled StateGraph topology (13 nodes)
    assert data["agents_ready"] == 13
    assert data["agents_total"] == 13
    assert data["agents_ready_str"] == "13/13 Agents Ready"


@pytest.mark.asyncio
async def test_dashboard_static_assets_are_served(
    dashboard_client: AsyncClient,
) -> None:
    """Verify that static js file for the dashboard is accessible and contains real logic."""
    response = await dashboard_client.get("/static/js/dashboard.js")
    assert response.status_code == 200
    assert "javascript" in response.headers.get("content-type", "")
    assert "fetch('/api/dashboard/telemetry')" in response.text
    assert "renderActivityLog" in response.text
    assert "setPipelineStage" in response.text
    assert "loadThoughts" in response.text
    assert "loadAgentStats" in response.text
    assert "loadCostBreakdown" in response.text
    assert "loadSecurityStatus" in response.text
    assert "loadDatabaseTable" in response.text
