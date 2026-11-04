"""Command Line Interface (CLI) for running and monitoring the Software Factory."""

import argparse
import asyncio
import re
import sys
import uuid
from pathlib import Path

from app.core.config import settings
from app.schemas.routing import AgentID, StepExecutionRecord
from app.services.backfill_service import (
    ProjectBackfillService,
    extend_project_with_new_agents,
)
from app.services.code_materializer import CodeMaterializerService
from app.services.github_publisher import GitHubPublisherService
from app.services.llm_gateway import GeminiLLMGateway, MockLLMGateway
from app.services.local_deployer import LocalSandboxDeployer
from app.services.mail_service import MailService
from app.services.notion_mcp_service import (
    KnowledgeSyncPort,
    LocalNotionMirrorAdapter,
    NotionMCPAdapter,
)
from app.services.office_store import OfficeStore
from app.services.orchestrator_service import OrchestratorService
from app.services.prompt_loader import PromptLoader
from app.services.vercel_deployer import VercelDeployerService
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


async def sync_notion_command(project_id: str, local_mirror: bool = False) -> None:
    """Synchronize completed project deliverables and internal email logs to Notion MCP."""
    proj_dir = Path(settings.WORKSPACES_DIR) / project_id
    if not proj_dir.exists() or not proj_dir.is_dir():
        print(f"\n[CLI] Error: El directorio '{project_id}' no existe en {proj_dir}.\n")
        sys.exit(1)

    use_local = local_mirror or not settings.NOTION_API_KEY
    mode_name = "Espejo Local (Zero-Config)" if use_local else "Notion Cloud REST API"

    print(f"\n[CLI] Sincronizando con Notion MCP para el proyecto: {project_id}")
    print(f"[CLI] Modo de Sincronización : {mode_name}")

    adapter: KnowledgeSyncPort
    if use_local:
        adapter = LocalNotionMirrorAdapter(workspaces_dir=settings.WORKSPACES_DIR)
    else:
        adapter = NotionMCPAdapter(
            api_key=settings.NOTION_API_KEY or "",
            parent_page_id=settings.NOTION_PARENT_PAGE_ID,
            workspaces_dir=settings.WORKSPACES_DIR,
        )

    # 1. Create or connect project hub
    hub_id = await adapter.create_project_hub(
        project_id=project_id,
        title=f"Proyecto {project_id}",
        summary="Sincronización a posteriori de entregables y telemetría de AgentOffice",
    )
    print(f"[CLI] Project Hub inicializado : {hub_id}")

    # 2. Iterate and sync deliverables
    md_files = sorted(
        [p for p in proj_dir.glob("*.md") if p.is_file() and p.name != "README.md"],
        key=lambda p: (
            int(p.stem.split("_")[0]) if p.stem.split("_")[0].isdigit() else 999,
            p.name,
        ),
    )

    print(f"\n[CLI] Sincronizando {len(md_files)} entregables Markdown...")
    synced_deliverables = 0
    for md_path in md_files:
        stem_parts = md_path.stem.split("_", 1)
        step_num = int(stem_parts[0]) if stem_parts[0].isdigit() else 0
        agent_name = stem_parts[1] if len(stem_parts) > 1 else "unknown"
        content = md_path.read_text(encoding="utf-8")

        m_state = re.search(r'estado_entregable:\s*"([^"]+)"', content)
        deliv_title = m_state.group(1) if m_state else f"Entregable {md_path.stem}"

        subpage_id = await adapter.append_deliverable_page(
            project_id=project_id,
            step_number=step_num,
            agent_id=agent_name,
            deliverable_title=deliv_title,
            markdown_content=content,
        )
        synced_deliverables += 1
        print(f"  [Paso {step_num:02d}] {agent_name:<21} -> Sincronizado ({subpage_id[:32]})")

    # 3. Synchronize internal agent emails
    store = OfficeStore()
    emails = await store.get_emails(project_id=project_id)
    print(f"\n[CLI] Sincronizando {len(emails)} correos internos auditados...")
    for em in emails:
        await adapter.log_agent_email(
            project_id=project_id,
            email_data=em.model_dump(mode="json"),
        )

    # 4. Update overall status
    await adapter.update_project_status(
        project_id=project_id,
        status_data={
            "current_status": "SINCRONIZADO_COMPLETO",
            "steps_completed": len(md_files),
            "emails_logged": len(emails),
            "mode": mode_name,
        },
    )

    mirror_index = proj_dir / "notion_mirror" / "INDEX.html"
    print("\n------------------------------------------------------------")
    print("Sincronización Notion MCP completada con éxito.")
    print(f"Total Entregables Sincronizados : {synced_deliverables}")
    print(f"Total Correos Auditados         : {len(emails)}")
    if mirror_index.exists():
        print(f"Navegador Local Espejo          : {mirror_index}")
    print("------------------------------------------------------------\n")


