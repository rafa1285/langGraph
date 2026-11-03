"""Phase 6 tests: Conversation persistence, internal agent email, and telemetry."""

from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.graph.nodes import FactoryNodes
from app.graph.state import create_initial_state
from app.graph.workflow import compile_factory_graph
from app.schemas.office import AgentConversationRecord, AgentEmailRecord
from app.schemas.routing import AgentID, DeliverableStatus, RoutingHeader
from app.services.llm_gateway import MockLLMGateway
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter
from cli import conversations_command, inbox_command, read_email_command, run_command


@pytest.mark.asyncio
async def test_office_store_crud_and_filtering(tmp_path: Path) -> None:
    """Test OfficeStore creation, conversation saving, email saving, and filters."""
    db_file = tmp_path / "office_test.sqlite"
    store = OfficeStore(db_path=db_file)
    await store.init_db()

    # 1. Save and retrieve conversations
    conv = AgentConversationRecord(
        project_id="proj_store_test",
        step_number=1,
        agent_id=AgentID.AGENTE_01_PM,
        system_prompt="System prompt PM",
        user_payload="Idea inicial",
        raw_response="--- \n origen: 'agente_01_pm' \n --- \n Contenido Pre-SDD",
        status=DeliverableStatus.PRE_SDD_LISTO,
        verdict="APROBADO",
        score=100,
        culprit=None,
        duration_ms=125,
        estimated_tokens_in=30,
        estimated_tokens_out=50,
    )
    await store.save_conversation(conv)

    convs = await store.get_conversations("proj_store_test")
    assert len(convs) == 1
    assert convs[0].agent_id == AgentID.AGENTE_01_PM
    assert convs[0].duration_ms == 125
    assert convs[0].score == 100

    # Filter by agent
    assert len(await store.get_conversations("proj_store_test", AgentID.AGENTE_01_PM)) == 1
    assert len(await store.get_conversations("proj_store_test", AgentID.AGENTE_02_ARCHITECT)) == 0

    # 2. Save and retrieve emails
    email = AgentEmailRecord(
        project_id="proj_store_test",
        step_number=1,
        sender="agente_01_pm@agentoffice.local",
        recipient="agente_02_architect@agentoffice.local",
        cc=[],
        subject="Handoff Pre-SDD listo",
        body_summary="Resumen ejecutivo del Pre-SDD.",
        attached_deliverable_path="workspaces/01_pre_sdd.md",
        priority="HIGH",
        is_read=False,
    )
    await store.save_email(email)

    emails = await store.get_emails("proj_store_test")
    assert len(emails) == 1
    assert emails[0].priority == "HIGH"
    assert not emails[0].is_read

    # Unread filter
    unread = await store.get_emails("proj_store_test", unread_only=True)
    assert len(unread) == 1

    # Mark as read
    await store.mark_emails_as_read([email.id])
    assert len(await store.get_emails("proj_store_test", unread_only=True)) == 0

    # Get by ID
    fetched = await store.get_email_by_id(email.id)
    assert fetched is not None
    assert fetched.is_read


@pytest.mark.asyncio
async def test_mail_service_handoff_and_inbox_injection(tmp_path: Path) -> None:
    """Test MailService handoff generation, fan-out recipients, and inbox prefix building."""
    db_file = tmp_path / "mail_service_test.sqlite"
    store = OfficeStore(db_path=db_file)
    mail_service = MailService(store)

    # 1. Multiple recipients handoff (Architect -> Laravel + FastAPI)
    header_arch = RoutingHeader(
        origen="agente_02_architect",
        destino_siguiente="agente_03_laravel, agente_04_fastapi",
        estado_entregable=DeliverableStatus.APROBADO_PARA_DESARROLLO,
        veredicto="APROBADO",
        puntuacion=100,
        culpable_detectado=None,
    )
    sent_arch = await mail_service.send_handoff_email(
        project_id="proj_mail_test",
        step_number=2,
        sender_id=AgentID.AGENTE_02_ARCHITECT,
        target_next="agente_03_laravel, agente_04_fastapi",
        header=header_arch,
        artifact_path="workspaces/02_sdd.md",
        raw_output="---\n---\n# SDD Arquitectura Técnica\nContenido del SDD.",
    )
    # Must send individual emails to both recipients
    assert len(sent_arch) == 2
    recipients = [e.recipient for e in sent_arch]
    assert "agente_03_laravel@agentoffice.local" in recipients
    assert "agente_04_fastapi@agentoffice.local" in recipients

    # 2. Critical rejection handoff (QA PHP -> Laravel)
    header_qa = RoutingHeader(
        origen="agente_05_qa_php",
        destino_siguiente="agente_03_laravel",
        estado_entregable=DeliverableStatus.RECHAZADO_PARA_REFACTOR,
        veredicto="RECHAZADO",
        puntuacion=40,
        culpable_detectado=AgentID.AGENTE_03_LARAVEL,
    )
    sent_qa = await mail_service.send_handoff_email(
        project_id="proj_mail_test",
        step_number=5,
        sender_id=AgentID.AGENTE_05_QA_PHP,
        target_next="agente_03_laravel",
        header=header_qa,
        artifact_path="workspaces/05_qa_php.md",
        raw_output="---\n---\n# Reporte QA\nRECHAZADO: Fallo crítico de validación.",
    )
    assert len(sent_qa) == 1
    assert sent_qa[0].priority == "CRITICAL"
    assert sent_qa[0].recipient == "agente_03_laravel@agentoffice.local"

    # 3. Fetch unread inbox for Laravel
    # Laravel should have received 2 emails (one from Architect, one from QA PHP)
    inbox_md, unread_emails = await mail_service.fetch_unread_inbox(
        project_id="proj_mail_test",
        agent_id=AgentID.AGENTE_03_LARAVEL,
    )
    assert len(unread_emails) == 2
    assert "### 📬 BANDEJA DE ENTRADA (CORREOS RECIBIDOS DE OTROS AGENTES)" in inbox_md
    assert "agente_02_architect@agentoffice.local" in inbox_md
    assert "agente_05_qa_php@agentoffice.local" in inbox_md

    # Second fetch should return empty as they were marked read
    inbox_md2, unread2 = await mail_service.fetch_unread_inbox(
        project_id="proj_mail_test",
        agent_id=AgentID.AGENTE_03_LARAVEL,
    )
    assert inbox_md2 == ""
    assert len(unread2) == 0


