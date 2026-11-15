"""Office UI API routes — agent status and office event endpoints (Phase 2 stub)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict

from app.schemas.api import CreateProjectRequest, CreateProjectResponse
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
from app.schemas.office import (
    AgentLLMChainPingResponse,
    AgentLLMConfig,
    AgentLLMConfigUpdate,
    LLMModelCatalogCreate,
    LLMModelCatalogItem,
    LLMModelCatalogUpdate,
    LLMModelPingResponse,
    MarketingExecuteRequest,
    MarketingExecuteResponse,
    MarketingPresetsResponse,
    MarketingToolTestResponse,
    N8NProvisionRequest,
    N8NProvisionResponse,
    ProjectMarketingProfile,
)
from app.schemas.routing import AgentID
from app.services.brownfield_service import BrownfieldService
from app.services.chat_service import ChatService
from app.services.file_edit_service import FileEditService
from app.services.llm_gateway import GeminiLLMGateway, LLMGatewayProtocol
from app.services.office_store import OfficeStore, normalize_agent_id
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


# ── Dynamic LLM Catalog, Routing & Diagnostics (PASO 3) ────────────────────

def _get_office_store(request: Request) -> OfficeStore:
    """Dependency: retrieve active OfficeStore from application state."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator and hasattr(orchestrator, "office_store"):
        return orchestrator.office_store
    return OfficeStore()


def _get_llm_gateway(request: Request) -> LLMGatewayProtocol:
    """Dependency: retrieve active LLMGateway from application state."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator and hasattr(orchestrator, "llm_gateway"):
        return orchestrator.llm_gateway
    return GeminiLLMGateway(store=_get_office_store(request))


llm_router = APIRouter()


@llm_router.get(
    "/llm/catalog",
    response_model=list[LLMModelCatalogItem],
    summary="Listar catálogo completo de modelos LLM con estado de credenciales",
)
async def list_llm_catalog(request: Request) -> list[LLMModelCatalogItem]:
    """Return all catalog models enriched with credential status (has_api_key)."""
    store = _get_office_store(request)
    return await store.get_llm_catalog()


@llm_router.post(
    "/llm/catalog",
    response_model=LLMModelCatalogItem,
    status_code=status.HTTP_201_CREATED,
    summary="Añadir nuevo modelo LLM al catálogo global",
)
async def create_llm_model(
    body: LLMModelCatalogCreate,
    request: Request,
) -> LLMModelCatalogItem:
    """Register a new LLM model in the catalog."""
    store = _get_office_store(request)
    existing = await store.get_llm_model(body.model_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El modelo '{body.model_id}' ya existe en el catálogo.",
        )
    return await store.create_llm_model(body)


@llm_router.put(
    "/llm/catalog/{model_id:path}",
    response_model=LLMModelCatalogItem,
    summary="Actualizar modelo LLM del catálogo",
)
async def update_llm_model(
    model_id: str,
    body: LLMModelCatalogUpdate,
    request: Request,
) -> LLMModelCatalogItem:
    """Modify parameters or status for an existing catalog model."""
    store = _get_office_store(request)
    updated = await store.update_llm_model(model_id, body)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Modelo '{model_id}' no encontrado en el catálogo.",
        )
    return updated


@llm_router.delete(
    "/llm/catalog/{model_id:path}",
    summary="Eliminar modelo LLM del catálogo",
)
async def delete_llm_model(
    model_id: str,
    request: Request,
) -> dict[str, str]:
    """Remove a model from the catalog."""
    store = _get_office_store(request)
    deleted = await store.delete_llm_model(model_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Modelo '{model_id}' no encontrado en el catálogo.",
        )
    return {"status": "deleted", "model_id": model_id}


@llm_router.get(
    "/agents/{agent_id}/llm-config",
    response_model=AgentLLMConfig,
    summary="Obtener configuración y cadena de fallback del agente",
)
async def get_agent_llm_config(
    agent_id: str,
    request: Request,
) -> AgentLLMConfig:
    """Retrieve dynamic LLM chain, temperature, timeout and max_retries for an agent."""
    norm_id = normalize_agent_id(agent_id)
    store = _get_office_store(request)
    return await store.get_agent_llm_config(norm_id)


@llm_router.put(
    "/agents/{agent_id}/llm-config",
    response_model=AgentLLMConfig,
    summary="Guardar en caliente la configuración de modelos del agente",
)
async def update_agent_llm_config(
    agent_id: str,
    body: AgentLLMConfigUpdate,
    request: Request,
) -> AgentLLMConfig:
    """Persist updated fallback priorities, enabled switches, and agent parameters."""
    norm_id = normalize_agent_id(agent_id)
    store = _get_office_store(request)
    return await store.save_agent_llm_config(norm_id, body)


@llm_router.post(
    "/agents/{agent_id}/llm-config/reset",
    response_model=AgentLLMConfig,
    summary="Restaurar configuración de modelos por defecto del agente",
)
async def reset_agent_llm_config(
    agent_id: str,
    request: Request,
) -> AgentLLMConfig:
    """Restore recommended factory defaults for an agent's LLM chain."""
    norm_id = normalize_agent_id(agent_id)
    store = _get_office_store(request)
    return await store.reset_agent_llm_config(norm_id)


