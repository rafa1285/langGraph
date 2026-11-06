"""Office UI API routes — agent status and office event endpoints (Phase 2 stub)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from app.schemas.brownfield import (
    AuditReport,
    BrownfieldApproveRequest,
    BrownfieldAuditRequest,
)
from app.schemas.chat import (
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
)
from app.schemas.file_edit import (
    FileEditConfirmResponse,
    FileEditProposal,
    FileEditRejectResponse,
    FileEditRequest,
    ProjectFileContent,
    ProjectFileInfo,
)
from app.schemas.routing import AgentID
from app.services.brownfield_service import BrownfieldService
from app.services.chat_service import ChatService
from app.services.file_edit_service import FileEditService
from app.services.orchestrator_service import OrchestratorService

router = APIRouter(prefix="/api/v1/office", tags=["Office UI"])


class AgentVisualStatus(BaseModel):
    """Visual state of an agent displayed in the 2D office map."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    room: str
    icon: str
    status: str  # idle | working | reviewing | blocked | done
    current_project_id: str
    last_activity: str
    message: str


# Static agent display configuration: (AgentID, display_name, room_id, icon)
_AGENT_CONFIG: list[tuple[AgentID, str, str, str]] = [
    (AgentID.AGENTE_00_CEO, "CEO", "ceo", "👑"),
    (AgentID.AGENTE_01_PM, "PM", "dev", "📋"),
    (AgentID.AGENTE_02_ARCHITECT, "Arquitecto", "dev", "🏛"),
    (AgentID.AGENTE_03_LARAVEL, "Dev Laravel", "dev", "🐘"),
    (AgentID.AGENTE_04_FASTAPI, "Dev FastAPI", "dev", "⚡"),
    (AgentID.AGENTE_05_QA_PHP, "QA PHP", "qa", "🔬"),
    (AgentID.AGENTE_06_QA_PYTHON, "QA Python", "qa", "🐍"),
    (AgentID.AGENTE_07_DEVOPS, "DevOps", "dev", "⚙"),
    (AgentID.AGENTE_08_DOCS, "Docs & RAG", "strategy", "📚"),
    (AgentID.AGENTE_09_GROWTH, "Growth", "strategy", "📈"),
    (AgentID.AGENTE_10_CISO, "CISO", "ciso", "🛡"),
    (AgentID.AGENTE_11_UI_UX, "UI/UX", "uiux", "🎨"),
    (AgentID.AGENTE_12_MARKETING, "Marketing", "marketing", "📣"),
    (AgentID.AGENTE_13_SALES_ANALYTICS, "Sales BI", "marketing", "💹"),
    (AgentID.AGENTE_14_QA_UI_UX, "QA UI/UX", "qa", "🎯"),
]


@router.get(
    "/agents/status",
    response_model=list[AgentVisualStatus],
    summary="Estado visual de todos los agentes de la oficina",
)
async def get_agents_status() -> list[AgentVisualStatus]:
    """Return current visual state for all office agents.

    Phase 1: Returns idle state for all agents.
    Phase 2: Will integrate with AgentStatusService for live states.
    """
    now = datetime.now(UTC).isoformat()
    return [
        AgentVisualStatus(
            agent_id=agent_id.value,
            name=name,
            room=room,
            icon=icon,
            status="idle",
            current_project_id="",
            last_activity=now,
            message="En espera de instrucciones.",
        )
        for agent_id, name, room, icon in _AGENT_CONFIG
    ]


