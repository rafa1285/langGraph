"""LangGraph workflow definition, routing edges, and compilation for Software Factory."""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes import FactoryNodes
from app.graph.router import (
    route_after_architect,
    route_after_ciso,
    route_after_qa_php,
    route_after_qa_python,
    route_after_sync_barrier,
)
from app.graph.state import SoftwareFactoryState
from app.schemas.routing import AgentID

FactoryGraph = CompiledStateGraph[
    SoftwareFactoryState,
    None,
    SoftwareFactoryState,
    SoftwareFactoryState,
]

__all__ = [
    "FactoryGraph",
    "compile_factory_graph",
    "route_after_architect",
    "route_after_ciso",
    "route_after_qa_php",
    "route_after_qa_python",
    "route_after_sync_barrier",
]


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
