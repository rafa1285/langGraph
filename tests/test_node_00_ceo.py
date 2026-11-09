"""Automated test suite for Agent 00 (CEO) capabilities and LangGraph lifecycle.

Tests deterministic unit economics math, zero-touch compliance scanner,
safe CEO artifact extraction, graceful Notion/Resend comms sync, and circuit
breaker max-iterations anti-loop guard.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langgraph.graph import END

from app.graph.nodes import FactoryNodes
from app.graph.router import route_after_ceo_signoff
from app.graph.state import SoftwareFactoryState, create_initial_state
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.llm_gateway import MockLLMGateway
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter
from app.tools.ceo_tools import (
    auto_fix_tier_margins,
    extract_ceo_artifacts,
    scan_zero_touch_compliance,
    sync_ceo_executive_comms,
    verify_unit_economics_math,
)


@pytest.fixture
async def factory_nodes(tmp_path: Path) -> FactoryNodes:
    """Provide initialized FactoryNodes with isolated mock dependencies."""
    gateway = MockLLMGateway()
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    store = OfficeStore(db_path=tmp_path / "test_ceo.db")
    mail = MailService(store=store)

    return FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=store,
        mail_service=mail,
    )


def test_unit_economics_math_validation_and_autofix() -> None:
    """Test official tier pricing validation (>=80% net margin) and automatic correction."""
    # 1. Test official 3 tiers: Starter ($19), Growth ($69), Scale ($199)
    official_charter: dict[str, Any] = {
        "business_model": "100% Zero-Touch Micro-SaaS",
        "human_touchpoints_allowed": False,
        "max_ttfv_seconds": 60,
        "target_gross_margin_pct": 85.0,
        "tiers": [
            {
                "id": "tier_entry",
                "name": "Starter",
                "price_usd": 19.0,
                "billing": "monthly",
                "hard_quota": 2500,
                "max_cogs_usd": 1.50,
            },
            {
                "id": "tier_pro",
                "name": "Growth",
                "price_usd": 69.0,
                "billing": "monthly",
                "hard_quota": 25000,
                "max_cogs_usd": 6.00,
            },
            {
                "id": "tier_scale",
                "name": "Scale",
                "price_usd": 199.0,
                "billing": "monthly",
                "hard_quota": 150000,
                "max_cogs_usd": 22.00,
            },
        ],
    }

    audit = verify_unit_economics_math(official_charter)
    assert audit["valid"] is True
    assert len(audit["violations"]) == 0
    assert len(audit["tiers_audit"]) == 3

    # Verify each tier meets >= 80% net margin after Stripe fee (2.9% + $0.30) and COGS
    for tier_audit in audit["tiers_audit"]:
        assert tier_audit["compliant"] is True
        assert tier_audit["net_margin_pct"] >= 80.0

    # Specific margin audits:
    # Starter ($19): Stripe = 0.851, COGS = 1.50 -> net = 16.649 -> 87.63%
    assert audit["tiers_audit"][0]["net_margin_pct"] == pytest.approx(87.63, abs=0.1)
    # Growth ($69): Stripe = 2.301, COGS = 6.00 -> net = 60.699 -> 87.97%
    assert audit["tiers_audit"][1]["net_margin_pct"] == pytest.approx(87.97, abs=0.1)
    # Scale ($199): Stripe = 6.071, COGS = 22.00 -> net = 170.929 -> 85.89%
    assert audit["tiers_audit"][2]["net_margin_pct"] == pytest.approx(85.89, abs=0.1)

    # 2. Test defective tier ($19 with COGS $10.00 -> margin = 42.89% < 80%)
    defective_charter: dict[str, Any] = {
        "business_model": "Micro-SaaS Defective",
        "human_touchpoints_allowed": False,
        "max_ttfv_seconds": 60,
        "tiers": [
            {
                "id": "tier_bad",
                "name": "Bad Starter",
                "price_usd": 19.0,
                "max_cogs_usd": 10.00,
            }
        ],
    }

    bad_audit = verify_unit_economics_math(defective_charter)
    assert bad_audit["valid"] is False
    assert len(bad_audit["violations"]) >= 1
    assert "below" in bad_audit["violations"][0].lower()

    # Apply auto_fix_tier_margins
    fixed_charter = auto_fix_tier_margins(defective_charter)
    # For $19: max_cogs = 19 * 0.15 - (19*0.029 + 0.30) = 2.85 - 0.851 = 1.999 -> 2.00
    fixed_cogs = float(fixed_charter["tiers"][0]["max_cogs_usd"])
    assert fixed_cogs == pytest.approx(2.00, abs=0.02)

    # Re-verify fixed charter passes with >= 80% (approx 85% target)
    recheck = verify_unit_economics_math(fixed_charter)
    assert recheck["valid"] is True
    assert recheck["tiers_audit"][0]["net_margin_pct"] >= 80.0
    assert recheck["tiers_audit"][0]["compliant"] is True


def test_zero_touch_compliance_scanner() -> None:
    """Test scanner identifies prohibited sales/human terms and accepts pure self-serve text."""
    # 1. Forbidden high-touch terms
    bad_texts = [
        "Para contratar el plan anual, agendar demo con un comercial del equipo.",
        "Interested in Enterprise? Contact sales directly for custom pricing.",
        "Solicita un presupuesto a medida con onboarding manual guiado por soporte humano.",
    ]
    for text in bad_texts:
        res = scan_zero_touch_compliance(text)
        assert res["compliant"] is False
        assert len(res["detected_forbidden_terms"]) > 0

    # Test exact terms identified
    res_demo = scan_zero_touch_compliance("Agendar demo con un comercial")
    assert res_demo["compliant"] is False
    assert "agendar demo" in res_demo["detected_forbidden_terms"]

    res_sales = scan_zero_touch_compliance("Please contact sales for quotes")
    assert res_sales["compliant"] is False
    assert "contact sales" in res_sales["detected_forbidden_terms"]

    # 2. Compliant pure self-service text
    clean_text = "Alta instantánea autoservicio con Stripe y simulador en Hero sin registro previo."
    clean_res = scan_zero_touch_compliance(clean_text)
    assert clean_res["compliant"] is True
    assert clean_res["detected_forbidden_terms"] == []


def test_extract_ceo_artifacts_all_modes() -> None:
    """Verify clean extraction of business_charter, release_manifest, and executive_comms."""
    # 1. Modo 1: Apertura (Charter + Executive Comms)
    mode1_md = """---
