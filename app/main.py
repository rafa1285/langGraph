"""Main FastAPI application entry point with lifespan management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.routes_office import router as office_router
from app.api.routes_telemetry import router as telemetry_router
from app.core.config import settings
from app.services.llm_gateway import GeminiLLMGateway, MockLLMGateway
from app.services.orchestrator_service import OrchestratorService
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter

# Directory containing the 2D Pixel Art SPA assets
_STATIC_DIR: Path = Path(__file__).parent / "static"


async def _serve_spa() -> FileResponse:
    """Serve the AgentOffice 2D Pixel Art single-page application."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


async def _serve_dashboard() -> FileResponse:
    """Serve the AgentOffice Operations & Telemetry Dashboard."""
    return FileResponse(str(_STATIC_DIR / "dashboard.html"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle."""
    # 1. Ensure storage and prompts exist
    Path(settings.CHECKPOINT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.WORKSPACES_DIR).mkdir(parents=True, exist_ok=True)

    prompt_loader = PromptLoader(prompts_dir=settings.PROMPTS_DIR)
    prompt_loader.ensure_prompt_files_exist()

    workspace_writer = WorkspaceWriter(base_dir=settings.WORKSPACES_DIR)
    llm_gateway = (
        MockLLMGateway() if settings.USE_MOCK_LLM else GeminiLLMGateway()
    )

    # 2. Initialize orchestrator with SQLite checkpoints
    orchestrator = OrchestratorService(
        db_path=settings.CHECKPOINT_DB_PATH,
        llm_gateway=llm_gateway,
        prompt_loader=prompt_loader,
        workspace_writer=workspace_writer,
    )
    await orchestrator.initialize()
    app.state.orchestrator = orchestrator

    yield

    # 3. Clean up connections on shutdown
    await orchestrator.close()


def create_app() -> FastAPI:
    """Application factory for the AgentOffice Software Factory service."""
    application = FastAPI(
        title="AgentOffice — Software Factory",
        description=(
            "Autonomous multi-agent software factory powered by LangGraph, FastAPI "
            "and a 2D Pixel Art virtual office UI."
        ),
        version="2.0.0",
        lifespan=lifespan,
    )

    # Existing pipeline API routes
    application.include_router(router)

    # Office UI routes (agent status, chat — Phase 2+)
    application.include_router(office_router)

    # Telemetry, Agent Thoughts & Operations Dashboard routes
    application.include_router(telemetry_router)

    # Serve the 2D Pixel Art SPA when the static directory is present
    if _STATIC_DIR.exists():
        application.mount(
            "/static",
            StaticFiles(directory=str(_STATIC_DIR)),
            name="static",
        )
        application.add_api_route(
            "/",
            _serve_dashboard,
            methods=["GET"],
            include_in_schema=False,
        )
        application.add_api_route(
            "/dashboard",
            _serve_dashboard,
            methods=["GET"],
            include_in_schema=False,
        )
        application.add_api_route(
            "/office",
            _serve_spa,
            methods=["GET"],
            include_in_schema=False,
        )

    return application


app = create_app()

# Expose compiled graph for LangGraph Studio and langgraph-cli
try:
    from app.graph_studio import graph
except Exception:
    graph = None  # type: ignore[assignment]