def _get_chat_service(request: Request) -> ChatService:
    """Dependency: build ChatService from application state orchestrator."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if not isinstance(orchestrator, OrchestratorService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio orquestador no inicializado.",
        )
    return ChatService(
        llm_gateway=orchestrator.llm_gateway,
        prompt_loader=orchestrator.prompt_loader,
        office_store=orchestrator.office_store,
    )


def _resolve_agent_id(agent_id: str) -> AgentID:
    """Resolve path param string to valid AgentID, raising 404 if invalid."""
    try:
        resolved = AgentID(agent_id)
        if resolved in (AgentID.QA_SYNC_BARRIER, AgentID.END_PIPELINE):
            raise ValueError("Pseudo-node not allowed for chat.")
        return resolved
    except ValueError:
        valid_ids = [
            a.value
            for a in AgentID
            if a not in (AgentID.QA_SYNC_BARRIER, AgentID.END_PIPELINE)
        ]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agente desconocido: '{agent_id}'. IDs válidos: {valid_ids}",
        ) from None


@router.post(
    "/chat/{agent_id}",
    response_model=ChatMessageResponse,
    summary="Enviar mensaje a un agente en modo chat directo",
)
async def chat_with_agent(
    agent_id: str,
    body: ChatMessageRequest,
    request: Request,
) -> ChatMessageResponse:
    """Send a message to an agent and get a response with conversation history maintained."""
    resolved_agent = _resolve_agent_id(agent_id)
    chat_svc = _get_chat_service(request)
    return await chat_svc.send_message(agent_id=resolved_agent, request=body)


@router.get(
    "/chat/{agent_id}/history",
    response_model=ChatHistoryResponse,
    summary="Obtener historial de chat con un agente",
)
async def get_chat_history(
    agent_id: str,
    session_id: str,
    request: Request,
) -> ChatHistoryResponse:
    """Retrieve conversation history for a specific session and agent."""
    resolved_agent = _resolve_agent_id(agent_id)
    chat_svc = _get_chat_service(request)
    return await chat_svc.get_history(agent_id=resolved_agent, session_id=session_id)


def _get_file_edit_service(request: Request) -> FileEditService:
    """Dependency: retrieve or instantiate singleton FileEditService in app state."""
    svc = getattr(request.app.state, "file_edit_service", None)
    if isinstance(svc, FileEditService):
        return svc
    orchestrator = getattr(request.app.state, "orchestrator", None)
    llm = orchestrator.llm_gateway if orchestrator else None
    prompt_loader = orchestrator.prompt_loader if orchestrator else None
    store = orchestrator.office_store if orchestrator else None
    new_svc = FileEditService(
        llm_gateway=llm,
        prompt_loader=prompt_loader,
        office_store=store,
    )
    request.app.state.file_edit_service = new_svc
    return new_svc


@router.get(
    "/files",
    response_model=list[ProjectFileInfo],
    summary="Listar archivos del workspace de un proyecto",
)
async def list_project_files(
    request: Request,
    project_id: str = Query(..., description="ID del proyecto"),
) -> list[ProjectFileInfo]:
    """Retrieve list of files in the project workspace."""
    edit_svc = _get_file_edit_service(request)
    return await edit_svc.list_workspace_files(project_id)


@router.get(
    "/files/content",
    response_model=ProjectFileContent,
    summary="Obtener contenido de un archivo del proyecto",
)
async def get_project_file_content(
    request: Request,
    project_id: str = Query(..., description="ID del proyecto"),
    file_path: str = Query(..., description="Ruta relativa del archivo"),
) -> ProjectFileContent:
    """Read full text content of a file within the project workspace."""
    edit_svc = _get_file_edit_service(request)
    try:
        return await edit_svc.read_file_content(project_id, file_path)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from None
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from None


@router.post(
    "/chat/{agent_id}/file-edit",
    response_model=FileEditProposal,
    summary="Solicitar propuesta de modificación de archivo a un agente",
)
async def propose_file_edit(
    agent_id: str,
    body: FileEditRequest,
    request: Request,
) -> FileEditProposal:
    """Ask an agent to propose modifications to a workspace file, generating a unified diff."""
    resolved_agent = _resolve_agent_id(agent_id)
    edit_svc = _get_file_edit_service(request)
    try:
        return await edit_svc.propose_file_edit(agent_id=resolved_agent, request=body)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from None


@router.post(
    "/chat/file-edit/{edit_token}/confirm",
    response_model=FileEditConfirmResponse,
    summary="Confirmar y aplicar propuesta de edición en disco",
)
async def confirm_file_edit(
    edit_token: str,
    request: Request,
) -> FileEditConfirmResponse:
    """Apply a previously proposed file edit, writing changes and creating a backup."""
    edit_svc = _get_file_edit_service(request)
    try:
        return await edit_svc.apply_file_edit(edit_token)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from None


@router.post(
    "/chat/file-edit/{edit_token}/reject",
    response_model=FileEditRejectResponse,
    summary="Descartar propuesta de edición de archivo",
)
async def reject_file_edit(
    edit_token: str,
    request: Request,
) -> FileEditRejectResponse:
    """Discard a pending file edit proposal."""
    edit_svc = _get_file_edit_service(request)
    return await edit_svc.reject_file_edit(edit_token)


def _get_brownfield_service(request: Request) -> BrownfieldService:
    """Dependency: retrieve or instantiate singleton BrownfieldService in app state."""
    svc = getattr(request.app.state, "brownfield_service", None)
    if isinstance(svc, BrownfieldService):
        return svc
    orchestrator = getattr(request.app.state, "orchestrator", None)
    llm = orchestrator.llm_gateway if orchestrator else None
    prompt_loader = orchestrator.prompt_loader if orchestrator else None
    store = orchestrator.office_store if orchestrator else None
    new_svc = BrownfieldService(
        llm_gateway=llm,
        prompt_loader=prompt_loader,
        office_store=store,
        orchestrator=orchestrator,
    )
    request.app.state.brownfield_service = new_svc
    return new_svc


@router.post(
    "/brownfield/audit",
    response_model=AuditReport,
    summary="Iniciar auditoría diagnóstica de repositorio GitHub",
)
async def start_brownfield_audit(
    body: BrownfieldAuditRequest,
    request: Request,
) -> AuditReport:
    """Run read-only security (CISO) and architecture audit on a GitHub repository."""
    bf_svc = _get_brownfield_service(request)
    try:
        return await bf_svc.start_audit(body)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from None


@router.get(
    "/brownfield/{project_id}/audit",
    response_model=AuditReport,
    summary="Consultar informe de auditoría Brownfield",
)
async def get_brownfield_audit(
    project_id: str,
    request: Request,
) -> AuditReport:
    """Retrieve an existing audit report by project ID."""
    bf_svc = _get_brownfield_service(request)
    report = await bf_svc.get_audit_report(project_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Informe de auditoría para '{project_id}' no encontrado.",
        )
    return report


@router.post(
    "/brownfield/{project_id}/approve",
    summary="Aprobar auditoría y lanzar refactorización de software",
)
async def approve_brownfield_audit(
    project_id: str,
    body: BrownfieldApproveRequest,
    request: Request,
) -> dict[str, str]:
    """Approve audit report recommendations and launch the factory refactoring pipeline."""
    bf_svc = _get_brownfield_service(request)
    try:
        pid = await bf_svc.approve_and_start_refactor(project_id, body)
        return {
            "project_id": pid,
            "status": "approved",
            "message": "Auditoría aprobada. Pipeline de refactorización iniciado.",
        }
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from None
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from None


@router.post(
    "/brownfield/{project_id}/reject",
    summary="Rechazar informe de auditoría Brownfield",
)
async def reject_brownfield_audit(
    project_id: str,
    request: Request,
) -> dict[str, str]:
    """Reject audit report recommendations without launching any code changes."""
    bf_svc = _get_brownfield_service(request)
    try:
        await bf_svc.reject_audit(project_id)
        return {
            "project_id": project_id,
            "status": "rejected",
            "message": "Informe de auditoría rechazado.",
        }
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from None
