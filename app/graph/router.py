"""Conditional routing functions for LangGraph Software Factory workflow."""

from langgraph.graph import END

from app.core.config import settings
from app.graph.state import SoftwareFactoryState
from app.schemas.routing import AgentID, DeliverableStatus


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
            for member in AgentID:
                if member.value == val:
                    return member.value
        return END

    return END
