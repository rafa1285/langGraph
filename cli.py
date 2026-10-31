"""Command Line Interface (CLI) for running and monitoring the Software Factory."""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from app.core.config import settings
from app.schemas.routing import AgentID, StepExecutionRecord
from app.services.code_materializer import CodeMaterializerService
from app.services.llm_gateway import GeminiLLMGateway, MockLLMGateway
from app.services.local_deployer import LocalSandboxDeployer
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.orchestrator_service import OrchestratorService
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")



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


async def resume_command(project_id: str, mock: bool = False) -> None:
    """Resume execution of an interrupted project from its last checkpoint, streaming steps."""
    print(f"\n[CLI] Reanudando proyecto: {project_id}...\n")

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
        steps_executed = 0
        async for chunk in orchestrator.stream_resume_project(project_id):
            for _node_name, output in chunk.items():
                if isinstance(output, dict):
                    records = output.get("execution_history", [])
                    if isinstance(records, list) and records:
                        rec = records[-1]
                        if isinstance(rec, StepExecutionRecord):
                            steps_executed += 1
                            print(
                                f"[Paso {rec.step_number:02d}] "
                                f"{rec.agent_id.value} -> "
                                f"{rec.status.value} -> "
                                f"Archivo guardado en {rec.artifact_path}"
                            )

        final_state = await orchestrator.get_project_state(project_id)
        if final_state is None:
            print(f"[CLI] Error: Proyecto '{project_id}' no encontrado.")
            return

        history = final_state.get("execution_history", [])
        ultimo = history[-1].agent_id.value if history else "Ninguno"
        print(f"\n[CLI] Proyecto {project_id} finalizado tras reanudación. Último nodo: {ultimo}")
        print(f"[CLI] Pasos completados en esta reanudación: {steps_executed}\n")
    finally:
        await orchestrator.close()


def _resolve_agent_id(agent_str: str | None) -> AgentID | None:
    """Resolve user-supplied agent string to an AgentID enum value."""
    if not agent_str:
        return None
    val = agent_str.strip().lower()
    for agent in AgentID:
        if agent.value == val or val in agent.value:
            return agent
    return None


