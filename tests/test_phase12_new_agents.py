"""Unit tests for Phase 12: CEO, UI/UX, Marketing, and Sales/Analytics agent nodes and state."""

from pathlib import Path

import pytest

from app.graph.nodes import FactoryNodes
from app.graph.state import ProjectState, SoftwareFactoryState, create_initial_state
from app.schemas.api import ProjectDeliverablesResponse
from app.schemas.routing import AgentID, DeliverableStatus, StepExecutionRecord
from app.services.code_materializer import CodeMaterializerService
from app.services.llm_gateway import MockLLMGateway
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.output_parser import AgentOutputParser
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


def _append_history(state: SoftwareFactoryState, updates: dict[str, object]) -> None:
    """Helper to append execution records from node results into state."""
    hist = updates.get("execution_history")
    if isinstance(hist, list):
        for item in hist:
            if isinstance(item, StepExecutionRecord):
                state["execution_history"].append(item)


@pytest.fixture
def clean_test_workspace(tmp_path: Path) -> Path:
    """Fixture providing an isolated temporary workspace directory."""
    return tmp_path / "workspaces"


@pytest.fixture
def test_office_store(tmp_path: Path) -> OfficeStore:
    """Fixture providing an isolated SQLite OfficeStore."""
    db_path = tmp_path / "test_office.db"
    return OfficeStore(db_path=db_path)


def test_identities_and_state_extension() -> None:
    """Verify that the 4 new AgentIDs and DeliverableStatuses exist in state."""
    # 1. Agent IDs
    assert AgentID.AGENTE_00_CEO.value == "agente_00_ceo"
    assert AgentID.AGENTE_11_UI_UX.value == "agente_11_ui_ux"
    assert AgentID.AGENTE_12_MARKETING.value == "agente_12_marketing"
    assert AgentID.AGENTE_13_SALES_ANALYTICS.value == "agente_13_sales_analytics"

    # Legacy compatibility check
    assert AgentID.AGENTE_09_GROWTH.value == "agente_09_growth"

    # 2. Deliverable Statuses
    assert DeliverableStatus.CHARTER_NEGOCIO_LISTO.value == "CHARTER_NEGOCIO_LISTO"
    assert DeliverableStatus.SISTEMA_DISENO_UI_LISTO.value == "SISTEMA_DISENO_UI_LISTO"
    assert DeliverableStatus.ESTRATEGIA_CAPTACION_LISTA.value == "ESTRATEGIA_CAPTACION_LISTA"
    assert DeliverableStatus.EMBUDO_Y_METRICAS_LISTOS.value == "EMBUDO_Y_METRICAS_LISTOS"
    assert DeliverableStatus.LANZAMIENTO_AUTORIZADO.value == "LANZAMIENTO_AUTORIZADO"

    # 3. State initialization
    state: ProjectState = create_initial_state(
        project_id="proj_phase12_test",
        idea_inicial="Plataforma SaaS de validación y limpieza de correos 100% autoservicio.",
    )
    assert state["ceo_charter"] == ""
    assert state["ui_ux_spec"] == ""
    assert state["marketing_spec"] == ""
    assert state["sales_analytics_spec"] == ""
    assert state["ceo_signoff"] == ""
    assert state["ceo_approved"] is False


