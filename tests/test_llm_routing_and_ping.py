"""Tests for dynamic LLM models catalog, agent routing chains, test ping, and fallbacks."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app, lifespan
from app.schemas.office import (
    AgentLLMConfigUpdate,
    AssignedModelItem,
    LLMModelCatalogCreate,
)
from app.schemas.routing import AgentID
from app.services.llm_gateway import GeminiLLMGateway
from app.services.office_store import OfficeStore


@pytest.fixture
async def llm_test_env(tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    """Configure isolated environment with temporary database and initialized app."""
    office_db = tmp_path / "office_data.sqlite"
    checkpoint_db = tmp_path / "checkpoints.sqlite"
    workspaces_dir = tmp_path / "workspaces"
    prompts_dir = tmp_path / "prompts"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    settings.USE_MOCK_LLM = False
    settings.OFFICE_DB_PATH = str(office_db)
    settings.CHECKPOINT_DB_PATH = str(checkpoint_db)
    settings.WORKSPACES_DIR = str(workspaces_dir)
    settings.PROMPTS_DIR = str(prompts_dir)
    settings.GEMINI_API_KEY = "test-gemini-key"

    store = OfficeStore(db_path=office_db)
    await store.init_db()

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield {
                "client": client,
                "store": store,
                "tmp_path": tmp_path,
            }


# ── Catalog CRUD Tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_catalog_seed_and_list(llm_test_env: dict[str, Any]) -> None:
    """Test that the global LLM catalog is seeded with 15 models and can be retrieved."""
    client: AsyncClient = llm_test_env["client"]

    # Both /api/office/llm/catalog and /api/v1/office/llm/catalog should work
    res = await client.get("/api/office/llm/catalog")
    assert res.status_code == 200
    models = res.json()
    assert len(models) >= 15

    model_ids = [m["model_id"] for m in models]
    assert "gemini-3.6-flash" in model_ids
    assert "codestral-latest" in model_ids
    assert "qwen/qwen3-32b" in model_ids
    assert "mistral-large-latest" in model_ids

    # Check credential presence calculation
    gemini_entry = next(m for m in models if m["model_id"] == "gemini-3.6-flash")
    assert gemini_entry["has_api_key"] is True
    assert gemini_entry["tier"] == "free"

    # Prefix /api/v1/office/llm/catalog should also work
    res_v1 = await client.get("/api/v1/office/llm/catalog")
    assert res_v1.status_code == 200
    assert len(res_v1.json()) == len(models)


@pytest.mark.asyncio
async def test_llm_catalog_create_update_delete(llm_test_env: dict[str, Any]) -> None:
    """Test full CRUD operations on LLM catalog items."""
    client: AsyncClient = llm_test_env["client"]

    # 1. Create a new custom model
    new_model = {
        "model_id": "custom/deep-reasoner-70b",
        "display_name": "Deep Reasoner 70B",
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "tier": "paid",
        "default_temperature": 0.3,
        "default_max_tokens": 8192,
        "is_active": True,
    }
    create_res = await client.post("/api/office/llm/catalog", json=new_model)
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["model_id"] == "custom/deep-reasoner-70b"
    assert created_data["tier"] == "paid"

    # 2. Duplicate create returns 409 Conflict
    dup_res = await client.post("/api/office/llm/catalog", json=new_model)
    assert dup_res.status_code == 409

    # 3. Update existing model
    update_res = await client.put(
        "/api/office/llm/catalog/custom/deep-reasoner-70b",
        json={"display_name": "Deep Reasoner 70B v2", "default_temperature": 0.4},
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["display_name"] == "Deep Reasoner 70B v2"
    assert updated_data["default_temperature"] == 0.4

    # 4. Delete model
    del_res = await client.delete("/api/office/llm/catalog/custom/deep-reasoner-70b")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # 5. Get deleted model returns 404
    update_del = await client.put(
        "/api/office/llm/catalog/custom/deep-reasoner-70b",
        json={"display_name": "Gone"},
    )
    assert update_del.status_code == 404


# ── Agent Configuration & Normalization Tests ───────────────────────────────


@pytest.mark.asyncio
async def test_agent_llm_config_seed_and_normalization(llm_test_env: dict[str, Any]) -> None:
    """Test retrieving agent LLM configuration with aliases and default seed chains."""
    client: AsyncClient = llm_test_env["client"]

    # Test short alias "02_architect" resolves correctly
    res1 = await client.get("/api/office/agents/02_architect/llm-config")
    assert res1.status_code == 200
    cfg1 = res1.json()
    assert cfg1["agent_id"] == "agente_02_architect"

    # Chain check for 02_architect:
    # 1º gemini-3.5-pro -> 2º gemini-3.6-flash -> 3º mistral-large-latest
    assigned = cfg1["assigned_models"]
    assert len(assigned) >= 3
    assert assigned[0]["model_id"] == "gemini-3.5-pro"
    assert assigned[0]["enabled"] is True
    assert assigned[0]["priority"] == 1
    assert assigned[1]["model_id"] == "gemini-3.6-flash"
    assert assigned[2]["model_id"] == "mistral-large-latest"

    # Test short alias "10_ciso"
    res2 = await client.get("/api/office/agents/10_ciso/llm-config")
    assert res2.status_code == 200
    cfg2 = res2.json()
    assert cfg2["assigned_models"][0]["model_id"] == "gemini-3.5-pro"
    assert cfg2["assigned_models"][1]["model_id"] == "mistral-large-latest"
    assert cfg2["assigned_models"][2]["model_id"] == "qwen/qwen3-32b"

    # Test canonical ID "agente_00_ceo"
    res3 = await client.get("/api/office/agents/agente_00_ceo/llm-config")
    assert res3.status_code == 200
    cfg3 = res3.json()
    assert cfg3["assigned_models"][0]["model_id"] == "meta-llama/llama-4-scout-17b-16e-instruct"


@pytest.mark.asyncio
async def test_agent_llm_config_update_and_reset(llm_test_env: dict[str, Any]) -> None:
    """Test modifying agent LLM priorities, toggles, and resetting to factory defaults."""
    client: AsyncClient = llm_test_env["client"]

    # 1. Update 03_laravel config: swap order, change temp
    update_payload = {
        "assigned_models": [
            {"model_id": "codestral-latest", "enabled": True, "priority": 1},
            {"model_id": "gemini-3.6-flash", "enabled": True, "priority": 2},
            {"model_id": "qwen/qwen3-32b", "enabled": False, "priority": 3},
        ],
        "temperature": 0.15,
        "max_tokens": 2048,
        "timeout": 45,
        "max_retries": 2,
    }
    put_res = await client.put("/api/office/agents/03_laravel_dev/llm-config", json=update_payload)
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["temperature"] == 0.15
    assert data["timeout"] == 45
    assert data["max_retries"] == 2
    assert data["assigned_models"][0]["model_id"] == "codestral-latest"
    assert data["assigned_models"][2]["enabled"] is False

    # 2. Reset back to defaults
    reset_res = await client.post("/api/office/agents/03_laravel_dev/llm-config/reset")
    assert reset_res.status_code == 200
    reset_data = reset_res.json()
    # Factory default: 1º gemini-3.6-flash -> 2º codestral-latest
    assert reset_data["assigned_models"][0]["model_id"] == "gemini-3.6-flash"
    assert reset_data["assigned_models"][1]["model_id"] == "codestral-latest"


# ── Diagnostic Ping Tests (Simulating 200, 429, Auth Error, Missing Key) ────


@pytest.mark.asyncio
async def test_ping_model_missing_api_key(llm_test_env: dict[str, Any]) -> None:
    """Test that pinging a model without an API key immediately returns status=missing_api_key."""
    client: AsyncClient = llm_test_env["client"]

    # mistral-large-latest uses MISTRAL_API_KEY, which is not set in test environment
    res = await client.post("/api/office/llm/ping/mistral-large-latest")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["status"] == "missing_api_key"
    assert "MISTRAL_API_KEY" in data["message"]


@pytest.mark.asyncio
async def test_ping_model_200_ok(llm_test_env: dict[str, Any]) -> None:
    """Test diagnostic ping capturing simulated HTTP 200 OK with latency."""
    client: AsyncClient = llm_test_env["client"]

    with patch.object(
        GeminiLLMGateway,
        "_execute_diagnostic_http",
        new_callable=AsyncMock,
        return_value=(200, 185, '{"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}'),
    ):
        res = await client.post("/api/office/llm/ping/gemini-3.6-flash")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["status"] == "ok"
        assert data["http_status"] == 200
        assert data["latency_ms"] == 185
        assert "Conectado" in data["message"]


@pytest.mark.asyncio
async def test_ping_model_429_rate_limited(llm_test_env: dict[str, Any]) -> None:
    """Test diagnostic ping capturing simulated HTTP 429 Rate Limit error."""
    client: AsyncClient = llm_test_env["client"]

    with patch.object(
        GeminiLLMGateway,
        "_execute_diagnostic_http",
        new_callable=AsyncMock,
        return_value=(429, 95, "Quota limit reached"),
    ):
        res = await client.post("/api/office/llm/ping/gemini-3.6-flash")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["status"] == "rate_limited"
        assert data["http_status"] == 429
        assert "429" in data["message"]


@pytest.mark.asyncio
async def test_ping_model_auth_error_and_timeout(llm_test_env: dict[str, Any]) -> None:
    """Test diagnostic ping capturing HTTP 401 Auth Error and timeout."""
    client: AsyncClient = llm_test_env["client"]

    # 1. 401 Auth Error
    with patch.object(
        GeminiLLMGateway,
        "_execute_diagnostic_http",
        new_callable=AsyncMock,
        return_value=(401, 75, "Invalid API key"),
    ):
        res_auth = await client.post("/api/office/llm/ping/gemini-3.6-flash")
        assert res_auth.status_code == 200
        data_auth = res_auth.json()
        assert data_auth["success"] is False
        assert data_auth["status"] == "auth_error"
        assert data_auth["http_status"] == 401

    # 2. Timeout
    with patch.object(
        GeminiLLMGateway,
        "_execute_diagnostic_http",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timed out"),
    ):
        res_timeout = await client.post("/api/office/llm/ping/gemini-3.6-flash")
        assert res_timeout.status_code == 200
        data_to = res_timeout.json()
        assert data_to["success"] is False
        assert data_to["status"] == "timeout"
        assert data_to["http_status"] == 408


@pytest.mark.asyncio
async def test_ping_agent_chain(llm_test_env: dict[str, Any]) -> None:
    """Test testing an entire agent's fallback chain and resolving effective model."""
    client: AsyncClient = llm_test_env["client"]

    with patch.object(
        GeminiLLMGateway,
        "_execute_diagnostic_http",
        new_callable=AsyncMock,
        return_value=(200, 150, "OK"),
    ):
        res = await client.post("/api/office/agents/02_architect/llm-ping")
        assert res.status_code == 200
        data = res.json()
        assert data["agent_id"] == "agente_02_architect"
        assert data["all_ok"] is True
        assert data["effective_model_id"] == "gemini-3.5-pro"
        assert len(data["chain_status"]) >= 3
        assert data["chain_status"][0]["role_label"] == "Primario"
        assert data["chain_status"][1]["role_label"] == "Fallback 1"


