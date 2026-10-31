"""Unit tests for Phase 3: LLM gateway, payload construction, and FactoryNodes."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.graph.nodes import FactoryNodes, _build_user_payload
from app.graph.state import SoftwareFactoryState, create_initial_state
from app.schemas.routing import AgentID, DeliverableStatus, StepExecutionRecord
from app.services.llm_gateway import GeminiLLMGateway, MockLLMGateway
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


def _append_history(state: SoftwareFactoryState, updates: dict[str, object]) -> None:
    """Helper to safely type-check and append execution history items."""
    hist = updates.get("execution_history")
    if isinstance(hist, list):
        for item in hist:
            if isinstance(item, StepExecutionRecord):
                state["execution_history"].append(item)


def test_build_user_payload_standard_and_rebound_contexts() -> None:
    """Test payload generation across nodes including QA refactoring and CISO security blocks."""
    state = create_initial_state(
        project_id="test_proj_001",
        idea_inicial="Crear un sistema SaaS de gestión de facturas.",
    )

    # 1. PM payload
    pm_payload = _build_user_payload(AgentID.AGENTE_01_PM, state)
    assert "SaaS de gestión de facturas" in pm_payload

    # 2. Architect payload
    state["pre_sdd_doc"] = "# Pre-SDD\nRequisitos de arquitectura."
    arch_payload = _build_user_payload(AgentID.AGENTE_02_ARCHITECT, state)
    assert "# Pre-SDD" in arch_payload

    # 3. Laravel payload normal
    state["sdd_arquitectura"] = "# SDD\nArquitectura modular."
    state["codigo_php"] = "<?php // codigo v1"
    lar_normal = _build_user_payload(AgentID.AGENTE_03_LARAVEL, state)
    assert "Arquitectura modular" in lar_normal
    assert "INFORME DE RECHAZO" not in lar_normal

    # 4. Laravel rebound from QA PHP
    state["status_qa_php"] = DeliverableStatus.RECHAZADO_PARA_REFACTOR
    state["reporte_qa_php"] = "Error crítico en validaciones."
    lar_qa_rebound = _build_user_payload(AgentID.AGENTE_03_LARAVEL, state)
    assert "CÓDIGO PHP PREVIO A REFACTORIZAR" in lar_qa_rebound
    assert "Error crítico en validaciones." in lar_qa_rebound

    # 5. Laravel rebound from CISO
    state["status_qa_php"] = DeliverableStatus.PENDIENTE
    state["status_ciso"] = DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
    state["ciso_culprit"] = AgentID.AGENTE_03_LARAVEL
    state["dictamen_ciso"] = "Inyección SQL detectada en repositorio."
    lar_ciso_rebound = _build_user_payload(AgentID.AGENTE_03_LARAVEL, state)
    assert "CÓDIGO PHP PREVIO CON VULNERABILIDADES" in lar_ciso_rebound
    assert "Inyección SQL detectada" in lar_ciso_rebound

    # 6. FastAPI rebound from QA Python
    state["status_ciso"] = DeliverableStatus.PENDIENTE
    state["ciso_culprit"] = None
    state["codigo_python"] = "def endpoint(): pass"
    state["status_qa_python"] = DeliverableStatus.RECHAZADO_PARA_REFACTOR
    state["reporte_qa_python"] = "Mypy estricto fallido en línea 10."
    py_qa_rebound = _build_user_payload(AgentID.AGENTE_04_FASTAPI, state)
    assert "CÓDIGO PYTHON PREVIO A REFACTORIZAR" in py_qa_rebound
    assert "Mypy estricto fallido" in py_qa_rebound

    # 7. DevOps rebound from CISO
    state["infraestructura_docker"] = "version: '3.8'\nservices: web:"
    state["status_ciso"] = DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
    state["ciso_culprit"] = AgentID.AGENTE_07_DEVOPS
    state["dictamen_ciso"] = "Contenedor root expuesto."
    devops_payload = _build_user_payload(AgentID.AGENTE_07_DEVOPS, state)
    assert "INFRAESTRUCTURA DOCKER PREVIA BLOQUEADA" in devops_payload
    assert "Contenedor root expuesto." in devops_payload


@pytest.mark.asyncio
async def test_factory_nodes_end_to_end_mock(tmp_path: Path) -> None:
    """Test full sequential node execution using MockLLMGateway and temporary workspace."""
    gateway = MockLLMGateway()
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    state = create_initial_state("proj_pipeline_test", "Crear API SaaS")

    # 1. Node 01 PM
    u1 = await nodes.node_01_pm(state)
    state["pre_sdd_doc"] = str(u1["pre_sdd_doc"])
    _append_history(state, u1)
    assert state["pre_sdd_doc"] != ""
    assert len(state["execution_history"]) == 1
    assert state["execution_history"][0].agent_id == AgentID.AGENTE_01_PM

    # 2. Node 02 Architect
    u2 = await nodes.node_02_architect(state)
    state["sdd_arquitectura"] = str(u2["sdd_arquitectura"])
    state["requiere_php"] = bool(u2["requiere_php"])
    state["requiere_python"] = bool(u2["requiere_python"])
    _append_history(state, u2)
    assert state["sdd_arquitectura"] != ""
    assert state["requiere_php"] is True
    assert state["requiere_python"] is True
    assert len(state["execution_history"]) == 2

    # 3. Node 03 Laravel
    u3 = await nodes.node_03_laravel(state)
    state["codigo_php"] = str(u3["codigo_php"])
    status_php_dev: DeliverableStatus = DeliverableStatus(str(u3["status_qa_php"]))
    state["status_qa_php"] = status_php_dev
    _append_history(state, u3)
    assert "TaskController" in state["codigo_php"]
    assert status_php_dev == DeliverableStatus.IMPLEMENTADO_PARA_REVISION

    # 4. Node 04 FastAPI
    u4 = await nodes.node_04_fastapi(state)
    state["codigo_python"] = str(u4["codigo_python"])
    status_py_dev: DeliverableStatus = DeliverableStatus(str(u4["status_qa_python"]))
    state["status_qa_python"] = status_py_dev
    _append_history(state, u4)
    assert "FastAPI" in state["codigo_python"]
    assert status_py_dev == DeliverableStatus.IMPLEMENTADO_PARA_REVISION

    # 5. Node 05 QA PHP (Approved)
    u5 = await nodes.node_05_qa_php(state)
    status_qa_php: DeliverableStatus = DeliverableStatus(str(u5["status_qa_php"]))
    state["status_qa_php"] = status_qa_php
    _append_history(state, u5)
    assert status_qa_php == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert state["retry_counts"]["qa_php"] == 0

    # 6. Node 06 QA Python (Approved)
    u6 = await nodes.node_06_qa_python(state)
    status_qa_python: DeliverableStatus = DeliverableStatus(str(u6["status_qa_python"]))
    state["status_qa_python"] = status_qa_python
    _append_history(state, u6)
    assert status_qa_python == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert state["retry_counts"]["qa_python"] == 0

    # 7. Node QA Sync Barrier
    u_barrier = await nodes.node_qa_sync_barrier(state)
    _append_history(state, u_barrier)
    assert state["execution_history"][-1].agent_id == AgentID.QA_SYNC_BARRIER

    # 8. Node 07 DevOps
    u7 = await nodes.node_07_devops(state)
    state["infraestructura_docker"] = str(u7["infraestructura_docker"])
    _append_history(state, u7)
    assert state["infraestructura_docker"] != ""

    # 9. Node 10 CISO (Approved)
    u10 = await nodes.node_10_ciso(state)
    status_ciso: DeliverableStatus = DeliverableStatus(str(u10["status_ciso"]))
    state["status_ciso"] = status_ciso
    _append_history(state, u10)
    assert status_ciso == DeliverableStatus.BLINDADO_APTO_PRODUCCION

    # 10. Node 08 Docs
    u8 = await nodes.node_08_docs(state)
    state["documentacion_rag"] = str(u8["documentacion_rag"])
    _append_history(state, u8)
    assert state["documentacion_rag"] != ""

    # 11. Node 09 Growth
    u9 = await nodes.node_09_growth(state)
    state["estrategia_growth"] = str(u9["estrategia_growth"])
    _append_history(state, u9)
    assert state["estrategia_growth"] != ""


@pytest.mark.asyncio
async def test_node_architect_inactive_stack_pre_approval(tmp_path: Path) -> None:
    """Test that Architect pre-approves QA status for stacks that are marked as inactive."""
    gateway = MockLLMGateway(sdd_requires_php=False, sdd_requires_python=True)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    state = create_initial_state("proj_no_php", "Python only project")
    state["pre_sdd_doc"] = "# Pre-SDD"

    updates = await nodes.node_02_architect(state)
    assert updates["requiere_php"] is False
    assert updates["requiere_python"] is True
    assert updates["status_qa_php"] == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert "status_qa_python" not in updates


@pytest.mark.asyncio
async def test_node_qa_rejection_increments_retry_count(tmp_path: Path) -> None:
    """Test that QA PHP rejection increments the retry counter."""
    gateway = MockLLMGateway(fail_qa_php_once=True)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    state = create_initial_state("proj_qa_retry", "Retry test")
    state["sdd_arquitectura"] = "# SDD"
    state["codigo_php"] = "<?php // bugged"

    updates = await nodes.node_05_qa_php(state)
    assert updates["status_qa_php"] == DeliverableStatus.RECHAZADO_PARA_REFACTOR
    retry_update = updates.get("retry_counts")
    assert isinstance(retry_update, dict)
    assert retry_update["qa_php"] == 1


@pytest.mark.asyncio
async def test_node_ciso_blockage_and_qa_reset(tmp_path: Path) -> None:
    """Test CISO security blockage: increment counter, set culprit, and reset QA status."""
    gateway = MockLLMGateway(fail_ciso_target=AgentID.AGENTE_03_LARAVEL)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    state = create_initial_state("proj_ciso_block", "Security test")
    state["status_qa_php"] = DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    state["status_qa_python"] = DeliverableStatus.APROBADO_PARA_DESPLIEGUE

    updates = await nodes.node_10_ciso(state)
    assert updates["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
    assert updates["ciso_culprit"] == AgentID.AGENTE_03_LARAVEL
    assert updates["status_qa_php"] == DeliverableStatus.PENDIENTE
    retry_update = updates.get("retry_counts")
    assert isinstance(retry_update, dict)
    assert retry_update["ciso"] == 1


@pytest.mark.asyncio
async def test_gemini_llm_gateway_retry_on_429() -> None:
    """Test that GeminiLLMGateway retries with backoff upon capturing quota limit errors."""
    gateway = GeminiLLMGateway(api_key="mock-key")

    mock_chat = AsyncMock()
    # First two attempts fail with 429 quota error, third attempt succeeds
    mock_chat.ainvoke.side_effect = [
        Exception("429 ResourceExhausted: Quota exceeded"),
        Exception("429 ResourceExhausted: Quota exceeded"),
        AsyncMock(content="--- \n origen: 'agente_01_pm' \n --- \n OK"),
    ]

    with patch("app.services.llm_gateway.ChatGoogleGenerativeAI", return_value=mock_chat):
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await gateway.invoke_agent(
                agent_id=AgentID.AGENTE_01_PM,
                system_prompt="sys prompt",
                user_payload="payload",
            )
            assert "OK" in result
            assert mock_chat.ainvoke.call_count == 3
            assert mock_sleep.call_count >= 2