@pytest.mark.asyncio
async def test_prompt_loader_and_mock_llm_for_new_agents() -> None:
    """Test that prompts load correctly and mock LLM generates outputs with YAML headers."""
    loader = PromptLoader()
    gateway = MockLLMGateway()

    # AGENTE_00_CEO Opening
    prompt_ceo = await loader.load_prompt(AgentID.AGENTE_00_CEO)
    assert "Director Ejecutivo" in prompt_ceo or "CEO" in prompt_ceo
    mock_ceo_charter = await gateway.invoke_agent(
        agent_id=AgentID.AGENTE_00_CEO,
        system_prompt=prompt_ceo,
        user_payload="Definir Business Charter 100% Zero-Touch",
    )
    header_ceo = AgentOutputParser.parse_routing_header(AgentID.AGENTE_00_CEO, mock_ceo_charter)
    assert header_ceo.estado_entregable == DeliverableStatus.CHARTER_NEGOCIO_LISTO
    assert header_ceo.destino_siguiente == AgentID.AGENTE_01_PM.value
    assert "Zero-Touch" in mock_ceo_charter
    assert "config/business_charter.json" in mock_ceo_charter
    assert '"human_touchpoints_allowed": false' in mock_ceo_charter

    # AGENTE_00_CEO Closing (Signoff)
    mock_ceo_signoff = await gateway.invoke_agent(
        agent_id=AgentID.AGENTE_00_CEO,
        system_prompt=prompt_ceo,
        user_payload="# Resumen Ejecutivo y Auditoría de Cierre (Acta)",
    )
    header_signoff = AgentOutputParser.parse_routing_header(
        AgentID.AGENTE_00_CEO, mock_ceo_signoff
    )
    assert header_signoff.estado_entregable == DeliverableStatus.LANZAMIENTO_AUTORIZADO
    assert header_signoff.destino_siguiente == AgentID.END_PIPELINE.value
    assert "config/release_manifest.json" in mock_ceo_signoff
    assert '"zero_touch_compliance": true' in mock_ceo_signoff

    # AGENTE_11_UI_UX
    prompt_ui = await loader.load_prompt(AgentID.AGENTE_11_UI_UX)
    assert "UI/UX" in prompt_ui
    mock_ui = await gateway.invoke_agent(
        agent_id=AgentID.AGENTE_11_UI_UX,
        system_prompt=prompt_ui,
        user_payload="Crear diseño",
    )
    header_ui = AgentOutputParser.parse_routing_header(AgentID.AGENTE_11_UI_UX, mock_ui)
    assert header_ui.estado_entregable == DeliverableStatus.SISTEMA_DISENO_UI_LISTO
    assert "tailwind.config.js" in mock_ui
    assert "design_tokens.css" in mock_ui

    # AGENTE_12_MARKETING
    prompt_mkt = await loader.load_prompt(AgentID.AGENTE_12_MARKETING)
    assert "Marketing" in prompt_mkt
    mock_mkt = await gateway.invoke_agent(
        agent_id=AgentID.AGENTE_12_MARKETING,
        system_prompt=prompt_mkt,
        user_payload="Estrategia TOFU",
    )
    header_mkt = AgentOutputParser.parse_routing_header(AgentID.AGENTE_12_MARKETING, mock_mkt)
    assert header_mkt.estado_entregable == DeliverableStatus.ESTRATEGIA_CAPTACION_LISTA
    assert "robots.txt" in mock_mkt
    assert "sitemap.xml" in mock_mkt

    # AGENTE_13_SALES_ANALYTICS
    prompt_sales = await loader.load_prompt(AgentID.AGENTE_13_SALES_ANALYTICS)
    assert "Sales" in prompt_sales or "Ventas" in prompt_sales
    mock_sales = await gateway.invoke_agent(
        agent_id=AgentID.AGENTE_13_SALES_ANALYTICS,
        system_prompt=prompt_sales,
        user_payload="Monetización BOFU",
    )
    header_sales = AgentOutputParser.parse_routing_header(
        AgentID.AGENTE_13_SALES_ANALYTICS, mock_sales
    )
    assert header_sales.estado_entregable == DeliverableStatus.EMBUDO_Y_METRICAS_LISTOS
    assert "stripe_plans.json" in mock_sales
    assert "analytics_schema.sql" in mock_sales