id_proyecto: "proj_m1"
agente_emisor: "agente_00_ceo"
agente_receptor: "agente_01_pm"
estado: "CHARTER_NEGOCIO_LISTO"
---

# Business Charter
```json
// filepath: config/business_charter.json
{
  "business_model": "100% Zero-Touch Micro-SaaS",
  "human_touchpoints_allowed": false,
  "max_ttfv_seconds": 60,
  "tiers": [{"id": "t1", "price_usd": 19}]
}
```

```json
// filepath: config/executive_comms.json
{
  "notion_page": {
    "template": "STRATEGIC_CHARTER_PAGE",
    "title": "Business Charter — Proj M1",
    "status": "EN_EJECUCION"
  },
  "email_notification": {
    "send": true,
    "type": "FOUNDER_DIGEST",
    "subject": "[Charter] Proj M1"
  }
}
```
"""
    art1 = extract_ceo_artifacts(mode1_md)
    assert art1["business_charter"] is not None
    assert art1["business_charter"]["business_model"] == "100% Zero-Touch Micro-SaaS"
    assert art1["executive_comms"] is not None
    assert art1["executive_comms"]["notion_page"]["template"] == "STRATEGIC_CHARTER_PAGE"
    assert art1["release_manifest"] is None

    # Test filepath alias access
    assert art1["config/business_charter.json"] == art1["business_charter"]
    assert art1.get("config/executive_comms.json") == art1["executive_comms"]

    # 2. Modo 2: Lanzamiento Autorizado (Release Manifest + Executive Comms)
    mode2_md = """---
id_proyecto: "proj_m2"
estado: "LANZAMIENTO_AUTORIZADO"
---

# Acta de Cierre
```json
// filepath: config/release_manifest.json
{
  "release_status": "AUTHORIZED_FOR_PRODUCTION",
  "zero_touch_compliance": true,
  "circuit_breaker_triggered": false
}
```

