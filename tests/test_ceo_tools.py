"""Tests for Agent 00 (CEO) deterministic tools and free connectors."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from app.tools.ceo_tools import (
    auto_fix_tier_margins,
    extract_ceo_artifacts,
    scan_zero_touch_compliance,
    sync_ceo_executive_comms,
    verify_unit_economics_math,
)


def test_verify_unit_economics_math_valid() -> None:
    """Test verify_unit_economics_math with a fully compliant charter."""
    charter: dict[str, Any] = {
        "business_model": "100% Zero-Touch Micro-SaaS",
        "human_touchpoints_allowed": False,
        "max_ttfv_seconds": 45,
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
                "max_cogs_usd": 5.00,
            },
        ],
    }

    result = verify_unit_economics_math(charter)
    assert result["valid"] is True
    assert len(result["violations"]) == 0
    assert len(result["tiers_audit"]) == 2

    # Tier 1 audit: 19 - (19*0.029 + 0.30) - 1.50 = 19 - 0.851 - 1.50 = 16.649 -> 87.63%
    assert result["tiers_audit"][0]["net_margin_pct"] >= 80.0
    assert result["tiers_audit"][0]["compliant"] is True


def test_verify_unit_economics_math_violations_and_autofix() -> None:
    """Test violation detection and automatic COGS adjustment to 85% margin."""
    deficient_charter: dict[str, Any] = {
        "business_model": "Micro-SaaS",
        "human_touchpoints_allowed": True,  # Violation!
        "max_ttfv_seconds": 120,  # Violation!
        "tiers": [
            {
                "id": "tier_cheap",
                "name": "Cheap",
                "price_usd": 10.0,
                "max_cogs_usd": 4.00,  # High COGS -> Net margin < 80%
            }
        ],
    }

    audit = verify_unit_economics_math(deficient_charter)
    assert audit["valid"] is False
    assert len(audit["violations"]) >= 3  # human_touch, ttfv, margin

    # Apply auto_fix
    fixed = auto_fix_tier_margins(deficient_charter)
    assert fixed["human_touchpoints_allowed"] is False
    assert fixed["max_ttfv_seconds"] <= 60

    # For $10: stripe_fee = 10 * 0.029 + 0.30 = 0.59.
    # target_cogs = 10 * 0.15 - 0.59 = 1.50 - 0.59 = 0.91.
    assert fixed["tiers"][0]["max_cogs_usd"] == 0.91

    # Verify fixed charter now passes
    fixed_audit = verify_unit_economics_math(fixed)
    assert fixed_audit["valid"] is True
    assert len(fixed_audit["violations"]) == 0
    assert fixed_audit["tiers_audit"][0]["net_margin_pct"] >= 84.9


def test_scan_zero_touch_compliance() -> None:
    """Test scanner detects forbidden human sales and high-touch terms."""
    clean_text = "Nuestro flujo de onboarding es 100% self-service con checkout automático."
    clean_result = scan_zero_touch_compliance(clean_text)
    assert clean_result["compliant"] is True
    assert clean_result["detected_forbidden_terms"] == []

    dirty_text = (
        "Para planes Enterprise, puedes contactar con ventas o agendar demo con nuestro equipo."
    )
    dirty_result = scan_zero_touch_compliance(dirty_text)
    assert dirty_result["compliant"] is False
    assert "contactar con ventas" in dirty_result["detected_forbidden_terms"]
    assert "agendar demo" in dirty_result["detected_forbidden_terms"]


def test_extract_ceo_artifacts() -> None:
    """Test extracting business_charter, release_manifest, and executive_comms."""
    sample_markdown = """---
id_proyecto: "proj_unit_test"
---

# Dictamen Ejecutivo

```json
// filepath: config/business_charter.json
{
  "business_model": "100% Zero-Touch Micro-SaaS",
  "human_touchpoints_allowed": false,
  "max_ttfv_seconds": 60,
  "tiers": []
}
```

Información intermedia...

```json
// filepath: config/release_manifest.json
{
  "release_status": "AUTHORIZED_FOR_PRODUCTION",
  "circuit_breaker_triggered": false
}
```

```json
// filepath: config/executive_comms.json
{
  "notion_page": {
    "title": "Acta de Lanzamiento",
    "summary_callout": "Todo listo",
    "markdown_body": "# Body"
  },
  "email_notification": {
    "send": true,
    "subject": "Lanzamiento",
    "body_text": "Texto"
  }
}
```
"""
    artifacts = extract_ceo_artifacts(sample_markdown)

    # 1. Canonical keys
    assert artifacts["business_charter"] is not None
    assert artifacts["business_charter"]["business_model"] == "100% Zero-Touch Micro-SaaS"
    assert artifacts["release_manifest"]["release_status"] == "AUTHORIZED_FOR_PRODUCTION"
    assert artifacts["executive_comms"]["notion_page"]["title"] == "Acta de Lanzamiento"

    # 2. Filepath alias keys
    assert artifacts["config/business_charter.json"] is not None
    assert "config/release_manifest.json" in artifacts
    assert artifacts.get("config/executive_comms.json") is not None


def test_sync_ceo_executive_comms_fallback() -> None:
    """Test fallback when environment variables are missing."""
    comms: dict[str, Any] = {
        "notion_page": {
            "title": "Documento Test",
            "summary_callout": "Resumen",
            "markdown_body": "Contenido",
        },
        "email_notification": {
            "send": True,
            "subject": "Test",
            "body_text": "Texto",
        },
    }

    # Ensure no credentials in env
    with patch.dict("os.environ", {}, clear=True):
        res = sync_ceo_executive_comms(comms)
        assert res["notion_synced"] is False
        assert res["email_sent"] is False
        assert res["status"] == "skipped_or_fallback"


def test_sync_ceo_executive_comms_success() -> None:
    """Test successful synchronization with mocked Notion and Resend responses."""
    comms: dict[str, Any] = {
        "notion_page": {
            "title": "Documento Test",
            "summary_callout": "Resumen",
            "markdown_body": "Contenido",
        },
        "email_notification": {
            "send": True,
            "subject": "Test",
            "body_text": "Texto",
        },
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch.dict(
        "os.environ",
        {
            "NOTION_API_KEY": "secret_notion_key",
            "NOTION_CEO_DATABASE_ID": "database_123",
            "RESEND_API_KEY": "re_123456",
            "FOUNDER_ALERT_EMAIL": "founder@example.com",
        },
    ):
        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = sync_ceo_executive_comms(comms)
            assert res["notion_synced"] is True
            assert res["email_sent"] is True
            assert res["status"] == "synced"


def test_sync_ceo_executive_comms_network_exception_resilience() -> None:
    """Test network exceptions are gracefully caught without crashing the graph."""
    comms: dict[str, Any] = {
        "notion_page": {"title": "Doc"},
        "email_notification": {"send": True},
    }

    with patch.dict(
        "os.environ",
        {
            "NOTION_API_KEY": "secret",
            "NOTION_CEO_DATABASE_ID": "db",
            "RESEND_API_KEY": "re_key",
            "FOUNDER_ALERT_EMAIL": "test@test.com",
        },
    ):
        with patch("urllib.request.urlopen", side_effect=OSError("Network unreachable")):
            res = sync_ceo_executive_comms(comms)
            assert res["notion_synced"] is False
            assert res["email_sent"] is False
            assert res["status"] == "skipped_or_fallback"
