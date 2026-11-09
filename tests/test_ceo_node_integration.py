"""Integration tests for Agent 00 (CEO) node validations, hooks, and routing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langgraph.graph import END

from app.graph.nodes import FactoryNodes
from app.graph.router import route_after_ceo_signoff
from app.graph.state import create_initial_state
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.llm_gateway import MockLLMGateway
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


@pytest.fixture
async def factory_nodes(tmp_path: Path) -> FactoryNodes:
    """Fixture providing initialized FactoryNodes with mock dependencies."""
    gateway = MockLLMGateway()
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    store = OfficeStore(db_path=tmp_path / "test.db")
    mail = MailService(store=store)

    return FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=store,
        mail_service=mail,
    )


@pytest.mark.asyncio
async def test_ceo_charter_node_auto_fixes_deficient_margins(
    factory_nodes: FactoryNodes,
) -> None:
    """Verify that ceo_charter_node automatically fixes deficient tier margins (<80%)."""
    state = create_initial_state("proj_charter_test", "Plataforma SaaS")

    # Mock gateway to return a charter with an invalid/deficient tier (COGS too high)
    bad_charter_markdown = """---
id_proyecto: "proj_charter_test"
version_iteracion: 1
agente_emisor: "agente_00_ceo"
agente_receptor: "agente_01_pm"
estado: "CHARTER_NEGOCIO_LISTO"
prioridad: "HIGH"
timestamp: "2026-11-04T00:00:00Z"
---

# Business Charter con Margen Deficiente
```json
// filepath: config/business_charter.json
{
  "business_model": "100% Zero-Touch Micro-SaaS",
  "human_touchpoints_allowed": false,
  "max_ttfv_seconds": 60,
  "target_gross_margin_pct": 85.0,
  "tiers": [
    {
      "id": "tier_entry",
      "name": "Starter",
      "price_usd": 10.0,
      "max_cogs_usd": 5.0
    }
  ]
}
```

```json
// filepath: config/executive_comms.json
{
  "notion_page": {
    "template": "STRATEGIC_CHARTER_PAGE",
    "title": "Business Charter",
    "status": "EN_EJECUCION",
    "summary_callout": "Charter listo",
    "markdown_body": "# Body"
  },
  "email_notification": {
    "send": false,
    "type": "FOUNDER_DIGEST",
    "subject": "Charter",
    "body_text": "Texto"
  }
}
```
"""
    with patch.object(
        factory_nodes.llm_gateway,
        "invoke_agent",
        return_value=bad_charter_markdown,
    ):
        result = await factory_nodes.ceo_charter_node(state)

    charter_output = str(result["ceo_charter"])
    # COGS should have been adjusted down to 0.91 to guarantee exactly 85% net margin
    assert '"max_cogs_usd": 0.91' in charter_output
    assert result["version_iteracion"] == 1


@pytest.mark.asyncio
async def test_ceo_signoff_node_detects_zero_touch_violations(
    factory_nodes: FactoryNodes,
) -> None:
    """Verify ceo_signoff_node detects prohibited terms in Marketing and triggers rework."""
    state = create_initial_state("proj_signoff_veto", "Micro-SaaS")
    state["marketing_spec"] = (
        "Para usuarios Enterprise, se recomienda contactar con ventas o agendar demo."
    )
    state["version_iteracion"] = 1

    result = await factory_nodes.ceo_signoff_node(state)

    assert result["ceo_approved"] is False
    assert result["ceo_blocked"] is True
    assert result["status_ceo"] == DeliverableStatus.LANZAMIENTO_BLOQUEADO_REWORK
    assert result["version_iteracion"] == 2
    assert "contactar con ventas (en marketing_spec)" in result["zero_touch_violations"]

    # Verify router loops back to Marketing
    state_after = {**state, **result}
    next_node = route_after_ceo_signoff(state_after)  # type: ignore[arg-type]
    assert next_node == AgentID.AGENTE_12_MARKETING.value


@pytest.mark.asyncio
async def test_ceo_signoff_node_escapes_loop_at_iteration_3(
    factory_nodes: FactoryNodes,
) -> None:
    """Verify that when iteration reaches >= 3, infinite loop is broken and escalates to END."""
    state = create_initial_state("proj_signoff_escalation", "Micro-SaaS")
    state["marketing_spec"] = "Por favor contactar con ventas para activar cuenta."
    state["version_iteracion"] = 3  # Already at limit

    mock_sync_comms = MagicMock()
    with patch("app.graph.nodes.sync_ceo_executive_comms", mock_sync_comms):
        result = await factory_nodes.ceo_signoff_node(state)

    assert result["ceo_approved"] is False
    assert result["version_iteracion"] == 3
    # Check that CRITICAL_ESCALATION was passed to sync_ceo_executive_comms
    assert mock_sync_comms.called
    called_args = mock_sync_comms.call_args[0][0]
    assert called_args["email_notification"]["type"] == "CRITICAL_ESCALATION"

    # Verify router terminates at END
    state_after = {**state, **result}
    next_node = route_after_ceo_signoff(state_after)  # type: ignore[arg-type]
    assert next_node == END