@llm_router.post(
    "/llm/ping/{model_id:path}",
    response_model=LLMModelPingResponse,
    summary="Test Ping individual de un modelo LLM",
)
async def ping_model(
    model_id: str,
    request: Request,
) -> LLMModelPingResponse:
    """Run isolated connection ping test against a model without penalizing circuit breaker."""
    store = _get_office_store(request)
    model = await store.get_llm_model(model_id)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Modelo '{model_id}' no encontrado en el catálogo.",
        )
    gateway = _get_llm_gateway(request)
    return await gateway.ping_model(model)


@llm_router.post(
    "/agents/{agent_id}/llm-ping",
    response_model=AgentLLMChainPingResponse,
    summary="Probar cadena activa completa de modelos del agente",
)
async def ping_agent_chain(
    agent_id: str,
    request: Request,
) -> AgentLLMChainPingResponse:
    """Test all active models in agent fallback chain and determine effective responding model."""
    norm_id = normalize_agent_id(agent_id)
    gateway = _get_llm_gateway(request)
    return await gateway.ping_agent_chain(norm_id)


# Marketing routes router
marketing_router = APIRouter(prefix="/marketing", tags=["Office Marketing"])


@marketing_router.get(
    "/presets",
    response_model=MarketingPresetsResponse,
    summary="Obtener catálogo de tipos de marketing y canales disponibles",
)
async def get_marketing_presets() -> MarketingPresetsResponse:
    """Devuelve los tipos de estrategia disponibles y el catálogo de canales y herramientas."""
    from app.schemas.office import MarketingChannelConfig, ProjectMarketingToolConfig
    from app.services.office_store import MARKETING_CHANNELS_CATALOG, MARKETING_TOOLS_CATALOG

    types = ["none", "saas_b2b", "b2c_app_ecommerce", "devtools_api", "internal_rollout", "custom"]
    channels = [
        MarketingChannelConfig(
            channel_id=ch["channel_id"],
            name=ch["name"],
            enabled=False,
            account_handle_or_url=ch.get("account_handle_or_url", ""),
            credentials=dict(ch.get("credentials", {})),
            custom_instructions=ch.get("custom_instructions", ""),
        )
        for ch in MARKETING_CHANNELS_CATALOG
    ]
    tools = [
        ProjectMarketingToolConfig(
            tool_id=t["tool_id"],
            name=t["name"],
            description=t["description"],
            enabled=False,
            credentials=dict(t.get("credentials", {})),
            settings=dict(t.get("settings", {})),
            is_configured=t.get("is_configured", True),
        )
        for t in MARKETING_TOOLS_CATALOG
    ]
    return MarketingPresetsResponse(
        available_types=types,
        channels_catalog=channels,
        tools_catalog=tools,
    )


@marketing_router.get(
    "/projects",
    response_model=list[dict[str, Any]],
    summary="Listar todos los proyectos con su estado de marketing",
)
async def list_marketing_projects(
    request: Request,
) -> list[dict[str, Any]]:
    """Listar proyectos con estado, marketing_type, canales activos y última ejecución."""
    store = _get_office_store(request)
    return await store.list_marketing_projects()


