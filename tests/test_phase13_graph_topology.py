"""Unit and integration tests for Phase 13: 13-agent graph topology, UI/UX design integration,

and CEO governance with Circuit Breaker escalation.
"""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from app.graph.nodes import FactoryNodes, _build_user_payload
from app.graph.state import create_initial_state
from app.graph.workflow import NODE_CEO_CHARTER, NODE_CEO_SIGNOFF, compile_factory_graph
from app.schemas.routing import AgentID
from app.services.llm_gateway import MockLLMGateway
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


@pytest.mark.asyncio
async def test_workflow_full_13_agents_happy_path(tmp_path: Path) -> None:
    """Verify complete end-to-end execution of the 13-agent software factory topology."""
    gateway = MockLLMGateway()
    prompts_dir = tmp_path / "prompts"
    loader = PromptLoader(prompts_dir=prompts_dir)
    loader.ensure_prompt_files_exist()

    workspaces_dir = tmp_path / "workspaces"
    writer = WorkspaceWriter(base_dir=workspaces_dir)
    db_file = tmp_path / "office_test.db"
    store = OfficeStore(db_path=db_file)
    mail_svc = MailService(store=store)

    nodes = FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=store,
        mail_service=mail_svc,
    )

    checkpointer = MemorySaver()
    graph = compile_factory_graph(nodes, checkpointer=checkpointer, full_13_agents=True)

    project_id = "test_phase13_full_saas"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="Plataforma SaaS de validación y enriquecimiento de leads 100% Zero-Touch.",
    )

    config: RunnableConfig = {"configurable": {"thread_id": "thread-phase13-happy"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    # 1. Verify sequence of executed agents in history
    history = final_state["execution_history"]
    executed_ids = [rec.agent_id for rec in history]

    # Must start with CEO and end with CEO
    assert executed_ids[0] == AgentID.AGENTE_00_CEO
    assert executed_ids[-1] == AgentID.AGENTE_00_CEO

    # Expected agents in execution sequence
    assert AgentID.AGENTE_01_PM in executed_ids
    assert AgentID.AGENTE_02_ARCHITECT in executed_ids
    assert AgentID.AGENTE_11_UI_UX in executed_ids
    assert AgentID.AGENTE_03_LARAVEL in executed_ids
    assert AgentID.AGENTE_04_FASTAPI in executed_ids
    assert AgentID.AGENTE_05_QA_PHP in executed_ids
    assert AgentID.AGENTE_06_QA_PYTHON in executed_ids
    assert AgentID.QA_SYNC_BARRIER in executed_ids
    assert AgentID.AGENTE_07_DEVOPS in executed_ids
    assert AgentID.AGENTE_10_CISO in executed_ids
    assert AgentID.AGENTE_08_DOCS in executed_ids
    assert AgentID.AGENTE_12_MARKETING in executed_ids
    assert AgentID.AGENTE_13_SALES_ANALYTICS in executed_ids

    # 2. Verify all deliverables were populated in state
    assert final_state["ceo_charter"] != ""
    assert "Business Charter" in final_state["ceo_charter"]
    assert "Zero-Touch" in final_state["ceo_charter"]

    assert final_state["pre_sdd_doc"] != ""
    assert final_state["sdd_arquitectura"] != ""

    assert final_state["ui_ux_spec"] != ""
    assert "tailwind.config.js" in final_state["ui_ux_spec"]

    assert final_state["codigo_php"] != ""
    assert final_state["codigo_python"] != ""
    assert final_state["infraestructura_docker"] != ""
    assert final_state["dictamen_ciso"] != ""
    assert final_state["documentacion_rag"] != ""

    assert final_state["marketing_spec"] != ""
    assert "robots.txt" in final_state["marketing_spec"]
    assert "sitemap.xml" in final_state["marketing_spec"]

    assert final_state["sales_analytics_spec"] != ""
    assert "stripe_plans.json" in final_state["sales_analytics_spec"]
    assert "analytics_schema.sql" in final_state["sales_analytics_spec"]

    assert final_state["ceo_signoff"] != ""
    assert "Acta de Cierre Ejecutivo" in final_state["ceo_signoff"]
    assert final_state["ceo_approved"] is True

    # 3. Verify deliverables exist in workspace and deliverables/ subdirectory
    project_ws = workspaces_dir / project_id
    assert project_ws.exists()

    deliv_dir = project_ws / "deliverables"
    assert deliv_dir.exists()

    md_files = list(project_ws.glob("*.md"))
    deliv_files = list(deliv_dir.glob("*.md"))

    # Both main folder and deliverables subfolder must have the exact same deliverables
    assert len(md_files) == len(deliv_files)
    assert len(md_files) >= 13


@pytest.mark.asyncio
async def test_ui_ux_context_injection_in_laravel_and_qa_php() -> None:
    """Verify that ui_ux_spec is injected into Laravel dev and QA PHP contexts."""
    state = create_initial_state(
        project_id="test_ui_ux_inject",
        idea_inicial="CRM inmobiliario con TailwindCSS.",
    )
    state["sdd_arquitectura"] = "# SDD: Arquitectura Modular Hexagonal."
    state["ui_ux_spec"] = "# UI/UX: Design Tokens con Primary #4f46e5 y Flow en 3 Clics."
    state["codigo_php"] = "<?php namespace App\\Http\\Controllers; class LeadController {}"

    # 1. Check Laravel payload incorporates ui_ux_spec
    payload_laravel = _build_user_payload(AgentID.AGENTE_03_LARAVEL, state)
    assert "Especificación Sistema de Diseño UI/UX y Vistas Frontend" in payload_laravel
    assert "Flow en 3 Clics" in payload_laravel

    # 2. Check QA PHP payload incorporates ui_ux_spec for visual fidelity audit
    payload_qa_php = _build_user_payload(AgentID.AGENTE_05_QA_PHP, state)
    assert "Auditoría de Fidelidad Visual" in payload_qa_php
    assert "Primary #4f46e5" in payload_qa_php


@pytest.mark.asyncio
async def test_circuit_breaker_escalation_to_ceo_on_qa_php(tmp_path: Path) -> None:
    """Verify that when QA PHP exceeds retries, graph halts and CRITICAL escalates to CEO."""
    gateway = MockLLMGateway(always_fail_qa_php=True)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()

    workspaces_dir = tmp_path / "workspaces"
    writer = WorkspaceWriter(base_dir=workspaces_dir)
    store = OfficeStore(db_path=tmp_path / "office_cb.db")
    mail_svc = MailService(store=store)

    nodes = FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=store,
        mail_service=mail_svc,
    )

    checkpointer = MemorySaver()
    graph = compile_factory_graph(nodes, checkpointer=checkpointer, full_13_agents=True)

    project_id = "test_cb_qa_php_halt"
    state = create_initial_state(
        project_id=project_id,
        idea_inicial="App con fallo permanente en tests QA.",
    )

    config: RunnableConfig = {"configurable": {"thread_id": "thread-cb-qa-php"}}
    final_state = await graph.ainvoke(state, config=config)

    # Graph must halt at 3 retries
    assert final_state["retry_counts"]["qa_php"] == 3

    # Subsequent agents must not have run
    executed_ids = [rec.agent_id for rec in final_state["execution_history"]]
    assert AgentID.AGENTE_07_DEVOPS not in executed_ids
    assert AgentID.AGENTE_10_CISO not in executed_ids
    assert AgentID.AGENTE_12_MARKETING not in executed_ids
    assert AgentID.AGENTE_13_SALES_ANALYTICS not in executed_ids

    # Verify CRITICAL escalation email recorded in OfficeStore addressed to CEO
    all_emails = await store.get_emails(project_id)
    escalations = [
        e
        for e in all_emails
        if ("ceo" in e.recipient or "agente_00_ceo" in e.recipient)
        and e.priority == "CRITICAL"
        and "CIRCUIT BREAKER" in e.subject
    ]
    assert len(escalations) >= 1
    esc = escalations[0]
    assert "QA_PHP" in esc.subject
    assert esc.sender == "agente_qa_php@agentoffice.local"


@pytest.mark.asyncio
async def test_circuit_breaker_escalation_to_ceo_on_ciso(tmp_path: Path) -> None:
    """Verify that when CISO exceeds retries, a CRITICAL escalation email is registered for CEO."""
    gateway = MockLLMGateway(ciso_failures_sequence=[AgentID.AGENTE_07_DEVOPS] * 5)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()

    workspaces_dir = tmp_path / "workspaces"
    writer = WorkspaceWriter(base_dir=workspaces_dir)
    store = OfficeStore(db_path=tmp_path / "office_ciso_cb.db")
    mail_svc = MailService(store=store)

    nodes = FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=store,
        mail_service=mail_svc,
    )

    checkpointer = MemorySaver()
    graph = compile_factory_graph(nodes, checkpointer=checkpointer, full_13_agents=True)

    project_id = "test_cb_ciso_halt"
    state = create_initial_state(
        project_id=project_id,
        idea_inicial="App con infraestructura Docker persistentemente vulnerable.",
    )

    config: RunnableConfig = {"configurable": {"thread_id": "thread-cb-ciso"}}
    final_state = await graph.ainvoke(state, config=config)

    assert final_state["retry_counts"]["ciso"] == 3

    # Verify CRITICAL escalation email recorded in OfficeStore addressed to CEO
    all_emails = await store.get_emails(project_id)
    ciso_escalations = [
        e
        for e in all_emails
        if ("ceo" in e.recipient or "agente_00_ceo" in e.recipient)
        and e.priority == "CRITICAL"
        and "CISO" in e.subject
    ]
    assert len(ciso_escalations) >= 1
    assert ciso_escalations[0].sender == "agente_10_ciso@agentoffice.local"


def test_node_constants_exported() -> None:
    """Verify NODE_CEO_CHARTER and NODE_CEO_SIGNOFF constants."""
    assert NODE_CEO_CHARTER == "agente_00_ceo_charter"
    assert NODE_CEO_SIGNOFF == "agente_00_ceo_signoff"
