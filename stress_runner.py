"""Executable stress and chaos runner demonstrating complex fault-tolerance scenarios."""

import asyncio
import shutil
import time
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import settings
from app.graph.nodes import FactoryNodes
from app.graph.state import create_initial_state
from app.graph.workflow import compile_factory_graph
from app.schemas.routing import AgentID, DeliverableStatus, StepExecutionRecord
from app.services.llm_gateway import MockLLMGateway
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


def _format_table(records: list[StepExecutionRecord]) -> str:
    """Format execution history records as an ASCII table with step-by-step audit details."""
    col_step = 8
    col_agent = 21
    col_status = 38
    col_retries = 24
    col_dest = 38
    col_file = 28

    sep_line = (
        f"+{'-' * col_step}+{'-' * col_agent}+{'-' * col_status}"
        f"+{'-' * col_retries}+{'-' * col_dest}+{'-' * col_file}+"
    )
    header = (
        f"| {'Paso #':<{col_step - 2}} "
        f"| {'Agente Ejecutado':<{col_agent - 2}} "
        f"| {'Estado / Veredicto':<{col_status - 2}} "
        f"| {'Reintentos (PHP/PY/CISO)':<{col_retries - 2}} "
        f"| {'Destino Siguiente':<{col_dest - 2}} "
        f"| {'Archivo Generado':<{col_file - 2}} |"
    )

    lines: list[str] = [sep_line, header, sep_line]

    retries_php = 0
    retries_py = 0
    retries_ciso = 0

    for idx, rec in enumerate(records, start=1):
        # Update running retry counters
        if rec.status == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
            if rec.agent_id == AgentID.AGENTE_05_QA_PHP:
                retries_php += 1
            elif rec.agent_id == AgentID.AGENTE_06_QA_PYTHON:
                retries_py += 1
        elif rec.status == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD:
            if rec.agent_id == AgentID.AGENTE_10_CISO:
                retries_ciso += 1

        retry_str = f"{retries_php} / {retries_py} / {retries_ciso}"
        file_display = (
            Path(rec.artifact_path).name
            if not rec.artifact_path.startswith("barrier://")
            else "(barrera en memoria)"
        )

        step_label = f"[{idx:02d}]"
        agent_label = rec.agent_id.value
        status_label = rec.status.value
        dest_label = rec.target_next or "END"

        row = (
            f"| {step_label:<{col_step - 2}} "
            f"| {agent_label:<{col_agent - 2}} "
            f"| {status_label:<{col_status - 2}} "
            f"| {retry_str:<{col_retries - 2}} "
            f"| {dest_label:<{col_dest - 2}} "
            f"| {file_display:<{col_file - 2}} |"
        )
        lines.append(row)

    lines.append(sep_line)
    return "\n".join(lines)


async def run_scenario_1(work_dir: Path) -> None:
    """Run Scenario 1: Perfect storm with cross-rebounds CISO -> PHP -> DevOps -> CISO."""
    print("\n" + "=" * 163)
    print(" ESCENARIO 1: TORMENTA PERFECTA Y REBOTE CRUZADO (CISO -> PHP -> QA -> DEVOPS -> CISO)")
    print("=" * 163)
    print("Configuración:")
    print("  - qa_php_failures_before_pass   : 2 (Falla 2 veces antes de aprobar)")
    print("  - qa_python_failures_before_pass: 1 (Falla 1 vez antes de aprobar)")
    print("  - ciso_failures_sequence        : [agente_03_laravel, agente_07_devops]")
    print("=" * 163)

    db_path = work_dir / "scenario1.db"
    gateway = MockLLMGateway(
        qa_php_failures_before_pass=2,
        qa_python_failures_before_pass=1,
        ciso_failures_sequence=[
            AgentID.AGENTE_03_LARAVEL,
            AgentID.AGENTE_07_DEVOPS,
        ],
    )
    loader = PromptLoader(prompts_dir=Path("prompts"))
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=work_dir / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    project_id = "stress_scenario_1"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="Plataforma de liquidación bancaria de alta concurrencia en tiempo real.",
    )
    config: RunnableConfig = {"configurable": {"thread_id": project_id}}

    start_time = time.perf_counter()
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        graph = compile_factory_graph(nodes, checkpointer=checkpointer)
        final_state = await graph.ainvoke(initial_state, config=config)
    elapsed = time.perf_counter() - start_time

    records = final_state["execution_history"]
    print(_format_table(records))

    print("\n--- RESUMEN ESCENARIO 1 ---")
    print(f"Tiempo Total de Ejecución: {elapsed:.4f} segundos")
    print(f"Pasos Totales en Historial : {len(records)}")
    num_disk_files = len(list((work_dir / "workspaces" / project_id).glob("*.md")))
    print(f"Archivos Físicos en Disco : {num_disk_files}")
    print(f"Estado Final CISO         : {final_state['status_ciso'].value}")
    print(f"Último Estado del Grafo   : {records[-1].status.value}")
    print("\nConteo Exacto de Invocaciones por Agente LLM:")
    for agent_id, count in gateway.invocation_counts.items():
        if agent_id != AgentID.QA_SYNC_BARRIER:
            print(f"  - {agent_id.value:<22}: {count} invocaciones")


