"""Unit and integration tests for Telemetry, Agent Thoughts, and Operations Dashboard APIs."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app():
    """Application fixture with configured routers."""
    return create_app()


@pytest.mark.asyncio
async def test_get_kpis_endpoint(app):
    """Confirm /api/v1/telemetry/kpis returns valid aggregated metrics."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/telemetry/kpis")
        assert response.status_code == 200
        data = response.json()
        assert "projects_count" in data
        assert "total_tokens" in data
        assert "estimated_cost_usd" in data
        assert "saved_usd" in data
        assert "health_score" in data
        assert "agents_ready" in data
        assert "agents_total" in data
        assert data["projects_count"] >= 0
        assert data["total_tokens"] >= 0
        assert 0 <= data["health_score"] <= 100


@pytest.mark.asyncio
async def test_list_agent_thoughts(app):
    """Confirm /api/v1/telemetry/thoughts returns reasoning items."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/telemetry/thoughts?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "thoughts" in data
        assert isinstance(data["thoughts"], list)


@pytest.mark.asyncio
async def test_agent_stats_endpoint(app):
    """Confirm /api/v1/telemetry/agent-stats aggregates workload per agent."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/telemetry/agent-stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_agents" in data
        assert data["total_agents"] >= 14
        assert len(data["agents"]) >= 14
        agent_names = [a["name"] for a in data["agents"]]
        assert "CEO" in agent_names
        assert "CISO" in agent_names


@pytest.mark.asyncio
async def test_cost_breakdown_endpoint(app):
    """Confirm /api/v1/telemetry/cost-breakdown computes ROI and tier economics."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/telemetry/cost-breakdown")
        assert response.status_code == 200
        data = response.json()
        assert "total_tokens" in data
        assert "total_cost_usd" in data
        assert "pricing_tiers" in data
        assert len(data["pricing_tiers"]) == 3
        starter = data["pricing_tiers"][0]
        assert starter["name"] == "Starter"
        assert starter["price_usd"] == 19.0
        assert starter["net_margin_pct"] >= 80.0


@pytest.mark.asyncio
async def test_security_breakers_endpoint(app):
    """Confirm /api/v1/telemetry/security reports circuit breaker state."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/telemetry/security")
        assert response.status_code == 200
        data = response.json()
        assert "circuit_breakers_tripped" in data
        assert "max_allowed_loops" in data
        assert data["max_allowed_loops"] == 3
        assert "projects_monitored" in data
        assert "recent_security_events" in data


@pytest.mark.asyncio
async def test_database_tables_and_query_safety(app):
    """Confirm database inspector lists tables and enforces table allowlist."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Tables list
        t_resp = await client.get("/api/v1/telemetry/database/tables")
        assert t_resp.status_code == 200
        t_data = t_resp.json()
        table_names = [t["name"] for t in t_data["tables"]]
        assert "agent_conversations" in table_names

        # 2. Query allowed table
        q_resp = await client.get(
            "/api/v1/telemetry/database/query?table=agent_conversations&limit=5"
        )
        assert q_resp.status_code == 200
        q_data = q_resp.json()
        assert q_data["table"] == "agent_conversations"
        assert "columns" in q_data

        # 3. Disallowed table rejection
        bad_resp = await client.get(
            "/api/v1/telemetry/database/query?table=sqlite_master"
        )
        assert bad_resp.status_code == 400


@pytest.mark.asyncio
async def test_artifacts_traversal_protection(app):
    """Confirm artifacts endpoint protects against path traversal."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-existent project
        resp = await client.get("/api/v1/telemetry/artifacts?project_id=proj_nonexistent_xyz")
        assert resp.status_code == 404

        # Path traversal rejection
        resp2 = await client.get(
            "/api/v1/telemetry/artifacts/content?project_id=proj_88c9fd46&file_path=../../../../etc/passwd"
        )
        assert resp2.status_code in (403, 404)