async def inbox_command(project_id: str, agent: str | None = None) -> None:
    """Display internal email inbox and sent messages for a project."""
    store = OfficeStore()
    agent_id = _resolve_agent_id(agent)
    emails = await store.get_emails(project_id=project_id, agent_id=agent_id)

    if not emails:
        filter_msg = f" para el agente '{agent}'" if agent else ""
        print(f"\n[CLI] No se encontraron correos para '{project_id}'{filter_msg}.\n")
        return

    print(f"\n--- Bandeja de Correo del Proyecto: {project_id} ({len(emails)} mensajes) ---")
    header = (
        f"{'ID':<36} | {'De':<28} | {'Para':<28} | {'Prioridad':<8} | "
        f"{'Leído':<5} | {'Fecha':<16} | Asunto"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for em in emails:
        read_mark = "SÍ" if em.is_read else "NO"
        date_str = em.created_at.strftime("%Y-%m-%d %H:%M")
        subj = em.subject if len(em.subject) <= 35 else em.subject[:32] + "..."
        print(
            f"{str(em.id):<36} | {em.sender:<28} | {em.recipient:<28} | "
            f"{em.priority:<8} | {read_mark:<5} | {date_str:<16} | {subj}"
        )
    print(sep + "\n")


async def read_email_command(email_id: str) -> None:
    """Display the full content and attached deliverable of an internal email."""
    store = OfficeStore()
    email = await store.get_email_by_id(email_id)

    if email is None:
        print(f"\n[CLI] Error: Correo con ID '{email_id}' no encontrado.\n")
        return

    read_status = "Leído" if email.is_read else "No leído (marcado como leído ahora)"
    if not email.is_read:
        await store.mark_emails_as_read([email.id])

    date_str = email.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    print("\n" + "=" * 80)
    print(" 📧 CORREO INTERNO DE LA SOFTWARE FACTORY")
    print("=" * 80)
    print(f"ID        : {email.id}")
    print(f"Proyecto  : {email.project_id} (Paso {email.step_number:02d})")
    print(f"De        : {email.sender}")
    print(f"Para      : {email.recipient}")
    if email.cc:
        print(f"CC        : {', '.join(email.cc)}")
    print(f"Prioridad : {email.priority}")
    print(f"Estado    : {read_status}")
    print(f"Fecha     : {date_str}")
    print(f"Asunto    : {email.subject}")
    print(f"Adjunto   : {email.attached_deliverable_path}")
    print("-" * 80)
    print("CUERPO DEL MENSAJE:")
    print(email.body_summary)
    print("=" * 80 + "\n")


async def conversations_command(project_id: str, agent: str | None = None) -> None:
    """List conversation turns, execution duration, and estimated tokens by agent."""
    store = OfficeStore()
    agent_id = _resolve_agent_id(agent)
    conversations = await store.get_conversations(project_id=project_id, agent_id=agent_id)

    if not conversations:
        filter_msg = f" para el agente '{agent}'" if agent else ""
        print(
            f"\n[CLI] No se encontraron conversaciones para '{project_id}'{filter_msg}.\n"
        )
        return

    print(f"\n--- Historial de Conversaciones y Telemetría: {project_id} ---")
    header = (
        f"{'Paso':<6} | {'Agente':<21} | {'Estado':<35} | {'Veredicto':<12} | "
        f"{'Score':<5} | {'Dur (ms)':<8} | {'Tok In':<8} | {'Tok Out':<8} | Culpable"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    total_duration = 0
    total_tokens_in = 0
    total_tokens_out = 0

    for conv in conversations:
        total_duration += conv.duration_ms
        total_tokens_in += conv.estimated_tokens_in
        total_tokens_out += conv.estimated_tokens_out
        score_str = str(conv.score) if conv.score is not None else "-"
        culprit_str = conv.culprit or "-"

        print(
            f"[{conv.step_number:02d}]  | {conv.agent_id.value:<21} | "
            f"{conv.status.value:<35} | {conv.verdict:<12} | "
            f"{score_str:<5} | {conv.duration_ms:<8} | "
            f"{conv.estimated_tokens_in:<8} | {conv.estimated_tokens_out:<8} | "
            f"{culprit_str}"
        )

    print(sep)
    print(f"Total Turnos        : {len(conversations)}")
    print(f"Duración Acumulada  : {total_duration} ms ({total_duration / 1000:.2f} s)")
    print(f"Tokens Estimados In : {total_tokens_in:,}")
    print(f"Tokens Estimados Out: {total_tokens_out:,}")
    print(f"Tokens Totales      : {total_tokens_in + total_tokens_out:,}\n")


async def materialize_command(project_id: str, skip_deployer: bool = False) -> None:
    """Materialize project deliverables into source code in build/ and validate environment."""
    print(f"\n[CLI] Materializando código fuente para el proyecto: {project_id}...")

    materializer = CodeMaterializerService()
    try:
        build_dir, manifest = materializer.materialize_project(project_id)
    except FileNotFoundError as exc:
        print(f"[CLI] Error: {exc}")
        sys.exit(1)

    files = manifest.get("files", [])
    if not files:
        print(f"[CLI] Aviso: No se extrajeron archivos para el proyecto '{project_id}'.")
        return

    print(f"\n--- Archivos Materializados en: {build_dir} ---")
    header = f"{'Ruta de Archivo':<55} | {'Tamaño':<10} | {'SHA-256':<10} | Agente Autor"
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for item in files:
        path_str = item["path"]
        size_str = f"{item['size_bytes']:,} B"
        sha_short = item["sha256"][:8]
        author = f"{item['author_agent']} (Paso {item['step_number']:02d})"
        print(f"{path_str:<55} | {size_str:<10} | {sha_short:<10} | {author}")

    print(sep)
    print(f"Total Archivos Extraídos : {len(files)}")
    print(f"Directorio de Salida     : {build_dir}")
    print(f"Archivo de Manifiesto    : {build_dir / 'MANIFEST.json'}")

    if not skip_deployer:
        print("\n[CLI] Preparando entorno local y validando orquestación...")
        mail_service = MailService()
        deployer = LocalSandboxDeployer(mail_service=mail_service)
        env_result = deployer.prepare_local_environment(build_dir)
        scripts = ", ".join(env_result.get("scripts", []))
        compose_file = env_result.get("compose_file") or "No detectado"
        print(f"[CLI] Archivo Compose detectado : {compose_file}")
        print(f"[CLI] Scripts de inicio rápido : {scripts}")

        is_valid = await deployer.validate_compose_syntax(
            build_path=build_dir,
            project_id=project_id,
            mail_service=mail_service,
        )
        status_txt = "APROBADA [OK]" if is_valid else "FALLIDA [ERROR]"
        print(f"[CLI] Validación de Sintaxis   : {status_txt}")
        print("[CLI] Correo de entrega enviado a: ceo@agentoffice.local\n")
    else:
        print("\n[CLI] Despliegue y validación local omitidos (--skip-deployer).\n")


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
    resume_parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockLLMGateway for fast offline simulation",
    )

    # inbox command
    inbox_parser = subparsers.add_parser("inbox", help="Display internal email messages")
    inbox_parser.add_argument("--project-id", required=True, type=str, help="Project ID")
    inbox_parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help="Optional agent filter (e.g. agente_03_laravel)",
    )

    # read-email command
    read_parser = subparsers.add_parser("read-email", help="Read full content of an email")
    read_parser.add_argument("--email-id", required=True, type=str, help="Email UUID")

    # conversations command
    conv_parser = subparsers.add_parser(
        "conversations",
        help="Display conversation turns and telemetry",
    )
    conv_parser.add_argument("--project-id", required=True, type=str, help="Project ID")
    conv_parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help="Optional agent filter (e.g. agente_10_ciso)",
    )

    # materialize command
    mat_parser = subparsers.add_parser(
        "materialize",
        help="Materialize project deliverables into real source code",
    )
    mat_parser.add_argument("--project-id", required=True, type=str, help="Project ID")
    mat_parser.add_argument(
        "--skip-deployer",
        action="store_true",
        help="Skip local deployer preparation and syntax validation",
    )

    args = parser.parse_args()

    match args.command:
        case "run":
            asyncio.run(run_command(args.idea, args.mock, args.project_id))
        case "status":
            asyncio.run(status_command(args.project_id))
        case "resume":
            asyncio.run(resume_command(args.project_id, args.mock))
        case "inbox":
            asyncio.run(inbox_command(args.project_id, args.agent))
        case "read-email":
            asyncio.run(read_email_command(args.email_id))
        case "conversations":
            asyncio.run(conversations_command(args.project_id, args.agent))
        case "materialize":
            asyncio.run(materialize_command(args.project_id, args.skip_deployer))
        case _:
            parser.print_help()


if __name__ == "__main__":
    main()