```json
// filepath: config/executive_comms.json
{
  "notion_page": {
    "template": "RELEASE_AUDIT_ADR",
    "title": "Acta de Lanzamiento Proj M2",
    "status": "COMPLETADO_PRODUCCION"
  },
  "email_notification": {
    "send": true,
    "type": "FOUNDER_DIGEST",
    "subject": "[RELEASE] Proj M2 Autorizado"
  }
}
```
"""
    art2 = extract_ceo_artifacts(mode2_md)
    assert art2["release_manifest"] is not None
    assert art2["release_manifest"]["release_status"] == "AUTHORIZED_FOR_PRODUCTION"
    assert art2["executive_comms"]["notion_page"]["template"] == "RELEASE_AUDIT_ADR"
    assert art2["business_charter"] is None

    # 3. Modo 3: Veto y Devolución (Release Manifest BLOCKED + Executive Comms CIRCUIT_BREAKER)
    mode3_md = """---
id_proyecto: "proj_m3"
estado: "LANZAMIENTO_BLOQUEADO_REWORK"
estado_global: "CIRCUIT_BREAKER_ACTIVO"
---

# Veto Ejecutivo
```json
// filepath: config/release_manifest.json
{
  "release_status": "BLOCKED_REQUIRES_REWORK",
  "circuit_breaker_triggered": true,
  "culprit_agent": "agente_12_marketing"
}
```