@pytest.mark.asyncio
async def test_ceo_opening_and_signoff_nodes(
    clean_test_workspace: Path,
    test_office_store: OfficeStore,
) -> None:
    """Verify execution of ceo_charter_node and ceo_signoff_node."""
    gateway = MockLLMGateway()
    loader = PromptLoader()
    writer = WorkspaceWriter(base_dir=clean_test_workspace)
    mail_svc = MailService(store=test_office_store)
    nodes = FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=test_office_store,
        mail_service=mail_svc,
    )

    state = create_initial_state(
        project_id="proj_ceo_lifecycle",
        idea_inicial="Servicio de validación masiva de correos para SaaS B2B.",
    )

    # 1. Execute CEO Opening Node
    res_charter = await nodes.ceo_charter_node(state)
    state["ceo_charter"] = str(res_charter["ceo_charter"])
    _append_history(state, res_charter)

    assert "Business Charter" in state["ceo_charter"]
    assert "Zero-Touch" in state["ceo_charter"]
    assert "config/business_charter.json" in state["ceo_charter"]
    assert '"human_touchpoints_allowed": false' in state["ceo_charter"]
    assert len(state["execution_history"]) == 1
    assert state["execution_history"][0].agent_id == AgentID.AGENTE_00_CEO
    assert state["execution_history"][0].status == DeliverableStatus.CHARTER_NEGOCIO_LISTO

    # Verify deliverable file was written
    charter_file = clean_test_workspace / "proj_ceo_lifecycle" / "01_agente_00_ceo.md"
    assert charter_file.exists()
    charter_text = charter_file.read_text(encoding="utf-8")
    has_ceo_header = (
        'agente_emisor: "agente_00_ceo"' in charter_text
        or 'origen: "agente_00_ceo"' in charter_text
    )
    assert has_ceo_header

    # Verify email sent from ceo@agentoffice.local to agente_01_pm
    emails_pm = await test_office_store.get_emails("proj_ceo_lifecycle")
    assert len(emails_pm) >= 1
    ceo_email = emails_pm[0]
    assert ceo_email.sender == "ceo@agentoffice.local"
    assert "agente_01_pm" in ceo_email.recipient

    # 2. Simulate subsequent stages and execute CEO Signoff Node
    state["dictamen_ciso"] = "# Dictamen CISO: Blindado apto para producción"
    state["documentacion_rag"] = "# Docs & RAG listos"
    state["marketing_spec"] = "# Marketing TOFU listo"
    state["sales_analytics_spec"] = "# Ventas BOFU listas"

    res_signoff = await nodes.ceo_signoff_node(state)
    state["ceo_signoff"] = str(res_signoff["ceo_signoff"])
    state["ceo_approved"] = bool(res_signoff["ceo_approved"])
    _append_history(state, res_signoff)

    assert "Acta de Cierre Ejecutivo" in state["ceo_signoff"]
    assert state["ceo_approved"] is True
    assert "config/release_manifest.json" in state["ceo_signoff"]
    assert '"zero_touch_compliance": true' in state["ceo_signoff"]
    assert len(state["execution_history"]) == 2
    assert state["execution_history"][1].status == DeliverableStatus.LANZAMIENTO_AUTORIZADO

    # Deliverable 02
    signoff_file = clean_test_workspace / "proj_ceo_lifecycle" / "02_agente_00_ceo.md"
    assert signoff_file.exists()


@pytest.mark.asyncio
async def test_ui_ux_marketing_sales_nodes(
    clean_test_workspace: Path,
    test_office_store: OfficeStore,
) -> None:
    """Verify execution of ui_ux_node, marketing_node, and sales_analytics_node."""
    gateway = MockLLMGateway()
    loader = PromptLoader()
    writer = WorkspaceWriter(base_dir=clean_test_workspace)
    mail_svc = MailService(store=test_office_store)
    nodes = FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=test_office_store,
        mail_service=mail_svc,
    )

    state = create_initial_state(
        project_id="proj_growth_stack",
        idea_inicial="Herramienta de limpieza de emails con webhook instantáneo.",
    )
    state["pre_sdd_doc"] = "# Pre-SDD Funcional completo"
    state["sdd_arquitectura"] = "# SDD Arquitectura Técnica completa"
    state["ceo_charter"] = "# Charter CEO 100% Zero-Touch"

    # 1. UI/UX Node
    res_ui = await nodes.ui_ux_node(state)
    state["ui_ux_spec"] = str(res_ui["ui_ux_spec"])
    _append_history(state, res_ui)
    assert "tailwind.config.js" in state["ui_ux_spec"]
    assert "design_tokens.css" in state["ui_ux_spec"]
    assert "3 Clics" in state["ui_ux_spec"] or "3 clics" in state["ui_ux_spec"]

    ui_file = clean_test_workspace / "proj_growth_stack" / "01_agente_11_ui_ux.md"
    assert ui_file.exists()

    # 2. Marketing Node
    res_mkt = await nodes.marketing_node(state)
    state["marketing_spec"] = str(res_mkt["marketing_spec"])
    _append_history(state, res_mkt)
    assert "robots.txt" in state["marketing_spec"]
    assert "sitemap.xml" in state["marketing_spec"]

    mkt_file = clean_test_workspace / "proj_growth_stack" / "02_agente_12_marketing.md"
    assert mkt_file.exists()

    # 3. Sales & Analytics Node
    res_sales = await nodes.sales_analytics_node(state)
    state["sales_analytics_spec"] = str(res_sales["sales_analytics_spec"])
    _append_history(state, res_sales)
    assert "stripe_plans.json" in state["sales_analytics_spec"]
    assert "analytics_schema.sql" in state["sales_analytics_spec"]

    sales_file = clean_test_workspace / "proj_growth_stack" / "03_agente_13_sales_analytics.md"
    assert sales_file.exists()

    # Verify mail sequence: UI/UX -> Laravel (1), Mkt -> Sales (1), Sales -> CEO (1)
    all_emails = await test_office_store.get_emails("proj_growth_stack")
    assert len(all_emails) in (3, 4)
    senders = [em.sender for em in all_emails]
    assert "agente_11_ui_ux@agentoffice.local" in senders
    assert "agente_12_marketing@agentoffice.local" in senders
    assert "agente_13_sales_analytics@agentoffice.local" in senders


