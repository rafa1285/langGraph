"""End-to-end integration tests for Phase 4: StateGraph workflow execution and routing."""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from app.graph.nodes import FactoryNodes
from app.graph.state import create_initial_state
from app.graph.workflow import compile_factory_graph
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.llm_gateway import MockLLMGateway
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


@pytest.mark.asyncio
async def test_workflow_happy_path_hybrid(tmp_path: Path) -> None:
    """Test 1: Happy path running all 10 agents and converging once at QA sync barrier."""
    gateway = MockLLMGateway()
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    checkpointer = MemorySaver()
    graph = compile_factory_graph(nodes, checkpointer=checkpointer)

    project_id = "test_happy_path"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="Plataforma de comercio electrónico con Laravel y FastAPI.",
    )

    config: RunnableConfig = {"configurable": {"thread_id": "thread-happy-path"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    # 1. Verify deliverables created in workspace
    project_workspace = tmp_path / "workspaces" / project_id
    assert project_workspace.exists()

    md_files = list(project_workspace.glob("*.md"))
    assert len(md_files) == 10

    for rec in final_state["execution_history"]:
        if rec.agent_id != AgentID.QA_SYNC_BARRIER:
            assert (tmp_path / rec.artifact_path).exists()

    # 2. Verify state attributes
    assert final_state["pre_sdd_doc"] != ""
    assert final_state["sdd_arquitectura"] != ""
    assert final_state["codigo_php"] != ""
    assert final_state["codigo_python"] != ""
    assert final_state["reporte_qa_php"] != ""
    assert final_state["reporte_qa_python"] != ""
    assert final_state["infraestructura_docker"] != ""
    assert final_state["dictamen_ciso"] != ""
    assert final_state["documentacion_rag"] != ""
    assert final_state["estrategia_growth"] != ""

    # 3. Verify statuses
    assert final_state["status_qa_php"] == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert final_state["status_qa_python"] == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert final_state["status_ciso"] == DeliverableStatus.BLINDADO_APTO_PRODUCCION


@pytest.mark.asyncio
async def test_workflow_asymmetric_qa_refactor_loop(tmp_path: Path) -> None:
    """Test 2: Python passes QA on first try while PHP fails once and refactors before barrier."""
    gateway = MockLLMGateway(fail_qa_php_once=True)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    checkpointer = MemorySaver()
    graph = compile_factory_graph(nodes, checkpointer=checkpointer)

    project_id = "test_asymm_qa"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="App con refactorización asimétrica.",
    )

    config: RunnableConfig = {"configurable": {"thread_id": "thread-asymm-qa"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    # Verify execution history contains the refactor cycle
    executed_agents = [rec.agent_id for rec in final_state["execution_history"]]

    # Laravel and QA PHP must appear twice
    assert executed_agents.count(AgentID.AGENTE_03_LARAVEL) == 2
    assert executed_agents.count(AgentID.AGENTE_05_QA_PHP) == 2

    # DevOps and subsequent agents must only run once
    assert executed_agents.count(AgentID.AGENTE_07_DEVOPS) == 1
    assert executed_agents.count(AgentID.AGENTE_10_CISO) == 1
    assert executed_agents.count(AgentID.AGENTE_08_DOCS) == 1
    assert executed_agents.count(AgentID.AGENTE_09_GROWTH) == 1

    # Verify retry count incremented to 1
    assert final_state["retry_counts"]["qa_php"] == 1
    assert final_state["retry_counts"]["qa_python"] == 0


@pytest.mark.asyncio
async def test_workflow_ciso_blockage_and_re_audit(tmp_path: Path) -> None:
    """Test 3: CISO blocks DevOps Docker infrastructure, requiring correction and re-audit."""
    gateway = MockLLMGateway(
        fail_ciso_target=AgentID.AGENTE_07_DEVOPS,
        fail_ciso_once=True,
    )
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    checkpointer = MemorySaver()
    graph = compile_factory_graph(nodes, checkpointer=checkpointer)

    project_id = "test_ciso_block"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="App con auditoría CISO exigente.",
    )

    config: RunnableConfig = {"configurable": {"thread_id": "thread-ciso-block"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    executed_agents = [rec.agent_id for rec in final_state["execution_history"]]

    # DevOps and CISO ran twice due to security blockage
    assert executed_agents.count(AgentID.AGENTE_07_DEVOPS) == 2
    assert executed_agents.count(AgentID.AGENTE_10_CISO) == 2

    # CISO retry count recorded
    assert final_state["retry_counts"]["ciso"] == 1

    # Eventually reaches Docs and Growth
    assert executed_agents.count(AgentID.AGENTE_08_DOCS) == 1
    assert executed_agents.count(AgentID.AGENTE_09_GROWTH) == 1
    assert final_state["status_ciso"] == DeliverableStatus.BLINDADO_APTO_PRODUCCION


@pytest.mark.asyncio
async def test_workflow_circuit_breaker_halts(tmp_path: Path) -> None:
    """Test 4: Circuit breaker terminates graph execution when max retries is exceeded."""
    gateway = MockLLMGateway(always_fail_qa_php=True)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    checkpointer = MemorySaver()
    graph = compile_factory_graph(nodes, checkpointer=checkpointer)

    project_id = "test_circuit_breaker"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="App condenada a fallar QA.",
    )

    config: RunnableConfig = {"configurable": {"thread_id": "thread-breaker"}}
    final_state = await graph.ainvoke(initial_state, config=config)

    # QA PHP retries must equal 3
    assert final_state["retry_counts"]["qa_php"] == 3

    # Graph must halt before DevOps, CISO, Docs, or Growth can run
    executed_agents = [rec.agent_id for rec in final_state["execution_history"]]
    assert AgentID.AGENTE_07_DEVOPS not in executed_agents
    assert AgentID.AGENTE_10_CISO not in executed_agents
    assert AgentID.AGENTE_08_DOCS not in executed_agents
    assert AgentID.AGENTE_09_GROWTH not in executed_agents