async def backfill_command(project_id: str, real_mail: bool, notion: bool) -> None:
    """Retrospectively hydrate project data into SQLite and optionally sync Strato and Notion."""
    service = ProjectBackfillService()
    try:
        res = await service.backfill_project(
            project_id=project_id,
            sync_real_mail=real_mail,
            sync_notion=notion,
        )
    except FileNotFoundError as exc:
        print(f"\n[ERROR] {exc}\n")
        return

    print("\n------------------------------------------------------------")
    print(f"Hidratación Retrospectiva Completada: Proyecto {project_id}")
    print("------------------------------------------------------------")
    print(f"Total Entregables Escaneados : {res['total_deliverables_found']}")
    print(f"Conversaciones Agregadas     : {res['conversations_added']}")
    print(f"Correos Internos Agregados   : {res['emails_added']}")
    if real_mail:
        print(f"Correos Sincronizados Strato : {res['real_mail_synced']}")
    if notion:
        print(f"Entregables Sincroniz. Notion: {res['notion_synced']}")
    print("------------------------------------------------------------\n")


async def extend_agents_command(
    project_id: str,
    real_mail: bool = False,
    sync_notion: bool = False,
) -> None:
    """Extend an existing legacy project with CEO, UI/UX, Marketing, and Sales departments."""
    try:
        res = await extend_project_with_new_agents(
            project_id=project_id,
            real_mail=real_mail,
            sync_notion=sync_notion,
        )
    except FileNotFoundError as exc:
        print(f"\n[ERROR] {exc}\n")
        return

    print("\n------------------------------------------------------------")
    print(f"Extensión de Agentes Completada: Proyecto {project_id}")
    print("------------------------------------------------------------")
    print("Nodos Ejecutados             :")
    for node_name in res.get("executed_nodes", []):
        print(f"  - {node_name}")
    print(f"Artefactos Materializados    : {len(res.get('materialized_files', []))}")
    for mf in res.get("materialized_files", []):
        print(f"  * {mf}")
    print(f"Estado Final                 : {res.get('status', 'UNKNOWN')}")
    print("------------------------------------------------------------\n")


async def publish_git_command(project_id: str, repo_name: str, public: bool) -> None:
    """Create a remote repository on GitHub and push the materialized build."""
    service = GitHubPublisherService()
    try:
        res = await service.publish_project_build(
            project_id=project_id,
            repo_name=repo_name,
            private=not public,
        )
    except Exception as exc:
        print(f"\n[ERROR] Fallo al publicar en GitHub: {exc}\n")
        return

    visibility = "Público" if public else "Privado"
    print("\n------------------------------------------------------------")
    print(f"Publicación en GitHub Completada: Proyecto {project_id}")
    print("------------------------------------------------------------")
    print(f"Repositorio     : {res['repo_url']}")
    print(f"Visibilidad     : {visibility}")
    print(f"Archivos Subidos: {res['total_files']}")
    print("Rama Principal  : main")
    print("------------------------------------------------------------\n")


async def deploy_local_command(project_id: str, up: bool) -> None:
    """Prepare local Docker Compose stack and optionally spin up containers."""
    deployer = LocalSandboxDeployer()
    try:
        res = await deployer.prepare_and_check_local_stack(
            project_id=project_id,
            start_containers=up,
        )
    except Exception as exc:
        print(f"\n[ERROR] Fallo en despliegue local: {exc}\n")
        return

    ciso_status = "APLICADO" if res["ciso_patch_applied"] else "No requerido/ausente"
    containers_status = "SÍ" if res["containers_started"] else "FALLÓ / Docker ausente"

    print("\n------------------------------------------------------------")
    print(f"Preparación de Entorno Local Docker: Proyecto {project_id}")
    print("------------------------------------------------------------")
    print(f"Archivo Compose            : {res['compose_path']}")
    print(f"Parche de Seguridad CISO   : {ciso_status}")
    print(f"Puerto PostgreSQL 16       : {res['ports']['postgres']}")
    print(f"Puerto Redis 7             : {res['ports']['redis']}")
    print(f"Puerto FastAPI Engine      : {res['ports']['engine_fastapi']}")
    if up:
        print(f"Contenedores Iniciados     : {containers_status}")
        print(f"Estado de Salud (Health)   : {res['health_check']}")
        if not res["containers_started"] and res.get("error_details"):
            print(f"Detalle del Error          : {res['error_details']}")
    print("------------------------------------------------------------\n")