# ── Automatic Fallback Switching in llm_gateway.py ──────────────────────────


@pytest.mark.asyncio
async def test_gateway_automatic_fallback_on_429(tmp_path: Path) -> None:
    """Test that when a primary model encounters 429, gateway immediately switches to fallback."""
    store = OfficeStore(db_path=tmp_path / "office.sqlite")
    await store.init_db()

    # Configure agent with two models having simulated API keys:
    # 1. Primary: mock-model-primary (OpenAI-compatible)
    # 2. Fallback: mock-model-fallback (OpenAI-compatible)
    await store.create_llm_model(
        LLMModelCatalogCreate(
            model_id="mock-model-primary",
            display_name="Primary Test Model",
            provider="groq",
            base_url="https://api.mock.test/v1",
            api_key_env="MOCK_TEST_KEY",
            tier="free",
        )
    )
    await store.create_llm_model(
        LLMModelCatalogCreate(
            model_id="mock-model-fallback",
            display_name="Fallback Test Model",
            provider="mistral",
            base_url="https://api.mock.test/v1",
            api_key_env="MOCK_TEST_KEY",
            tier="free",
        )
    )

    with patch.dict("os.environ", {"MOCK_TEST_KEY": "dummy-token"}):
        await store.save_agent_llm_config(
            "agente_01_pm",
            AgentLLMConfigUpdate(
                assigned_models=[
                    AssignedModelItem(model_id="mock-model-primary", enabled=True, priority=1),
                    AssignedModelItem(model_id="mock-model-fallback", enabled=True, priority=2),
                ],
                temperature=0.2,
                max_tokens=1000,
                timeout=10,
                max_retries=1,
            ),
        )

        gateway = GeminiLLMGateway(store=store)

        # Primary returns 429, Fallback returns 200 with valid content
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.text = "Rate limit hit"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "choices": [
                {"message": {"content": "---\norigen: 'agente_01_pm'\n---\nFALLBACK_RECOVERED"}}
            ]
        }

        with patch.object(
            httpx.AsyncClient, "post", new_callable=AsyncMock, side_effect=[resp_429, resp_200]
        ):
            output = await gateway.invoke_agent(
                agent_id=AgentID.AGENTE_01_PM,
                system_prompt="system",
                user_payload="payload",
            )
            assert "FALLBACK_RECOVERED" in output
            # Verify telemetry tracking
            assert gateway.last_model_used["agente_01_pm"] == "mock-model-fallback"
            assert gateway.last_fallback_event["agente_01_pm"]["fallback_used"] is True
            assert gateway.last_fallback_event["agente_01_pm"]["attempt_index"] == 1
