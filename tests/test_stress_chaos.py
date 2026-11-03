"""Stress and Chaos tests for LangGraph Software Factory workflow."""

from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import settings
from app.graph.nodes import FactoryNodes
from app.graph.state import create_initial_state
from app.graph.workflow import compile_factory_graph
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.llm_gateway import MockLLMGateway
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


@pytest.mark.asyncio
async def test_chaos_scenario_perfect_storm_and_ciso_cross_bounce(
    tmp_path: Path,
) -> None:
    """Escenario 1: Tormenta Perfecta y Rebote Cruzado CISO -> PHP -> QA -> DevOps -> CISO.

    Verifica que:
    1. Laravel y FastAPI iteran de forma asimétrica sin disparar DevOps antes de tiempo.
    2. CISO bloquea culpando a Agente 03, el flujo retrocede a 03, pasa por QA PHP,
       cruza qa_sync_barrier, regenera DevOps y vuelve a CISO.
    3. CISO bloquea culpando a Agente 07, solo se re-ejecuta DevOps -> CISO (sin 03 ni 04).
    4. CISO finalmente aprueba y concluye en 08_docs -> 09_growth (100% completado).
    """
    db_file = tmp_path / "chaos_scenario1.db"
    gateway = MockLLMGateway(
        qa_php_failures_before_pass=2,
        qa_python_failures_before_pass=1,
        ciso_failures_sequence=[
            AgentID.AGENTE_03_LARAVEL,
            AgentID.AGENTE_07_DEVOPS,
        ],
    )
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    project_id = "chaos_perfect_storm"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="Sistema bancario de alta concurrencia con Laravel y FastAPI.",
    )
    config: RunnableConfig = {"configurable": {"thread_id": project_id}}

    async with AsyncSqliteSaver.from_conn_string(str(db_file)) as checkpointer:
        graph = compile_factory_graph(nodes, checkpointer=checkpointer, full_13_agents=False)
        final_state = await graph.ainvoke(initial_state, config=config)

    # Invocaciones exactas por agente LLM
    counts = gateway.invocation_counts
    assert counts[AgentID.AGENTE_01_PM] == 1
    assert counts[AgentID.AGENTE_02_ARCHITECT] == 1
    # PHP: 3 iteraciones iniciales + 1 tras rebote CISO = 4
    assert counts[AgentID.AGENTE_03_LARAVEL] == 4
    assert counts[AgentID.AGENTE_05_QA_PHP] == 4
    # Python: 2 iteraciones iniciales (1 fallo + 1 pase) y nunca re-ejecutado por CISO = 2
    assert counts[AgentID.AGENTE_04_FASTAPI] == 2
    assert counts[AgentID.AGENTE_06_QA_PYTHON] == 2
    # DevOps: 1 inicial + 1 tras rebote PHP + 1 tras rebote DevOps = 3
    assert counts[AgentID.AGENTE_07_DEVOPS] == 3
    # CISO: 1 culpando a PHP + 1 culpando a DevOps + 1 aprobando = 3
    assert counts[AgentID.AGENTE_10_CISO] == 3
    # Pipeline final
    assert counts[AgentID.AGENTE_08_DOCS] == 1
    assert counts[AgentID.AGENTE_09_GROWTH] == 1

    # Verificación del estado final
    assert final_state["status_ciso"] == DeliverableStatus.BLINDADO_APTO_PRODUCCION
    assert final_state["status_qa_php"] == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert final_state["status_qa_python"] == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert final_state["ciso_culprit"] is None
    assert final_state["retry_counts"]["qa_php"] == 2
    assert final_state["retry_counts"]["qa_python"] == 1
    assert final_state["retry_counts"]["ciso"] == 2

    # El último registro de ejecución debe ser Growth con 100% completado
    last_record = final_state["execution_history"][-1]
    assert last_record.agent_id == AgentID.AGENTE_09_GROWTH
    assert last_record.status == DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100


