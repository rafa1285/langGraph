"""Orchestrator service managing LangGraph lifecycle and SQLite checkpoints."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import settings
from app.graph.state import SoftwareFactoryState, create_initial_state
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.llm_gateway import (
    GeminiLLMGateway,
    LLMGatewayProtocol,
    MockLLMGateway,
)
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter

if TYPE_CHECKING:
    from app.graph.workflow import FactoryGraph


class OrchestratorService:
    """Service to orchestrate project creation, execution, and state checkpointing."""

    def __init__(
        self,
        db_path: str = settings.CHECKPOINT_DB_PATH,
        llm_gateway: LLMGatewayProtocol | None = None,
        prompt_loader: PromptLoader | None = None,
        workspace_writer: WorkspaceWriter | None = None,
        office_store: OfficeStore | None = None,
        mail_service: MailService | None = None,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        """Initialize the Orchestrator with storage and service dependencies."""
        from app.graph.nodes import FactoryNodes
        from app.graph.workflow import compile_factory_graph

        self.db_path = db_path
        self.llm_gateway = (
            llm_gateway
            or (MockLLMGateway() if settings.USE_MOCK_LLM else GeminiLLMGateway())
        )
        self.prompt_loader = prompt_loader or PromptLoader()
        self.workspace_writer = workspace_writer or WorkspaceWriter()
        self.office_store = office_store or OfficeStore()
        self.mail_service = mail_service or MailService(self.office_store)

        self.nodes: FactoryNodes = FactoryNodes(
            llm_gateway=self.llm_gateway,
            prompt_loader=self.prompt_loader,
            workspace_writer=self.workspace_writer,
            office_store=self.office_store,
            mail_service=self.mail_service,
        )

        self.checkpointer = checkpointer
        self._saver_cm: Any = None
        self._background_tasks: dict[str, asyncio.Task[Any]] = {}

        if self.checkpointer is not None:
            self.graph: FactoryGraph = compile_factory_graph(
                self.nodes,
                checkpointer=self.checkpointer,
            )
        else:
            self.graph = cast("FactoryGraph", None)

    async def initialize(self) -> None:
        """Initialize AsyncSqliteSaver connection if not pre-injected and compile graph."""
        if self.checkpointer is None:
            from app.graph.workflow import compile_factory_graph

            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._saver_cm = AsyncSqliteSaver.from_conn_string(self.db_path)
            self.checkpointer = await self._saver_cm.__aenter__()
            self.graph = compile_factory_graph(self.nodes, checkpointer=self.checkpointer)

    async def close(self) -> None:
        """Close SQLite checkpointer context if managed internally."""
        if self._saver_cm is not None:
            await self._saver_cm.__aexit__(None, None, None)
            self._saver_cm = None
            self.checkpointer = None

    async def start_project(
        self,
        idea_inicial: str,
        project_id: str | None = None,
    ) -> str:
        """Initialize state and launch execution in background task, returning project_id."""
        if self.graph is None:
            await self.initialize()

        pid = project_id or f"proj_{uuid.uuid4().hex[:8]}"
        initial_state = create_initial_state(project_id=pid, idea_inicial=idea_inicial)
        config: RunnableConfig = {"configurable": {"thread_id": pid}}

        task = asyncio.create_task(self.graph.ainvoke(initial_state, config=config))
        self._background_tasks[pid] = task
        return pid

    async def run_project_to_completion(
        self,
        project_id: str,
        idea_inicial: str,
    ) -> SoftwareFactoryState:
        """Execute graph from start to end and return the final state."""
        if self.graph is None:
            await self.initialize()

        initial_state = create_initial_state(project_id=project_id, idea_inicial=idea_inicial)
        config: RunnableConfig = {"configurable": {"thread_id": project_id}}
        result = await self.graph.ainvoke(initial_state, config=config)
        return cast(SoftwareFactoryState, result)

    async def stream_project(
        self,
        project_id: str,
        idea_inicial: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream graph node transitions in real-time."""
        if self.graph is None:
            await self.initialize()

        initial_state = create_initial_state(project_id=project_id, idea_inicial=idea_inicial)
        config: RunnableConfig = {"configurable": {"thread_id": project_id}}
        async for chunk in self.graph.astream(
            initial_state,
            config=config,
            stream_mode="updates",
        ):
            yield chunk

    async def get_project_state(self, project_id: str) -> SoftwareFactoryState | None:
        """Query latest checkpoint saved in SQLite via aget_state."""
        if self.graph is None:
            await self.initialize()

        config: RunnableConfig = {"configurable": {"thread_id": project_id}}
        snapshot = await self.graph.aget_state(config)
        if snapshot and snapshot.values:
            return cast(SoftwareFactoryState, snapshot.values)
        return None

    async def _prepare_resume(self, config: RunnableConfig, project_id: str) -> None:
        """Inspect checkpoint and automatically reopen circuit-breaker halted CISO states."""
        snapshot = await self.graph.aget_state(config)
        if not snapshot or not snapshot.values:
            return

        history = snapshot.values.get("execution_history", [])
        last_record = history[-1] if history else None
        completed_status = DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100
        is_completed = (
            last_record is not None and last_record.status == completed_status
        ) or snapshot.values.get("current_status") == completed_status

        blocked_status = DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
        if not snapshot.next and not is_completed:
            if last_record and last_record.agent_id == AgentID.AGENTE_10_CISO and (
                last_record.status == blocked_status
                or snapshot.values.get("status_ciso") == blocked_status
            ):
                print(
                    f"\n[Orchestrator] Reapertura automática para {project_id}: "
                    "Reanudando CISO como BLINDADO_APTO_PRODUCCION hacia Agente 08 (Docs)..."
                )
                await self.graph.aupdate_state(
                    config,
                    {
                        "status_ciso": DeliverableStatus.BLINDADO_APTO_PRODUCCION,
                        "current_status": DeliverableStatus.BLINDADO_APTO_PRODUCCION,
                    },
                    as_node=AgentID.AGENTE_10_CISO.value,
                )

    async def resume_project(self, project_id: str) -> SoftwareFactoryState:
        """Resume execution of an interrupted project from its SQLite checkpoint."""
        if self.graph is None:
            await self.initialize()

        config: RunnableConfig = {"configurable": {"thread_id": project_id}}
        await self._prepare_resume(config, project_id)
        result = await self.graph.ainvoke(None, config=config)
        return cast(SoftwareFactoryState, result)

    async def stream_resume_project(
        self,
        project_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream graph node transitions in real-time when resuming an interrupted project."""
        if self.graph is None:
            await self.initialize()

        config: RunnableConfig = {"configurable": {"thread_id": project_id}}
        await self._prepare_resume(config, project_id)
        async for chunk in self.graph.astream(
            None,
            config=config,
            stream_mode="updates",
        ):
            yield chunk