```json
// filepath: config/executive_comms.json
{
  "notion_page": {
    "template": "CIRCUIT_BREAKER_ALERT",
    "title": "ALERTA: Lanzamiento Bloqueado",
    "status": "BLOQUEADO_REWORK"
  },
  "email_notification": {
    "send": true,
    "type": "CRITICAL_ESCALATION",
    "subject": "[CRITICAL] Veto en Proj M3"
  }
}
```
"""
    art3 = extract_ceo_artifacts(mode3_md)
    assert art3["release_manifest"] is not None
    assert art3["release_manifest"]["release_status"] == "BLOCKED_REQUIRES_REWORK"
    assert art3["release_manifest"]["circuit_breaker_triggered"] is True
    assert art3["executive_comms"]["notion_page"]["template"] == "CIRCUIT_BREAKER_ALERT"


def test_sync_ceo_executive_comms_graceful_fallback_and_mock() -> None:
    """Test Notion and Resend connectors: graceful fallback and mocked HTTP POSTs."""
    sample_comms: dict[str, Any] = {
        "notion_page": {
            "template": "STRATEGIC_CHARTER_PAGE",
            "title": "Strategic Charter - Test Corp",
            "summary_callout": "Plan zero-touch listo.",
            "markdown_body": "# Introduccion\nDocumento estratégico ejecutivo.",
        },
        "email_notification": {
            "send": True,
            "type": "FOUNDER_DIGEST",
            "subject": "[Charter] Test Corp Iniciado",
            "body_text": "Todo configurado de forma autónoma.",
        },
    }

    # 1. Graceful fallback when environment variables are missing
    with patch.dict("os.environ", {}, clear=True):
        res_fallback = sync_ceo_executive_comms(sample_comms)
        assert res_fallback["notion_synced"] is False
        assert res_fallback["email_sent"] is False
        assert res_fallback["status"] == "skipped_or_fallback"

    # 2. Mocked HTTP POSTs when environment variables are set
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__.return_value = mock_response

    captured_requests: list[urllib.request.Request] = []

    def mock_urlopen(req: urllib.request.Request, timeout: int = 10) -> MagicMock:
        captured_requests.append(req)
        return mock_response

    with patch.dict(
        "os.environ",
        {
            "NOTION_API_KEY": "ntn_test_api_key_12345",
            "NOTION_CEO_DATABASE_ID": "database_abc_987",
            "RESEND_API_KEY": "re_test_key_67890",
            "FOUNDER_ALERT_EMAIL": "founder@testcorp.com",
        },
    ):
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            res_sync = sync_ceo_executive_comms(sample_comms)
            assert res_sync["notion_synced"] is True
            assert res_sync["email_sent"] is True
            assert res_sync["status"] == "synced"

    # Verify captured requests
    assert len(captured_requests) == 2

    # Verify Notion POST request
    notion_req = next(r for r in captured_requests if "api.notion.com" in r.full_url)
    assert notion_req.get_method() == "POST"
    assert notion_req.headers["Authorization"] == "Bearer ntn_test_api_key_12345"
    assert notion_req.headers["Notion-version"] == "2022-06-28"
    assert notion_req.data is not None
    notion_body = json.loads(notion_req.data.decode("utf-8"))
    assert notion_body["parent"]["database_id"] == "database_abc_987"
    assert notion_body["properties"]["title"]["title"][0]["text"]["content"] == (
        "Strategic Charter - Test Corp"
    )
    assert len(notion_body["children"]) >= 2
    assert notion_body["children"][0]["type"] == "callout"

    # Verify Resend POST request
    resend_req = next(r for r in captured_requests if "api.resend.com" in r.full_url)
    assert resend_req.get_method() == "POST"
    assert resend_req.headers["Authorization"] == "Bearer re_test_key_67890"
    assert resend_req.data is not None
    resend_body = json.loads(resend_req.data.decode("utf-8"))
    assert resend_body["from"] == "AgentOffice CEO <onboarding@resend.dev>"
    assert resend_body["to"] == ["founder@testcorp.com"]
    assert resend_body["subject"] == "[Charter] Test Corp Iniciado"


@pytest.mark.asyncio
async def test_ceo_circuit_breaker_max_iterations_guard(
    factory_nodes: FactoryNodes,
) -> None:
    """Verify that iteration control halts infinite rework loops when version_iteracion >= 3."""
    state = create_initial_state("proj_cb_guard", "Plataforma SaaS con error")
    # Simulate Marketing output violating zero-touch doctrine
    state["marketing_spec"] = "Contactar con ventas para activar el plan enterprise."

    # Iteration 1: Triggers rework and increments version to 2
    state["version_iteracion"] = 1
    res_iter1 = await factory_nodes.ceo_signoff_node(state)
    assert res_iter1["ceo_blocked"] is True
    assert res_iter1["ceo_approved"] is False
    assert res_iter1["version_iteracion"] == 2
    assert res_iter1["status_ceo"] == DeliverableStatus.LANZAMIENTO_BLOQUEADO_REWORK

    state_iter2: SoftwareFactoryState = {**state, **res_iter1}  # type: ignore[assignment]
    next_node_iter1 = route_after_ceo_signoff(state_iter2)
    assert next_node_iter1 == AgentID.AGENTE_12_MARKETING.value

    # Iteration 2: Second veto increments version to 3
    state_iter2["version_iteracion"] = 2
    res_iter2 = await factory_nodes.ceo_signoff_node(state_iter2)
    assert res_iter2["ceo_blocked"] is True
    assert res_iter2["version_iteracion"] == 3

    state_iter3: SoftwareFactoryState = {**state, **res_iter2}  # type: ignore[assignment]
    next_node_iter2 = route_after_ceo_signoff(state_iter3)
    # version_iteracion is now 3, so route_after_ceo_signoff halts and forces END
    assert next_node_iter2 == END

    # Iteration 3: Reaches max guard limit (version >= 3)
    # Node forces contingency halt, does not loop, and sends CRITICAL_ESCALATION
    state_iter3["version_iteracion"] = 3
    mock_sync_comms = MagicMock()
    with patch("app.graph.nodes.sync_ceo_executive_comms", mock_sync_comms):
        res_iter3 = await factory_nodes.ceo_signoff_node(state_iter3)

    assert res_iter3["ceo_blocked"] is False  # Circuit breaker trips, stopping further reworks
    assert res_iter3["ceo_approved"] is False
    assert res_iter3["version_iteracion"] == 3
    assert "escalado crítico" in str(res_iter3["halt_reason"]).lower()

    # Verify CRITICAL_ESCALATION was sent in comms
    assert mock_sync_comms.called
    comms_payload = mock_sync_comms.call_args[0][0]
    assert comms_payload["email_notification"]["type"] == "CRITICAL_ESCALATION"

    # Router must terminate at END
    state_final: SoftwareFactoryState = {**state, **res_iter3}  # type: ignore[assignment]
    assert route_after_ceo_signoff(state_final) == END