async def deploy_vercel_command(project_id: str, name: str = "validator-hq-saas") -> None:
    """Build serverless web bundle and deploy to Vercel Cloud."""
    deployer = VercelDeployerService()
    try:
        res = await deployer.deploy_to_vercel(project_id=project_id, project_name=name)
    except Exception as exc:
        print(f"\n[ERROR] Fallo en despliegue a Vercel: {exc}\n")
        return

    print("\n------------------------------------------------------------")
    print(f"Despliegue Serverless en Vercel Cloud: Proyecto {project_id}")
    print("------------------------------------------------------------")
    print(f"Nombre en Vercel    : {res['project_name']}")
    print(f"Éxito               : {'SÍ' if res['success'] else 'NO'}")
    if res["deployment_url"]:
        print(f"URL de Producción   : {res['deployment_url']}")
        print(f"Endpoint de Salud   : {res['deployment_url']}/api/health")
        print(f"Demo Interactiva    : {res['deployment_url']}/#demo")
        print(f"Documentación       : {res['deployment_url']}/docs.html")
    print(f"Directorio Paquete  : {res['bundle_path']}")
    print(f"Archivos Desplegados: {res['total_files']}")
    print(f"Notificación CEO    : {'Enviada' if res['email_logged'] else 'No enviada'}")
    if res.get("error"):
        print(f"Detalle del Error   : {res['error']}")
    print("------------------------------------------------------------\n")


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

    # sync-notion command
    notion_parser = subparsers.add_parser(
        "sync-notion",
        help="Synchronize project deliverables and audit logs with Notion MCP",
    )
    notion_parser.add_argument("--project-id", required=True, type=str, help="Project ID")
    notion_parser.add_argument(
        "--local-mirror",
        action="store_true",
        help="Force zero-config local mirror generation regardless of API key",
    )

    # backfill command
    backfill_parser = subparsers.add_parser(
        "backfill",
        help="Hydrate SQLite from historical deliverables and optionally sync",
    )
    backfill_parser.add_argument("--project-id", required=True, type=str, help="Project ID")
    backfill_parser.add_argument(
        "--real-mail",
        action="store_true",
        help="Sync all emails to real Strato IMAP/SMTP",
    )
    backfill_parser.add_argument(
        "--notion",
        action="store_true",
        help="Sync deliverables and logs to Notion",
    )

    # publish-git command
    pub_parser = subparsers.add_parser(
        "publish-git",
        help="Create a remote GitHub repository and push build code",
    )
    pub_parser.add_argument("--project-id", required=True, type=str, help="Project ID")
    pub_parser.add_argument("--repo-name", required=True, type=str, help="Target repository name")
    pub_parser.add_argument(
        "--public",
        action="store_true",
        help="Make GitHub repository public instead of private",
    )

    # deploy-local command
    deploy_parser = subparsers.add_parser(
        "deploy-local",
        help="Prepare local Docker Compose stack and optionally spin up containers",
    )
    deploy_parser.add_argument("--project-id", required=True, type=str, help="Project ID")
    deploy_parser.add_argument(
        "--up",
        action="store_true",
        help="Start docker containers with docker compose up -d",
    )

    # deploy-vercel command
    vercel_parser = subparsers.add_parser(
        "deploy-vercel",
        help="Build and deploy serverless web package to Vercel Cloud",
    )
    vercel_parser.add_argument("--project-id", required=True, type=str, help="Project ID")
    vercel_parser.add_argument(
        "--name",
        default="validator-hq-saas",
        type=str,
        help="Vercel project name",
    )

    # extend-agents command
    extend_parser = subparsers.add_parser(
        "extend-agents",
        help="Extend legacy project with 4 new departments (CEO, UI/UX, Marketing, Sales)",
    )
    extend_parser.add_argument(
        "--project-id",
        required=True,
        type=str,
        help="Legacy Project ID to extend",
    )
    extend_parser.add_argument(
        "--real-mail",
        action="store_true",
        help="Sync generated handoff emails to Strato IMAP",
    )
    extend_parser.add_argument(
        "--sync-notion",
        action="store_true",
        help="Sync deliverables and logs to Notion / Local Mirror",
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
        case "sync-notion":
            asyncio.run(sync_notion_command(args.project_id, args.local_mirror))
        case "backfill":
            asyncio.run(backfill_command(args.project_id, args.real_mail, args.notion))
        case "extend-agents":
            asyncio.run(
                extend_agents_command(
                    args.project_id,
                    args.real_mail,
                    args.sync_notion,
                )
            )
        case "publish-git":
            asyncio.run(publish_git_command(args.project_id, args.repo_name, args.public))
        case "deploy-local":
            asyncio.run(deploy_local_command(args.project_id, args.up))
        case "deploy-vercel":
            asyncio.run(deploy_vercel_command(args.project_id, args.name))
        case _:
            parser.print_help()


if __name__ == "__main__":
    main()