@marketing_router.get(
    "/projects/{project_id}",
    response_model=ProjectMarketingProfile,
    summary="Obtener perfil de marketing de un proyecto",
)
async def get_project_marketing_profile(
    project_id: str,
    request: Request,
) -> ProjectMarketingProfile:
    """Devuelve el ProjectMarketingProfile del proyecto."""
    store = _get_office_store(request)
    return await store.get_project_marketing_config(project_id)


@marketing_router.put(
    "/projects/{project_id}",
    response_model=ProjectMarketingProfile,
    summary="Actualizar en caliente la configuración de marketing del proyecto",
)
async def update_project_marketing_profile(
    project_id: str,
    profile: ProjectMarketingProfile,
    request: Request,
) -> ProjectMarketingProfile:
    """Actualiza en caliente el perfil de marketing, herramientas, canales y cuentas."""
    store = _get_office_store(request)
    return await store.save_project_marketing_config(project_id, profile)


@marketing_router.post(
    "/projects/{project_id}/apply-preset/{marketing_type}",
    response_model=ProjectMarketingProfile,
    summary="Aplicar preset de canales y herramientas conservando credenciales",
)
async def apply_marketing_preset(
    project_id: str,
    marketing_type: str,
    request: Request,
) -> ProjectMarketingProfile:
    """Aplica un preset de canales y herramientas al proyecto sin borrar sus API keys guardadas."""
    store = _get_office_store(request)
    return await store.apply_preset_to_project(project_id, marketing_type)


@marketing_router.post(
    "/projects/{project_id}/tools/{tool_id}/test",
    response_model=MarketingToolTestResponse,
    summary="Probar conectividad y credenciales de una herramienta de marketing",
)
async def test_marketing_tool(
    project_id: str,
    tool_id: str,
    request: Request,
) -> MarketingToolTestResponse:
    """Prueba conectividad y credenciales de una herramienta de marketing para el proyecto."""
    store = _get_office_store(request)
    return await store.test_marketing_tool(project_id, tool_id)


@marketing_router.post(
    "/projects/{project_id}/test-tool/{tool_id}",
    response_model=MarketingToolTestResponse,
    summary="Probar en vivo una herramienta de marketing con las cuentas del proyecto",
)
async def test_marketing_tool_live(
    project_id: str,
    tool_id: str,
    request: Request,
) -> MarketingToolTestResponse:
    """Prueba en vivo una herramienta con las credenciales y configuración del proyecto."""
    store = _get_office_store(request)
    return await store.test_marketing_tool(project_id, tool_id)