def test_project_deliverables_response_phase12() -> None:
    """Verify ProjectDeliverablesResponse schema with all new Phase 12 fields."""
    response = ProjectDeliverablesResponse(
        project_id="proj_deliv_test",
        pre_sdd_doc="# Pre-SDD",
        sdd_arquitectura="# SDD",
        codigo_php="<?php echo 1;",
        codigo_python="print(1)",
        reporte_qa_php="# QA PHP OK",
        reporte_qa_python="# QA Python OK",
        infraestructura_docker="# Docker Compose",
        dictamen_ciso="# CISO OK",
        documentacion_rag="# RAG Docs",
        estrategia_growth="# Growth",
        ceo_charter="# CEO Charter",
        ui_ux_spec="# UI UX Spec",
        marketing_spec="# Marketing Spec",
        sales_analytics_spec="# Sales Spec",
        ceo_signoff="# CEO Signoff",
    )

    data = response.model_dump()
    assert data["ceo_charter"] == "# CEO Charter"
    assert data["ui_ux_spec"] == "# UI UX Spec"
    assert data["marketing_spec"] == "# Marketing Spec"
    assert data["sales_analytics_spec"] == "# Sales Spec"
    assert data["ceo_signoff"] == "# CEO Signoff"


@pytest.mark.asyncio
async def test_ui_ux_emits_artifacts_and_materializer(
    clean_test_workspace: Path,
    test_office_store: OfficeStore,
) -> None:
    """Verify that node_11_ui_ux outputs tailwind.config.js & design_tokens.css for materializer."""
    gateway = MockLLMGateway()
    loader = PromptLoader()
    writer = WorkspaceWriter(base_dir=clean_test_workspace)
    mail_svc = MailService(store=test_office_store)
    nodes = FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=test_office_store,
        mail_service=mail_svc,
    )

    state = create_initial_state(
        project_id="proj_ui_materializer",
        idea_inicial="App de validación masiva con diseño TailwindCSS.",
    )
    state["pre_sdd_doc"] = "# Pre-SDD"
    state["sdd_arquitectura"] = "# SDD"

    res_ui = await nodes.ui_ux_node(state)
    ui_spec = str(res_ui["ui_ux_spec"])
    assert "tailwind.config.js" in ui_spec
    assert "design_tokens.css" in ui_spec

    materializer = CodeMaterializerService(workspaces_dir=clean_test_workspace)
    build_dir, manifest = materializer.materialize_project("proj_ui_materializer")

    tailwind_file = build_dir / "tailwind.config.js"
    assert tailwind_file.exists()
    assert "module.exports" in tailwind_file.read_text(encoding="utf-8")

    tokens_file = build_dir / "resources" / "css" / "design_tokens.css"
    assert tokens_file.exists()
    assert "--color-primary" in tokens_file.read_text(encoding="utf-8")