@pytest.mark.asyncio
async def test_full_workflow_end_to_end_with_mail_and_conversations(
    tmp_path: Path,
) -> None:
    """Test full LangGraph execution recording conversations and sending emails on rebounds."""
    store_file = tmp_path / "office_workflow.sqlite"
    office_store = OfficeStore(db_path=store_file)
    mail_service = MailService(office_store)

    gateway = MockLLMGateway(fail_qa_php_once=True)
    loader = PromptLoader(prompts_dir=tmp_path / "prompts")
    loader.ensure_prompt_files_exist()
    writer = WorkspaceWriter(base_dir=tmp_path / "workspaces")

    nodes = FactoryNodes(
        llm_gateway=gateway,
        prompt_loader=loader,
        workspace_writer=writer,
        office_store=office_store,
        mail_service=mail_service,
    )

    db_path = str(tmp_path / "checkpoints.db")
    project_id = "proj_e2e_office"
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        graph = compile_factory_graph(nodes, checkpointer=checkpointer, full_13_agents=False)
        state = create_initial_state(project_id, "Plataforma de comercio online.")
        config: RunnableConfig = {"configurable": {"thread_id": project_id}}
        final_state = await graph.ainvoke(state, config=config)

    # 1. Verify conversations recorded in SQLite
    conversations = await office_store.get_conversations(project_id)
    # 10 base agents + 2 extra turns from QA PHP refactoring (03_laravel + 05_qa_php) = 12
    assert len(conversations) == 12
    for conv in conversations:
        assert conv.project_id == project_id
        assert conv.duration_ms >= 0
        assert conv.estimated_tokens_in > 0
        assert conv.estimated_tokens_out > 0

    # 2. Verify emails persisted in SQLite
    emails = await office_store.get_emails(project_id)
    assert len(emails) >= 11

    # Verify at least one CRITICAL email from QA PHP to Laravel exists
    critical_emails = [e for e in emails if e.priority == "CRITICAL"]
    assert len(critical_emails) >= 1
    assert "agente_03_laravel" in critical_emails[0].recipient

    # 3. Verify final state completed
    assert final_state["status_ciso"] == DeliverableStatus.BLINDADO_APTO_PRODUCCION


@pytest.mark.asyncio
async def test_cli_office_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI commands: inbox, read-email, and conversations."""
    office_db = str(tmp_path / "cli_office.sqlite")
    check_db = str(tmp_path / "cli_checkpoints.sqlite")
    ws_dir = str(tmp_path / "workspaces")
    pid = "proj_cli_inspection"

    with patch("app.core.config.settings.OFFICE_DB_PATH", office_db):
        with patch("app.core.config.settings.CHECKPOINT_DB_PATH", check_db):
            with patch("app.core.config.settings.WORKSPACES_DIR", ws_dir):
                # Run full project with mock
                await run_command("App para telemetria", mock=True, project_id=pid)
                capsys.readouterr()

                # Test inbox command
                await inbox_command(pid)
                captured_inbox = capsys.readouterr()
                assert f"Bandeja de Correo del Proyecto: {pid}" in captured_inbox.out
                assert "agente_01_pm" in captured_inbox.out

                # Test inbox filter by agent
                await inbox_command(pid, agent="agente_03_laravel")
                captured_filter = capsys.readouterr()
                assert "agente_03_laravel" in captured_filter.out

                # Test conversations command
                await conversations_command(pid)
                captured_conv = capsys.readouterr()
                assert f"Historial de Conversaciones y Telemetría: {pid}" in captured_conv.out
                assert "Total Turnos" in captured_conv.out
                assert "Tokens Totales" in captured_conv.out

                # Test read-email command
                store = OfficeStore(db_path=office_db)
                emails = await store.get_emails(pid)
                assert len(emails) > 0
                first_email_id = str(emails[0].id)

                await read_email_command(first_email_id)
                captured_read = capsys.readouterr()
                assert "CORREO INTERNO DE LA SOFTWARE FACTORY" in captured_read.out
                assert first_email_id in captured_read.out
                assert "CUERPO DEL MENSAJE:" in captured_read.out
