"""Conditional routing functions for LangGraph Software Factory workflow."""

from langgraph.graph import END

from app.core.config import settings
from app.graph.state import SoftwareFactoryState
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.office_store import OfficeStore

NODE_CEO_SIGNOFF = "agente_00_ceo_signoff"


def _get_office_store(state: SoftwareFactoryState) -> OfficeStore:
    """Helper to instantiate OfficeStore using isolated DB path from state if present."""
    db_path = state.get("_office_db_path")
    if db_path:
        return OfficeStore(db_path=db_path)
    return OfficeStore()


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


def route_after_ui_ux(state: SoftwareFactoryState) -> list[str]:
    """Fan-out to Laravel and/or FastAPI development nodes following UI/UX design."""
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

    history = state.get("execution_history", [])
    if state.get("retry_counts", {}).get("ciso", 0) >= settings.MAX_RETRIES_PER_GATE:
        # If extensive refactoring has occurred (>= 16 steps), route to Docs to conclude
        if len(history) >= 16:
            print(
                "\n[CISO Router] Aviso: Avance forzado hacia Agente 08 (Docs) tras agotamiento "
                f"de iteraciones de auditoría CISO ({settings.MAX_RETRIES_PER_GATE} reintentos) "
                f"con {len(history)} pasos completados en historial."
            )
            return AgentID.AGENTE_08_DOCS.value
        return END

    if state.get("status_ciso") == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD:
        culprit = state.get("ciso_culprit")
        if culprit == AgentID.AGENTE_03_LARAVEL:
            return AgentID.AGENTE_03_LARAVEL.value
        if culprit == AgentID.AGENTE_04_FASTAPI:
            return AgentID.AGENTE_04_FASTAPI.value
        return AgentID.AGENTE_07_DEVOPS.value

    return AgentID.AGENTE_08_DOCS.value


def route_after_docs(state: SoftwareFactoryState) -> str:
    """Route after Agent 08 (Docs & RAG) based on real-time marketing configuration in SQLite."""
    project_id = state.get("project_id", "")
    office_store = _get_office_store(state)
    config = office_store.get_project_marketing_config_sync(project_id)

    if not config.marketing_enabled:
        return NODE_CEO_SIGNOFF

    if config.include_growth_agent:
        return AgentID.AGENTE_09_GROWTH.value

    return AgentID.AGENTE_12_MARKETING.value


def route_after_growth(state: SoftwareFactoryState) -> str:
    """Route after Agent 09 (Growth) to Marketing or skip directly to CEO Signoff."""
    project_id = state.get("project_id", "")
    office_store = _get_office_store(state)
    config = office_store.get_project_marketing_config_sync(project_id)

    if not config.marketing_enabled:
        return NODE_CEO_SIGNOFF

    return AgentID.AGENTE_12_MARKETING.value


def route_after_marketing(state: SoftwareFactoryState) -> str:
    """Route after Agent 12 (Marketing) to Sales Analytics or skip directly to CEO Signoff."""
    project_id = state.get("project_id", "")
    office_store = _get_office_store(state)
    config = office_store.get_project_marketing_config_sync(project_id)

    if not config.marketing_enabled:
        return NODE_CEO_SIGNOFF

    if config.include_sales_analytics_agent:
        return AgentID.AGENTE_13_SALES_ANALYTICS.value

    return NODE_CEO_SIGNOFF


def route_after_sales_analytics(state: SoftwareFactoryState) -> str:
    """Route after Agent 13 (Sales Analytics) to CEO Signoff."""
    return NODE_CEO_SIGNOFF


def route_after_docs_legacy(state: SoftwareFactoryState) -> str:
    """Route after Agent 08 in legacy 10-agent pipeline based on marketing config."""
    project_id = state.get("project_id", "")
    office_store = _get_office_store(state)
    config = office_store.get_project_marketing_config_sync(project_id)

    if not config.marketing_enabled or not config.include_growth_agent:
        return END

    return AgentID.AGENTE_09_GROWTH.value


def route_after_ceo_signoff(state: SoftwareFactoryState) -> str:
    """Route CEO signoff: END on approval or iteration limit (>=3), else loop back to culprit."""
    if state.get("ceo_approved", False):
        return END

    version = state.get("version_iteracion", 1)
    if version >= 3:
        return END

    if (
        state.get("ceo_blocked")
        or state.get("status_ceo") == DeliverableStatus.LANZAMIENTO_BLOQUEADO_REWORK
    ):
        culprit = state.get("ceo_culprit")
        if culprit:
            val = culprit.value if isinstance(culprit, AgentID) else str(culprit)
            # Verify if marketing agent rework is allowed under current project configuration
            marketing_agents = (
                AgentID.AGENTE_09_GROWTH.value,
                AgentID.AGENTE_12_MARKETING.value,
                AgentID.AGENTE_13_SALES_ANALYTICS.value,
            )
            if val in marketing_agents:
                office_store = _get_office_store(state)
                config = office_store.get_project_marketing_config_sync(
                    state.get("project_id", "")
                )
                if not config.marketing_enabled:
                    return END
                if val == AgentID.AGENTE_09_GROWTH.value and not config.include_growth_agent:
                    return END
                if (
                    val == AgentID.AGENTE_13_SALES_ANALYTICS.value
                    and not config.include_sales_analytics_agent
                ):
                    return END

            for member in AgentID:
                if member.value == val:
                    return member.value
        return END

    return END
