"""Main FastAPI application entry point with lifespan management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.services.llm_gateway import GeminiLLMGateway, MockLLMGateway
from app.services.orchestrator_service import OrchestratorService
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


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
    """Application factory for the Software Factory FastAPI service."""
    application = FastAPI(
        title="Software Factory LangGraph Backend",
        description="Autonomous multi-agent backend powered by LangGraph and FastAPI.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