@marketing_router.post(
    "/projects/{project_id}/execute",
    response_model=MarketingExecuteResponse,
    summary="Ejecutar marketing bajo demanda para un proyecto",
)
async def execute_marketing_ondemand(
    project_id: str,
    request: Request,
    payload: MarketingExecuteRequest | None = None,
) -> MarketingExecuteResponse:
    """Ejecuta el ciclo de marketing bajo demanda para un proyecto en cualquier fase."""
    import json
    from pathlib import Path

    from app.core.config import settings
    from app.graph.nodes import FactoryNodes
    from app.graph.state import SoftwareFactoryState
    from app.services.llm_gateway import GeminiLLMGateway, MockLLMGateway
    from app.services.prompt_loader import PromptLoader
    from app.services.workspace_writer import WorkspaceWriter

    store = _get_office_store(request)
    profile = await store.get_project_marketing_config(project_id)

    # 1. Apply any payload updates or switch on marketing
    if payload:
        if payload.marketing_type and payload.marketing_type != profile.marketing_type:
            profile = await store.apply_preset_to_project(project_id, payload.marketing_type)
        if payload.brand_voice:
            profile.brand_voice = payload.brand_voice
        if payload.target_audience:
            profile.target_audience = payload.target_audience

    # Ensure marketing is turned ON
    profile.marketing_enabled = True
    if profile.marketing_type == "none":
        profile = await store.apply_preset_to_project(project_id, "saas_b2b")
        profile.marketing_enabled = True

    await store.save_project_marketing_config(project_id, profile)

    # 2. Inspect workspace context
    ws_dir = Path(settings.WORKSPACES_DIR) / project_id
    idea_inicial = f"Proyecto {project_id}"
    pre_sdd_doc = ""
    sdd_arquitectura = ""
    documentacion_rag = ""
    ui_ux_spec = ""
    ceo_charter = ""

    if ws_dir.exists():
        deliv_dir = ws_dir / "deliverables"
        if deliv_dir.exists():
            for f in deliv_dir.glob("*.md"):
                fname = f.name.lower()
                if "01_agente_01_pm" in fname:
                    pre_sdd_doc = f.read_text(encoding="utf-8")
                elif "02_agente_02_architect" in fname:
                    sdd_arquitectura = f.read_text(encoding="utf-8")
                elif "08_agente_08_docs" in fname:
                    documentacion_rag = f.read_text(encoding="utf-8")
                elif "11_agente_11_ui_ux" in fname:
                    ui_ux_spec = f.read_text(encoding="utf-8")
                elif "00_agente_00_ceo" in fname:
                    ceo_charter = f.read_text(encoding="utf-8")

        if not pre_sdd_doc:
            readme = ws_dir / "README.md"
            if readme.exists():
                pre_sdd_doc = readme.read_text(encoding="utf-8")

    state: SoftwareFactoryState = {
        "project_id": project_id,
        "idea_inicial": idea_inicial,
        "pre_sdd_doc": pre_sdd_doc or f"# Especificación {project_id}\nPlataforma de software.",
        "sdd_arquitectura": sdd_arquitectura or f"# SDD {project_id}\nArquitectura modular.",
        "documentacion_rag": documentacion_rag or f"# Documentación {project_id}\nGuías y API.",
        "ui_ux_spec": ui_ux_spec or f"# UI/UX {project_id}\nComponentes TailwindCSS.",
        "ceo_charter": ceo_charter or f"# CEO Charter {project_id}\nZero-Touch 100% autoservicio.",
        "version_iteracion": 1,
        "marketing_enabled": True,
        "marketing_type": profile.marketing_type,
        "_office_db_path": str(store.db_path),
        "execution_history": [],
    }

    # 3. Instantiate FactoryNodes with active store
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator and getattr(orchestrator, "nodes", None):
        nodes = orchestrator.nodes
        nodes.office_store = store
    else:
        gateway = MockLLMGateway() if settings.USE_MOCK_LLM else GeminiLLMGateway()
        loader = PromptLoader()
        writer = WorkspaceWriter(base_dir=settings.WORKSPACES_DIR)
        nodes = FactoryNodes(
            llm_gateway=gateway,
            prompt_loader=loader,
            workspace_writer=writer,
            office_store=store,
        )

    executed_nodes: list[str] = []

    # 4. Sequence execution: 09_growth -> 12_marketing -> 13_sales_analytics
    force_all = bool(payload and payload.force_all_nodes)
    if profile.include_growth_agent or force_all:
        res_09 = await nodes.node_09_growth(state)
        state["estrategia_growth"] = str(res_09.get("estrategia_growth", ""))
        executed_nodes.append("agente_09_growth")

    res_12 = await nodes.marketing_node(state)
    state["marketing_spec"] = str(res_12.get("marketing_spec", ""))
    executed_nodes.append("agente_12_marketing")

    if profile.include_sales_analytics_agent or force_all:
        res_13 = await nodes.sales_analytics_node(state)
        state["sales_analytics_spec"] = str(res_13.get("sales_analytics_spec", ""))
        executed_nodes.append("agente_13_sales_analytics")

    # 5. Collect created artifacts
    marketing_dir = ws_dir / "marketing"
    artifacts_created: list[str] = []
    actions_dispatched: list[dict[str, Any]] = []

    if marketing_dir.exists():
        for p in marketing_dir.glob("*"):
            if p.is_file():
                artifacts_created.append(p.name)

        channels_payload_file = marketing_dir / "channels_payload.json"
        if channels_payload_file.exists():
            try:
                cdata = json.loads(channels_payload_file.read_text(encoding="utf-8"))
                for hook in cdata.get("dispatched_webhooks", []):
                    actions_dispatched.append({"type": "webhook", **hook})
            except Exception:
                pass

        emails_payload_file = marketing_dir / "email_campaigns.json"
        if emails_payload_file.exists():
            try:
                edata = json.loads(emails_payload_file.read_text(encoding="utf-8"))
                actions_dispatched.append(
                    {
                        "type": "email_campaigns",
                        "provider": edata.get("email_provider"),
                        "send_mode": edata.get("send_mode"),
                        "count": len(edata.get("campaigns", [])),
                    }
                )
            except Exception:
                pass

    updated_profile = await store.get_project_marketing_config(project_id)

    return MarketingExecuteResponse(
        project_id=project_id,
        status="COMPLETED",
        marketing_type=updated_profile.marketing_type,
        executed_nodes=executed_nodes,
        artifacts_created=artifacts_created,
        actions_dispatched=actions_dispatched,
        profile=updated_profile,
        message=(
            f"Marketing ejecutado bajo demanda con éxito "
            f"({len(executed_nodes)} nodos, {len(artifacts_created)} artefactos)."
        ),
    )


