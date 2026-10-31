"""Command Line Interface (CLI) for running and monitoring the Software Factory."""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from app.core.config import settings
from app.schemas.routing import StepExecutionRecord
from app.services.llm_gateway import GeminiLLMGateway, MockLLMGateway
from app.services.orchestrator_service import OrchestratorService
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter


async def run_command(idea: str, mock: bool, project_id: str | None) -> None:
    """Execute project pipeline in real-time, printing node transitions."""
    pid = project_id or f"proj_{uuid.uuid4().hex[:8]}"
    print(f"\n[CLI] Iniciando Software Factory para el proyecto: {pid}")
    print(f"[CLI] Idea inicial: {idea}\n")

    # Ensure directories exist
    Path(settings.PROMPTS_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.WORKSPACES_DIR).mkdir(parents=True, exist_ok=True)

    prompt_loader = PromptLoader(prompts_dir=settings.PROMPTS_DIR)
    prompt_loader.ensure_prompt_files_exist()
    workspace_writer = WorkspaceWriter(base_dir=settings.WORKSPACES_DIR)

    use_mock = mock or settings.USE_MOCK_LLM
    gateway = MockLLMGateway() if use_mock else GeminiLLMGateway()

    orchestrator = OrchestratorService(
        db_path=settings.CHECKPOINT_DB_PATH,
        llm_gateway=gateway,
        prompt_loader=prompt_loader,
        workspace_writer=workspace_writer,
    )
    await orchestrator.initialize()

    try:
        async for chunk in orchestrator.stream_project(pid, idea):
            for _node_name, output in chunk.items():
                if isinstance(output, dict):
                    records = output.get("execution_history", [])
                    if isinstance(records, list) and records:
                        rec = records[-1]
                        if isinstance(rec, StepExecutionRecord):
                            print(
                                f"[Paso {rec.step_number:02d}] "
                                f"{rec.agent_id.value} -> "
                                f"{rec.status.value} -> "
                                f"Archivo guardado en {rec.artifact_path}"
                            )

        print(f"\n[CLI] Proyecto {pid} finalizado con éxito.\n")
    finally:
        await orchestrator.close()


async def status_command(project_id: str) -> None:
    """Query and display operational status and audit log of an existing project."""
    orchestrator = OrchestratorService(db_path=settings.CHECKPOINT_DB_PATH)
    await orchestrator.initialize()

    try:
        state = await orchestrator.get_project_state(project_id)
        if state is None:
            print(f"[CLI] Error: Proyecto '{project_id}' no encontrado.")
            sys.exit(1)

        history = state.get("execution_history", [])
        ultimo_agente = history[-1].agent_id.value if history else "Ninguno"

        print(f"\n--- Estado del Proyecto: {project_id} ---")
        print(f"Último agente activo : {ultimo_agente}")
        print(f"Pasos completados    : {len(history)}")
        print(f"Status QA PHP        : {state.get('status_qa_php')}")
        print(f"Status QA Python     : {state.get('status_qa_python')}")
        print(f"Status CISO          : {state.get('status_ciso')}")
        print(f"Contador de reintentos: {state.get('retry_counts')}\n")
    finally:
        await orchestrator.close()


async def resume_command(project_id: str) -> None:
    """Resume execution of an interrupted project from its last checkpoint."""
    print(f"\n[CLI] Reanudando proyecto: {project_id}...")
    orchestrator = OrchestratorService(db_path=settings.CHECKPOINT_DB_PATH)
    await orchestrator.initialize()

    try:
        final_state = await orchestrator.resume_project(project_id)
        history = final_state.get("execution_history", [])
        ultimo = history[-1].agent_id.value if history else "Ninguno"
        print(f"[CLI] Proyecto completado tras reanudación. Último nodo: {ultimo}\n")
    finally:
        await orchestrator.close()


def main() -> None:
    """Parse command line arguments and execute corresponding async commands."""
    parser = argparse.ArgumentParser(
        description="Software Factory LangGraph Backend CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run the full agent pipeline for an idea")
    run_parser.add_argument("--idea", required=True, type=str, help="Initial software idea")
    run_parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockLLMGateway for fast offline simulation",
    )
    run_parser.add_argument(
        "--project-id",
        type=str,
        default=None,
        help="Optional custom project identifier",
    )

    # status command
    status_parser = subparsers.add_parser("status", help="Get status of an existing project")
    status_parser.add_argument("--project-id", required=True, type=str, help="Project ID")

    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted project")
    resume_parser.add_argument("--project-id", required=True, type=str, help="Project ID")

    args = parser.parse_args()

    match args.command:
        case "run":
            asyncio.run(run_command(args.idea, args.mock, args.project_id))
        case "status":
            asyncio.run(status_command(args.project_id))
        case "resume":
            asyncio.run(resume_command(args.project_id))
        case _:
            parser.print_help()


if __name__ == "__main__":
    main()