async def run_scenario_2(work_dir: Path) -> None:
    """Run Scenario 2: Circuit breaker collapse on CISO after exceeding MAX_RETRIES_PER_GATE."""
    print("\n" + "=" * 163)
    print(" ESCENARIO 2: COLAPSO POR CIRCUIT BREAKER EN CISO (MAX_RETRIES_PER_GATE = 3)")
    print("=" * 163)
    print("Configuración:")
    print("  - ciso_failures_sequence: [agente_07_devops] * 5 (Supera límite de 3 bloqueos)")
    print("  - Comportamiento esperado: Cortocircuito inmediato hacia END en el intento 3.")
    print("=" * 163)

    db_path = work_dir / "scenario2.db"
    gateway = MockLLMGateway(
        ciso_failures_sequence=[AgentID.AGENTE_07_DEVOPS] * 5,
    )
    loader = PromptLoader(prompts_dir=Path("prompts"))
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=work_dir / "workspaces")
    nodes = FactoryNodes(gateway, loader, writer)

    project_id = "stress_scenario_2"
    initial_state = create_initial_state(
        project_id=project_id,
        idea_inicial="Infraestructura Docker vulnerable con fuga de credenciales persistente.",
    )
    config: RunnableConfig = {"configurable": {"thread_id": project_id}}

    start_time = time.perf_counter()
    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        graph = compile_factory_graph(nodes, checkpointer=checkpointer)
        final_state = await graph.ainvoke(initial_state, config=config)
    elapsed = time.perf_counter() - start_time

    records = final_state["execution_history"]
    print(_format_table(records))

    print("\n--- RESUMEN ESCENARIO 2 ---")
    print(f"Tiempo Total de Ejecución: {elapsed:.4f} segundos")
    print(f"Pasos Totales en Historial : {len(records)}")
    ciso_retries = final_state["retry_counts"]["ciso"]
    max_retries = settings.MAX_RETRIES_PER_GATE
    culprit_str = (
        final_state["ciso_culprit"].value
        if final_state["ciso_culprit"]
        else "None"
    )
    docs_called = gateway.invocation_counts[AgentID.AGENTE_08_DOCS] > 0
    growth_called = gateway.invocation_counts[AgentID.AGENTE_09_GROWTH] > 0

    print(f"Reintentos Registrados CISO: {ciso_retries} / {max_retries}")
    print(f"Estado Final CISO         : {final_state['status_ciso'].value}")
    print(f"Culpable Detectado        : {culprit_str}")
    print(f"Docs (Agente 08) Ejecutado: {'SÍ' if docs_called else 'NO (0 invocaciones)'}")
    print(f"Growth (09) Ejecutado     : {'SÍ' if growth_called else 'NO (0 invocaciones)'}")
    print("\nConteo Exacto de Invocaciones por Agente LLM:")
    for agent_id, count in gateway.invocation_counts.items():
        if agent_id != AgentID.QA_SYNC_BARRIER:
            print(f"  - {agent_id.value:<22}: {count} invocaciones")


async def main() -> None:
    """Execute both stress and chaos scenarios and clean up temporary workspaces."""
    temp_dir = Path("workspaces") / "_stress_chaos_run"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        await run_scenario_1(temp_dir)
        await run_scenario_2(temp_dir)
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    asyncio.run(main())
