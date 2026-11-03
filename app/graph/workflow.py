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
    route_after_ui_ux,
)
from app.graph.state import SoftwareFactoryState
from app.schemas.routing import AgentID

FactoryGraph = CompiledStateGraph[
    SoftwareFactoryState,
    None,
    SoftwareFactoryState,
    SoftwareFactoryState,
]

NODE_CEO_CHARTER = "agente_00_ceo_charter"
NODE_CEO_SIGNOFF = "agente_00_ceo_signoff"

__all__ = [
    "FactoryGraph",
    "NODE_CEO_CHARTER",
    "NODE_CEO_SIGNOFF",
    "compile_factory_graph",
    "route_after_architect",
    "route_after_ciso",
    "route_after_qa_php",
    "route_after_qa_python",
    "route_after_sync_barrier",
    "route_after_ui_ux",
]


def compile_factory_graph(
    nodes: FactoryNodes,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    full_13_agents: bool = True,
) -> FactoryGraph:
    """Build, configure edges, and compile the Software Factory StateGraph.

    Args:
        nodes: FactoryNodes instance containing node callbacks.
        checkpointer: Optional checkpointer for state persistence.
        full_13_agents: If True (standard default), compiles the complete 13-agent
            topology including CEO charter/signoff, UI/UX design, Marketing TOFU,
            and Sales BI. If False, compiles the legacy 10-agent pipeline.
    """
    builder = StateGraph(SoftwareFactoryState)

    if not full_13_agents:
        # Legacy 10-agent pipeline
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

        builder.add_edge(START, AgentID.AGENTE_01_PM.value)
        builder.add_edge(AgentID.AGENTE_01_PM.value, AgentID.AGENTE_02_ARCHITECT.value)
        builder.add_conditional_edges(
            AgentID.AGENTE_02_ARCHITECT.value,
            route_after_architect,
        )
        builder.add_edge(AgentID.AGENTE_03_LARAVEL.value, AgentID.AGENTE_05_QA_PHP.value)
        builder.add_edge(AgentID.AGENTE_04_FASTAPI.value, AgentID.AGENTE_06_QA_PYTHON.value)
        builder.add_conditional_edges(AgentID.AGENTE_05_QA_PHP.value, route_after_qa_php)
        builder.add_conditional_edges(AgentID.AGENTE_06_QA_PYTHON.value, route_after_qa_python)
        builder.add_conditional_edges(AgentID.QA_SYNC_BARRIER.value, route_after_sync_barrier)
        builder.add_edge(AgentID.AGENTE_07_DEVOPS.value, AgentID.AGENTE_10_CISO.value)
        builder.add_conditional_edges(AgentID.AGENTE_10_CISO.value, route_after_ciso)
        builder.add_edge(AgentID.AGENTE_08_DOCS.value, AgentID.AGENTE_09_GROWTH.value)
        builder.add_edge(AgentID.AGENTE_09_GROWTH.value, END)

        return builder.compile(checkpointer=checkpointer)

    # Standard full 13-agent pipeline
    builder.add_node(NODE_CEO_CHARTER, nodes.ceo_charter_node)
    builder.add_node(AgentID.AGENTE_01_PM.value, nodes.node_01_pm)
    builder.add_node(AgentID.AGENTE_02_ARCHITECT.value, nodes.node_02_architect)
    builder.add_node(AgentID.AGENTE_11_UI_UX.value, nodes.ui_ux_node)
    builder.add_node(AgentID.AGENTE_03_LARAVEL.value, nodes.node_03_laravel)
    builder.add_node(AgentID.AGENTE_04_FASTAPI.value, nodes.node_04_fastapi)
    builder.add_node(AgentID.AGENTE_05_QA_PHP.value, nodes.node_05_qa_php)
    builder.add_node(AgentID.AGENTE_06_QA_PYTHON.value, nodes.node_06_qa_python)
    builder.add_node(AgentID.QA_SYNC_BARRIER.value, nodes.node_qa_sync_barrier)
    builder.add_node(AgentID.AGENTE_07_DEVOPS.value, nodes.node_07_devops)
    builder.add_node(AgentID.AGENTE_10_CISO.value, nodes.node_10_ciso)
    builder.add_node(AgentID.AGENTE_08_DOCS.value, nodes.node_08_docs)
    builder.add_node(AgentID.AGENTE_12_MARKETING.value, nodes.marketing_node)
    builder.add_node(AgentID.AGENTE_13_SALES_ANALYTICS.value, nodes.sales_analytics_node)
    builder.add_node(NODE_CEO_SIGNOFF, nodes.ceo_signoff_node)

    # 1. START -> CEO Charter
    builder.add_edge(START, NODE_CEO_CHARTER)

    # 2. CEO Charter -> PM
    builder.add_edge(NODE_CEO_CHARTER, AgentID.AGENTE_01_PM.value)

    # 3. PM -> Architect
    builder.add_edge(AgentID.AGENTE_01_PM.value, AgentID.AGENTE_02_ARCHITECT.value)

    # 4. Architect -> UI/UX
    builder.add_edge(AgentID.AGENTE_02_ARCHITECT.value, AgentID.AGENTE_11_UI_UX.value)

    # 5. UI/UX -> Development execution (parallel fan-out)
    builder.add_conditional_edges(
        AgentID.AGENTE_11_UI_UX.value,
        route_after_ui_ux,
    )

    # 6. Dev to QA
    builder.add_edge(AgentID.AGENTE_03_LARAVEL.value, AgentID.AGENTE_05_QA_PHP.value)
    builder.add_edge(AgentID.AGENTE_04_FASTAPI.value, AgentID.AGENTE_06_QA_PYTHON.value)

    # 7. QA conditional feedback loops
    builder.add_conditional_edges(AgentID.AGENTE_05_QA_PHP.value, route_after_qa_php)
    builder.add_conditional_edges(AgentID.AGENTE_06_QA_PYTHON.value, route_after_qa_python)

    # 8. Synchronization Barrier
    builder.add_conditional_edges(AgentID.QA_SYNC_BARRIER.value, route_after_sync_barrier)

    # 9. DevOps to CISO
    builder.add_edge(AgentID.AGENTE_07_DEVOPS.value, AgentID.AGENTE_10_CISO.value)

    # 10. CISO conditional multi-directional routing
    builder.add_conditional_edges(AgentID.AGENTE_10_CISO.value, route_after_ciso)

    # 11. Terminal sequence: Docs -> Marketing -> Sales Analytics -> CEO Signoff -> END
    builder.add_edge(AgentID.AGENTE_08_DOCS.value, AgentID.AGENTE_12_MARKETING.value)
    builder.add_edge(AgentID.AGENTE_12_MARKETING.value, AgentID.AGENTE_13_SALES_ANALYTICS.value)
    builder.add_edge(AgentID.AGENTE_13_SALES_ANALYTICS.value, NODE_CEO_SIGNOFF)
    builder.add_edge(NODE_CEO_SIGNOFF, END)

    return builder.compile(checkpointer=checkpointer)