@marketing_router.get(
    "/projects/{project_id}/n8n-workflow",
    response_model=dict[str, Any],
    summary="Generar y descargar workflow de n8n para el proyecto",
)
async def get_project_n8n_workflow_endpoint(
    project_id: str,
    request: Request,
) -> dict[str, Any]:
    """Genera el JSON completo de workflow para n8n adaptado a los canales activos del proyecto."""
    from app.services.n8n_service import generate_project_n8n_workflow

    store = _get_office_store(request)
    profile = await store.get_project_marketing_config(project_id)
    return generate_project_n8n_workflow(profile)


@marketing_router.post(
    "/projects/{project_id}/n8n-provision",
    response_model=N8NProvisionResponse,
    summary="Aprovisionar automáticamente el workflow en la API de n8n",
)
async def provision_project_n8n_workflow_endpoint(
    project_id: str,
    request: Request,
    payload: N8NProvisionRequest | None = None,
) -> N8NProvisionResponse:
    """Crea el workflow en la instancia de n8n vía API y auto-asigna el webhook URL resultante."""
    from app.services.n8n_service import provision_workflow_in_n8n

    store = _get_office_store(request)
    profile = await store.get_project_marketing_config(project_id)

    base_url = payload.n8n_base_url if payload and payload.n8n_base_url else ""
    api_key = payload.n8n_api_key if payload and payload.n8n_api_key else ""

    result = await provision_workflow_in_n8n(
        profile=profile,
        n8n_base_url=base_url,
        n8n_api_key=api_key,
        office_store=store,
    )
    return N8NProvisionResponse(**result)


# Mount llm_router & marketing_router under /api/v1/office
router.include_router(llm_router)
router.include_router(marketing_router)

# Mount compat router under /api/office
office_compat_router = APIRouter(prefix="/api/office", tags=["Office UI (compat)"])
office_compat_router.include_router(llm_router)
office_compat_router.include_router(marketing_router)


@office_compat_router.post(
    "/projects",
    response_model=CreateProjectResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Crear proyecto con configuración opcional de marketing",
)
async def create_office_project(
    payload: CreateProjectRequest,
    request: Request,
) -> CreateProjectResponse:
    """Crea un proyecto aceptando opcionalmente marketing_enabled y marketing_type."""
    import uuid
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if not isinstance(orchestrator, OrchestratorService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio orquestador no inicializado.",
        )
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    store = _get_office_store(request)
    if payload.marketing_enabled is not None or payload.marketing_type is not None:
        m_type = payload.marketing_type or (
            "saas_b2b" if payload.marketing_enabled is not False else "none"
        )
        profile = store.get_marketing_preset(m_type, project_id=project_id)
        if payload.marketing_enabled is not None:
            profile.marketing_enabled = payload.marketing_enabled
        await store.save_project_marketing_config(project_id, profile)

    await orchestrator.start_project(
        idea_inicial=payload.idea_inicial,
        project_id=project_id,
    )
    return CreateProjectResponse(project_id=project_id, status="RUNNING")

