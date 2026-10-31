"""FastAPI REST routes for project orchestration and deliverable inspection."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.schemas.api import (
    CreateProjectRequest,
    CreateProjectResponse,
    ProjectDeliverablesResponse,
    ProjectStatusResponse,
)
from app.schemas.routing import DeliverableStatus
from app.services.orchestrator_service import OrchestratorService

router = APIRouter()


def get_orchestrator(request: Request) -> OrchestratorService:
    """Retrieve initialized OrchestratorService from application state."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if not isinstance(orchestrator, OrchestratorService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio orquestador no inicializado.",
        )
    return orchestrator


OrchestratorDep = Annotated[OrchestratorService, Depends(get_orchestrator)]


@router.get("/health", tags=["Monitoring"])
async def health_check() -> dict[str, str]:
    """Health check endpoint confirming application readiness."""
    return {"status": "ok"}


@router.post(
    "/api/v1/projects",
    response_model=CreateProjectResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Projects"],
)
async def create_project(
    payload: CreateProjectRequest,
    orchestrator: OrchestratorDep,
) -> CreateProjectResponse:
    """Create a project and trigger asynchronous background execution."""
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    await orchestrator.start_project(
        idea_inicial=payload.idea_inicial,
        project_id=project_id,
    )
    return CreateProjectResponse(project_id=project_id, status="RUNNING")


@router.get(
    "/api/v1/projects/{project_id}/status",
    response_model=ProjectStatusResponse,
    tags=["Projects"],
)
async def get_project_status(
    project_id: str,
    orchestrator: OrchestratorDep,
) -> ProjectStatusResponse:
    """Retrieve operational status, active agents, and audit logs of a project."""
    state = await orchestrator.get_project_state(project_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto {project_id} no encontrado.",
        )

    history = state.get("execution_history", [])
    ultimo_agente = history[-1].agent_id.value if history else None

    return ProjectStatusResponse(
        project_id=project_id,
        ultimo_agente=ultimo_agente,
        status_qa_php=state.get("status_qa_php", DeliverableStatus.PENDIENTE),
        status_qa_python=state.get("status_qa_python", DeliverableStatus.PENDIENTE),
        status_ciso=state.get("status_ciso", DeliverableStatus.PENDIENTE),
        retry_counts=state.get("retry_counts", {}),
        pasos_completados=len(history),
        execution_history=history,
    )


@router.get(
    "/api/v1/projects/{project_id}/deliverables",
    response_model=ProjectDeliverablesResponse,
    tags=["Projects"],
)
async def get_project_deliverables(
    project_id: str,
    orchestrator: OrchestratorDep,
) -> ProjectDeliverablesResponse:
    """Retrieve all structured Markdown deliverables produced for a project."""
    state = await orchestrator.get_project_state(project_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto {project_id} no encontrado.",
        )

    return ProjectDeliverablesResponse(
        project_id=project_id,
        pre_sdd_doc=state.get("pre_sdd_doc", ""),
        sdd_arquitectura=state.get("sdd_arquitectura", ""),
        codigo_php=state.get("codigo_php", ""),
        codigo_python=state.get("codigo_python", ""),
        reporte_qa_php=state.get("reporte_qa_php", ""),
        reporte_qa_python=state.get("reporte_qa_python", ""),
        infraestructura_docker=state.get("infraestructura_docker", ""),
        dictamen_ciso=state.get("dictamen_ciso", ""),
        documentacion_rag=state.get("documentacion_rag", ""),
        estrategia_growth=state.get("estrategia_growth", ""),
    )


@router.post(
    "/api/v1/projects/{project_id}/resume",
    response_model=CreateProjectResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Projects"],
)
async def resume_project_endpoint(
    project_id: str,
    orchestrator: OrchestratorDep,
) -> CreateProjectResponse:
    """Resume execution of an interrupted or halted project from its last checkpoint."""
    state = await orchestrator.get_project_state(project_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto {project_id} no encontrado para reanudar.",
        )

    # Launch resumption asynchronously
    import asyncio
    asyncio.create_task(orchestrator.resume_project(project_id))

    return CreateProjectResponse(project_id=project_id, status="RESUMED")