@pytest.mark.asyncio
async def test_chaos_scenario_circuit_breaker_collapse_on_ciso(
    tmp_path: Path,
) -> None:
    """Escenario 2: Colapso por Circuit Breaker en CISO tras exceder MAX_RETRIES_PER_GATE.

    Verifica que:
    1. Al alcanzar 3 bloqueos en CISO (retry_counts['ciso'] == 3), el grafo corta hacia END.
    2. Agente 08 (Docs) y Agente 09 (Growth) tienen 0 invocaciones.
    3. El checkpoint en SQLite conserva el estado íntegro y el dictamen de bloqueo.
    """
    db_file = tmp_path / "chaos_scenario2.db"
    gateway = MockLLMGateway(
        ciso_failures_sequence=[AgentID.AGENTE_07_DEVOPS] * 5,
    )
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    project_id = "chaos_ciso_collapse"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="App fintech con fallo persistente de contenedor Docker.",
    )
    config: RunnableConfig = {"configurable": {"thread_id": project_id}}

    async with AsyncSqliteSaver.from_conn_string(str(db_file)) as checkpointer:
        graph = compile_factory_graph(nodes, checkpointer=checkpointer, full_13_agents=False)
        final_state = await graph.ainvoke(initial_state, config=config)

        # Consultar checkpoint guardado en SQLite mediante aget_state
        saved_snapshot = await graph.aget_state(config)
        assert saved_snapshot is not None
        assert saved_snapshot.values["project_id"] == project_id

    counts = gateway.invocation_counts
    # CISO y DevOps deben haber alcanzado exactamente 3 ejecuciones
    assert counts[AgentID.AGENTE_07_DEVOPS] == settings.MAX_RETRIES_PER_GATE
    assert counts[AgentID.AGENTE_10_CISO] == settings.MAX_RETRIES_PER_GATE

    # Cortocircuito: Docs y Growth NUNCA se ejecutaron
    assert counts[AgentID.AGENTE_08_DOCS] == 0
    assert counts[AgentID.AGENTE_09_GROWTH] == 0

    # Estado final congelado en SQLite
    assert final_state["retry_counts"]["ciso"] == settings.MAX_RETRIES_PER_GATE
    assert final_state["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
    assert final_state["ciso_culprit"] == AgentID.AGENTE_07_DEVOPS
    assert "BLOQUEADO" in final_state["dictamen_ciso"]


@pytest.mark.asyncio
async def test_chaos_scenario_disk_artifacts_audit(tmp_path: Path) -> None:
    """Escenario 3: Auditoría de Archivos Físicos en Disco.

    Verifica que todos los artefactos intermedios generados durante las iteraciones
    y refactorizaciones se escriban secuencialmente en workspaces/{project_id}/
    sin sobrescribirse ni perder pasos anteriores.
    """
    db_file = tmp_path / "chaos_scenario3.db"
    gateway = MockLLMGateway(
        qa_php_failures_before_pass=2,
        qa_python_failures_before_pass=1,
        ciso_failures_sequence=[
            AgentID.AGENTE_03_LARAVEL,
            AgentID.AGENTE_07_DEVOPS,
        ],
    )
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    project_id = "chaos_artifacts_audit"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="Plataforma de pagos con auditoría exhaustiva de entregables.",
    )
    config: RunnableConfig = {"configurable": {"thread_id": project_id}}

    async with AsyncSqliteSaver.from_conn_string(str(db_file)) as checkpointer:
        graph = compile_factory_graph(nodes, checkpointer=checkpointer, full_13_agents=False)
        final_state = await graph.ainvoke(initial_state, config=config)

    workspace_dir = tmp_path / "workspaces" / project_id
    assert workspace_dir.exists()

    generated_files = sorted(workspace_dir.glob("*.md"))
    # En Escenario 1 hay 22 llamadas a agentes LLM -> 22 archivos generados
    assert len(generated_files) == 22

    # Verificar que cada archivo existe, no está vacío y coincide con el historial
    llm_history_records = [
        rec
        for rec in final_state["execution_history"]
        if rec.agent_id != AgentID.QA_SYNC_BARRIER
    ]
    assert len(llm_history_records) == 22

    for rec in llm_history_records:
        target_path = tmp_path / rec.artifact_path
        assert target_path.exists(), f"El archivo {target_path} no existe en disco."
        content = target_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 0, f"El archivo {target_path} está vacío."

    # Verificar que existan versiones múltiples secuenciales de Laravel y DevOps
    laravel_files = [f for f in generated_files if "agente_03_laravel" in f.name]
    assert len(laravel_files) == 4

    devops_files = [f for f in generated_files if "agente_07_devops" in f.name]
    assert len(devops_files) == 3

    ciso_files = [f for f in generated_files if "agente_10_ciso" in f.name]
    assert len(ciso_files) == 3
