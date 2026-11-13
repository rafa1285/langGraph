"""FastAPI REST routes for project orchestration and deliverable inspection."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from app.core.config import settings
from app.schemas.api import (
    CreateProjectRequest,
    CreateProjectResponse,
    DeployVercelRequest,
    DeployVercelResponse,
    MaterializeResponse,
    ProjectDeliverablesResponse,
    ProjectsListResponse,
    ProjectStatusResponse,
    ProjectSummaryResponse,
    SendEmailRequest,
)
from app.schemas.office import (
    AgentConversationRecord,
    AgentEmailRecord,
    EmailPriority,
)
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.code_materializer import CodeMaterializerService
from app.services.event_bus import event_bus
from app.services.local_deployer import LocalSandboxDeployer
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.orchestrator_service import OrchestratorService
from app.services.vercel_deployer import VercelDeployerService

logger = logging.getLogger(__name__)

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


@router.get(
    "/api/v1/projects",
    response_model=ProjectsListResponse,
    tags=["Projects"],
)
async def list_projects(
    orchestrator: OrchestratorDep,
) -> ProjectsListResponse:
    """List all factory projects with aggregated status, step counts, and telemetry."""
    office_store = OfficeStore()
    db_summaries = await office_store.get_all_projects_summary()

    all_project_ids = set(db_summaries.keys())
    # Only include workspaces that are visible in database
    workspaces_dir = Path(settings.WORKSPACES_DIR)
    if workspaces_dir.exists() and workspaces_dir.is_dir():
        for item in workspaces_dir.iterdir():
            if item.is_dir() and not item.name.startswith(".") and item.name in db_summaries:
                all_project_ids.add(item.name)

    projects_list: list[ProjectSummaryResponse] = []
    for pid in sorted(all_project_ids):
        summary_data = db_summaries.get(pid)
        pname = summary_data.get("project_name") if summary_data else None
        if not pname and pid == "proj_88c9fd46":
            pname = "validator-hq-saas"

        if summary_data:
            projects_list.append(
                ProjectSummaryResponse(
                    project_id=pid,
                    current_status=summary_data["current_status"],
                    steps_completed=summary_data["steps_completed"],
                    total_tokens_in=summary_data["total_tokens_in"],
                    total_tokens_out=summary_data["total_tokens_out"],
                    total_duration_ms=summary_data["total_duration_ms"],
                    updated_at=summary_data["updated_at"] or datetime.now(UTC).isoformat(),
                    project_name=pname,
                )
            )
        else:
            state = await orchestrator.get_project_state(pid)
            if state is not None:
                history = state.get("execution_history", [])
                projects_list.append(
                    ProjectSummaryResponse(
                        project_id=pid,
                        current_status=state.get("status_ciso", DeliverableStatus.PENDIENTE).value,
                        steps_completed=len(history),
                        total_tokens_in=0,
                        total_tokens_out=0,
                        total_duration_ms=0,
                        updated_at=datetime.now(UTC).isoformat(),
                        project_name=pname,
                    )
                )
            else:
                projects_list.append(
                    ProjectSummaryResponse(
                        project_id=pid,
                        current_status="INITIALIZING",
                        steps_completed=0,
                        total_tokens_in=0,
                        total_tokens_out=0,
                        total_duration_ms=0,
                        updated_at=datetime.now(UTC).isoformat(),
                        project_name=pname,
                    )
                )

    return ProjectsListResponse(total=len(projects_list), projects=projects_list)


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
        ceo_charter=state.get("ceo_charter", ""),
        ui_ux_spec=state.get("ui_ux_spec", ""),
        marketing_spec=state.get("marketing_spec", ""),
        sales_analytics_spec=state.get("sales_analytics_spec", ""),
        ceo_signoff=state.get("ceo_signoff", ""),
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

    asyncio.create_task(orchestrator.resume_project(project_id))

    return CreateProjectResponse(project_id=project_id, status="RESUMED")


@router.get(
    "/api/v1/projects/{project_id}/conversations",
    response_model=list[AgentConversationRecord],
    tags=["Projects"],
)
async def get_project_conversations(
    project_id: str,
    agent_id: Annotated[AgentID | None, Query(description="Filtrar por agente específico")] = None,
) -> list[AgentConversationRecord]:
    """Retrieve full conversation and LLM prompt turns for a project."""
    office_store = OfficeStore()
    conversations = await office_store.get_conversations(project_id, agent_id=agent_id)
    workspaces_dir = Path(settings.WORKSPACES_DIR) / project_id
    if not conversations and not workspaces_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto {project_id} no encontrado.",
        )
    return conversations


@router.get(
    "/api/v1/projects/{project_id}/inbox",
    response_model=list[AgentEmailRecord],
    tags=["Office Mail"],
)
async def get_project_inbox(
    project_id: str,
    recipient: Annotated[str | None, Query(description="Filtrar por destinatario")] = None,
    sender: Annotated[str | None, Query(description="Filtrar por remitente")] = None,
    priority: Annotated[EmailPriority | None, Query(description="Filtrar por prioridad")] = None,
    unread_only: Annotated[bool, Query(description="Solo correos no leídos")] = False,
) -> list[AgentEmailRecord]:
    """Retrieve internal office emails exchanged between agents or from CEO."""
    office_store = OfficeStore()
    emails = await office_store.get_emails(
        project_id=project_id,
        recipient=recipient,
        sender=sender,
        priority=priority,
        unread_only=unread_only,
    )
    workspaces_dir = Path(settings.WORKSPACES_DIR) / project_id
    if not emails and not workspaces_dir.exists():
        convs = await office_store.get_conversations(project_id)
        if not convs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Proyecto {project_id} no encontrado.",
            )
    return emails


@router.post(
    "/api/v1/projects/{project_id}/email",
    response_model=AgentEmailRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["Office Mail"],
)
async def send_ceo_email(
    project_id: str,
    payload: SendEmailRequest,
) -> AgentEmailRecord:
    """Send direct directive email from CEO (ceo@agentoffice.local) to an agent."""
    norm_recipient = payload.recipient.strip()
    if "@" not in norm_recipient:
        norm_recipient = f"{norm_recipient}@agentoffice.local"

    office_store = OfficeStore()
    mail_service = MailService(office_store)
    email_record = await mail_service.send_email(
        project_id=project_id,
        sender="ceo@agentoffice.local",
        recipient=norm_recipient,
        subject=payload.subject,
        body_summary=payload.body,
        priority=payload.priority,
    )

    await event_bus.broadcast(
        project_id=project_id,
        event_type="EMAIL_SENT",
        data=email_record.model_dump(mode="json"),
    )

    return email_record


@router.post(
    "/api/v1/projects/{project_id}/materialize",
    response_model=MaterializeResponse,
    tags=["Projects"],
)
async def materialize_project_source(
    project_id: str,
) -> MaterializeResponse:
    """Materialize code deliverables into build/ directory and validate environment."""
    source_dir = Path(settings.WORKSPACES_DIR) / project_id
    if not source_dir.exists() or not source_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto {project_id} no encontrado en workspaces.",
        )

    materializer = CodeMaterializerService()
    build_path, manifest_data = materializer.materialize_project(project_id)

    deployer = LocalSandboxDeployer()
    env_info = deployer.prepare_local_environment(build_path)
    is_valid = await deployer.validate_compose_syntax(build_path, project_id)

    return MaterializeResponse(
        project_id=project_id,
        build_path=str(build_path),
        total_files=manifest_data.get("total_files", 0),
        manifest=manifest_data,
        compose_file=env_info.get("compose_file"),
        compose_valid=is_valid,
        scripts=env_info.get("scripts", []),
    )


@router.post(
    "/api/v1/projects/{project_id}/deploy-vercel",
    response_model=DeployVercelResponse,
    tags=["Deployments"],
)
async def deploy_project_to_vercel(
    project_id: str,
    payload: DeployVercelRequest | None = None,
) -> DeployVercelResponse:
    """Package serverless distribution bundle and deploy to Vercel Cloud."""
    source_dir = Path(settings.WORKSPACES_DIR) / project_id
    if not source_dir.exists() or not source_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proyecto {project_id} no encontrado en workspaces.",
        )

    project_name = payload.name if payload else "validator-hq-saas"
    deployer = VercelDeployerService()
    result = await deployer.deploy_to_vercel(
        project_id=project_id,
        project_name=project_name,
        sync_notifications=True,
    )

    if not result["success"]:
        status_code = (
            status.HTTP_400_BAD_REQUEST
            if "VERCEL_TOKEN" in (result["error"] or "")
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(
            status_code=status_code,
            detail=result["error"] or "Error al desplegar en Vercel.",
        )

    return DeployVercelResponse(
        success=True,
        project_id=result["project_id"],
        project_name=result["project_name"],
        deployment_url=result["deployment_url"],
        bundle_path=result["bundle_path"],
        total_files=result["total_files"],
        email_logged=result["email_logged"],
        error=None,
    )


@router.websocket("/ws/projects/{project_id}")
async def project_events_websocket(
    websocket: WebSocket,
    project_id: str,
) -> None:
    """WebSocket event stream broadcasting real-time execution steps and agent communications."""
    await event_bus.connect(project_id, websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        await event_bus.disconnect(project_id, websocket)
    except Exception as exc:
        logger.warning("Error en WebSocket del proyecto %s: %s", project_id, exc)
        await event_bus.disconnect(project_id, websocket)
