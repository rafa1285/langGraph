"""State definition and reducer functions for the LangGraph software factory."""

from typing import Annotated, NotRequired, TypedDict

from app.schemas.routing import AgentID, DeliverableStatus, StepExecutionRecord


def merge_retry_counts(
    current: dict[str, int],
    update: dict[str, int],
) -> dict[str, int]:
    """Pure reducer that merges retry count dictionaries with updated keys."""
    merged = dict(current)
    merged.update(update)
    return merged


def append_execution_records(
    current: list[StepExecutionRecord],
    update: list[StepExecutionRecord],
) -> list[StepExecutionRecord]:
    """Pure reducer that concatenates audit records in chronological order."""
    return list(current) + list(update)


class SoftwareFactoryState(TypedDict):
    """Global typed state shared across all agents in the pipeline."""

    project_id: str
    idea_inicial: str
    pre_sdd_doc: str
    sdd_arquitectura: str
    requiere_php: bool
    requiere_python: bool
    codigo_php: str
    codigo_python: str
    reporte_qa_php: str
    reporte_qa_python: str
    infraestructura_docker: str
    dictamen_ciso: str
    documentacion_rag: str
    estrategia_growth: str
    status_qa_php: DeliverableStatus
    status_qa_python: DeliverableStatus
    status_ciso: DeliverableStatus
    ciso_culprit: AgentID | None
    current_status: NotRequired[DeliverableStatus]
    halt_reason: str | None
    retry_counts: Annotated[dict[str, int], merge_retry_counts]
    execution_history: Annotated[list[StepExecutionRecord], append_execution_records]


def create_initial_state(
    project_id: str,
    idea_inicial: str,
    requiere_php: bool = True,
    requiere_python: bool = True,
) -> SoftwareFactoryState:
    """Create and return a freshly initialized SoftwareFactoryState."""
    return {
        "project_id": project_id,
        "idea_inicial": idea_inicial,
        "pre_sdd_doc": "",
        "sdd_arquitectura": "",
        "requiere_php": requiere_php,
        "requiere_python": requiere_python,
        "codigo_php": "",
        "codigo_python": "",
        "reporte_qa_php": "",
        "reporte_qa_python": "",
        "infraestructura_docker": "",
        "dictamen_ciso": "",
        "documentacion_rag": "",
        "estrategia_growth": "",
        "status_qa_php": DeliverableStatus.PENDIENTE,
        "status_qa_python": DeliverableStatus.PENDIENTE,
        "status_ciso": DeliverableStatus.PENDIENTE,
        "ciso_culprit": None,
        "current_status": DeliverableStatus.PENDIENTE,
        "halt_reason": None,
        "retry_counts": {
            "qa_php": 0,
            "qa_python": 0,
            "ciso": 0,
        },
        "execution_history": [],
    }
