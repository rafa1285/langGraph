"""LangGraph workflow definition, routing edges, and compilation for Software Factory."""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.config import settings
from app.graph.nodes import FactoryNodes
from app.graph.state import SoftwareFactoryState
from app.schemas.routing import AgentID, DeliverableStatus

FactoryGraph = CompiledStateGraph[
    SoftwareFactoryState,
    None,
    SoftwareFactoryState,
    SoftwareFactoryState,
]


def route_after_architect(state: SoftwareFactoryState) -> list[str]:
    """Fan-out to Laravel and/or FastAPI nodes based on architectural stack requirements."""
    req_php = state.get("requiere_php", True)
    req_python = state.get("requiere_python", True)

    if req_php and req_python:
        return [AgentID.AGENTE_03_LARAVEL.value, AgentID.AGENTE_04_FASTAPI.value]
    if req_php:
        return [AgentID.AGENTE_03_LARAVEL.value]
    if req_python:
        return [AgentID.AGENTE_04_FASTAPI.value]

    return [AgentID.AGENTE_03_LARAVEL.value, AgentID.AGENTE_04_FASTAPI.value]


def route_after_qa_php(state: SoftwareFactoryState) -> str:
    """Route PHP workflow based on QA audit approval, circuit breaker, or refactor."""
    if state.get("status_qa_php") == DeliverableStatus.APROBADO_PARA_DESPLIEGUE:
        return AgentID.QA_SYNC_BARRIER.value

    if state.get("retry_counts", {}).get("qa_php", 0) >= settings.MAX_RETRIES_PER_GATE:
        return END

    return AgentID.AGENTE_03_LARAVEL.value


def route_after_qa_python(state: SoftwareFactoryState) -> str:
    """Route Python workflow based on QA audit approval, circuit breaker, or refactor."""
    if state.get("status_qa_python") == DeliverableStatus.APROBADO_PARA_DESPLIEGUE:
        return AgentID.QA_SYNC_BARRIER.value

    if state.get("retry_counts", {}).get("qa_python", 0) >= settings.MAX_RETRIES_PER_GATE:
        return END

    return AgentID.AGENTE_04_FASTAPI.value


def route_after_sync_barrier(state: SoftwareFactoryState) -> str:
    """Evaluate whether both parallel QA gates have reached approval before DevOps."""
    php_ready = state.get("status_qa_php") == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    python_ready = (
        state.get("status_qa_python") == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    )

    if php_ready and python_ready:
        return AgentID.AGENTE_07_DEVOPS.value

    return END


def route_after_ciso(state: SoftwareFactoryState) -> str:
    """Route security audit results to docs, circuit breaker, or designated culprit."""
    if state.get("status_ciso") == DeliverableStatus.BLINDADO_APTO_PRODUCCION:
        return AgentID.AGENTE_08_DOCS.value

    if state.get("retry_counts", {}).get("ciso", 0) >= settings.MAX_RETRIES_PER_GATE:
        return END

    if state.get("status_ciso") == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD:
        culprit = state.get("ciso_culprit")
        if culprit == AgentID.AGENTE_03_LARAVEL:
            return AgentID.AGENTE_03_LARAVEL.value
        if culprit == AgentID.AGENTE_04_FASTAPI:
            return AgentID.AGENTE_04_FASTAPI.value
        return AgentID.AGENTE_07_DEVOPS.value

    return AgentID.AGENTE_08_DOCS.value


def compile_factory_graph(
    nodes: FactoryNodes,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> FactoryGraph:
    """Build, configure edges, and compile the Software Factory StateGraph."""
    builder = StateGraph(SoftwareFactoryState)

    # 1. Register all 11 nodes
    builder.add_node(AgentID.AGENTE_01_PM.value, nodes.node_01_pm)
    builder.add_node(AgentID.AGENTE_02_ARCHITECT.value, nodes.node_02_architect)
    builder.add_node(AgentID.AGENTE_03_LARAVEL.value, nodes.node_03_laravel)
    builder.add_node(AgentID.AGENTE_04_FASTAPI.value, nodes.node_04_fastapi)
    builder.add_node(AgentID.AGENTE_05_QA_PHP.value, nodes.node_05_qa_php)
    builder.add_node(AgentID.AGENTE_06_QA_PYTHON.value, nodes.node_06_qa_python)
    builder.add_node(AgentID.QA_SYNC_BARRIER.value, nodes.node_qa_sync_barrier)
    builder.add_node(AgentID.AGENTE_07_DEVOPS.value, nodes.node_07_devops)
    builder.add_node(AgentID.AGENTE_10_CISO.value, nodes.node_10_ciso)
    builder.add_node(AgentID.AGENTE_08_DOCS.value, nodes.node_08_docs)
    builder.add_node(AgentID.AGENTE_09_GROWTH.value, nodes.node_09_growth)

    # 2. Sequential entry: START -> PM -> Architect
    builder.add_edge(START, AgentID.AGENTE_01_PM.value)
    builder.add_edge(AgentID.AGENTE_01_PM.value, AgentID.AGENTE_02_ARCHITECT.value)

    # 3. Parallel Fan-Out after Architect
    builder.add_conditional_edges(
        AgentID.AGENTE_02_ARCHITECT.value,
        route_after_architect,
    )

    # 4. Dev to QA
    builder.add_edge(AgentID.AGENTE_03_LARAVEL.value, AgentID.AGENTE_05_QA_PHP.value)
    builder.add_edge(AgentID.AGENTE_04_FASTAPI.value, AgentID.AGENTE_06_QA_PYTHON.value)

    # 5. QA conditional feedback loops
    builder.add_conditional_edges(AgentID.AGENTE_05_QA_PHP.value, route_after_qa_php)
    builder.add_conditional_edges(AgentID.AGENTE_06_QA_PYTHON.value, route_after_qa_python)

    # 6. Synchronization Barrier
    builder.add_conditional_edges(AgentID.QA_SYNC_BARRIER.value, route_after_sync_barrier)

    # 7. DevOps to CISO
    builder.add_edge(AgentID.AGENTE_07_DEVOPS.value, AgentID.AGENTE_10_CISO.value)

    # 8. CISO conditional multi-directional routing
    builder.add_conditional_edges(AgentID.AGENTE_10_CISO.value, route_after_ciso)

    # 9. Terminal sequence: Docs -> Growth -> END
    builder.add_edge(AgentID.AGENTE_08_DOCS.value, AgentID.AGENTE_09_GROWTH.value)
    builder.add_edge(AgentID.AGENTE_09_GROWTH.value, END)

    return builder.compile(checkpointer=checkpointer)
