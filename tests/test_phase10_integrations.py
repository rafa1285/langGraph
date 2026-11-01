"""Phase 10 tests: Retrospective hydration (backfill), Real Mail (Strato), GitHub, and Docker."""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.schemas.office import AgentEmailRecord
from app.schemas.routing import AgentID, DeliverableStatus
from app.services.backfill_service import ProjectBackfillService
from app.services.github_publisher import GitHubPublisherService
from app.services.local_deployer import LocalSandboxDeployer
from app.services.mail_service import MailService
from app.services.notion_mcp_service import LocalNotionMirrorAdapter
from app.services.office_store import OfficeStore
from app.services.real_mail_bridge import RealMailBridge
from cli import backfill_command, deploy_local_command, publish_git_command


@pytest.fixture
def test_env(tmp_path: Path) -> dict[str, Any]:
    """Provide isolated paths and configuration for Phase 10 integration tests."""
    workspaces = tmp_path / "workspaces"
    prompts = tmp_path / "prompts"
    office_db = tmp_path / "office_data.sqlite"
    workspaces.mkdir(parents=True, exist_ok=True)
    prompts.mkdir(parents=True, exist_ok=True)

    settings.WORKSPACES_DIR = str(workspaces)
    settings.PROMPTS_DIR = str(prompts)
    settings.OFFICE_DB_PATH = str(office_db)
    settings.REAL_MAIL_ENABLED = True
    settings.MAIL_USERNAME = "testbot@strato.de"
    settings.MAIL_PASSWORD = "supersecretpassword"
    settings.GITHUB_TOKEN = "ghp_mocktoken123456789"
    settings.GITHUB_USERNAME = "testuser"

    return {
        "workspaces": workspaces,
        "prompts": prompts,
        "office_db": office_db,
        "tmp_path": tmp_path,
    }


# =====================================================================
# 1. RealMailBridge Tests
# =====================================================================


def test_real_mail_bridge_rfc5322_generation(test_env: dict[str, Any]) -> None:
    """Test RFC 5322 MIME message construction, executive HTML body, and attachment."""
    bridge = RealMailBridge()

    # Create dummy deliverable markdown file
    deliverable = test_env["tmp_path"] / "01_agente_01_pm.md"
    deliverable.write_text("# Deliverable Content\nDetails here.", encoding="utf-8")

    record = AgentEmailRecord(
        project_id="proj_mail_test",
        step_number=1,
        sender="agente_01_pm@agentoffice.local",
        recipient="agente_02_architect@agentoffice.local",
        cc=[],
        subject="Especificación Pre-SDD Completa",
        body_summary="Se entrega especificación técnica inicial para el proyecto.",
        attached_deliverable_path=str(deliverable),
        priority="NORMAL",
    )

    msg = bridge.build_rfc5322_message(record, deliverable_path=deliverable)

    assert "agente_01_pm" in msg["From"] and "testbot@strato.de" in msg["From"]
    assert "agente_02_architect" in msg["To"] and "testbot@strato.de" in msg["To"]
    assert msg["Subject"] == "[proj_mail_test][NORMAL] Especificación Pre-SDD Completa"

    # Verify attachment
    attachments = list(msg.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "01_agente_01_pm.md"


@pytest.mark.asyncio
async def test_real_mail_bridge_sync_imap_and_smtp(test_env: dict[str, Any]) -> None:
    """Test IMAP folder hierarchy creation, append, and optional SMTP dispatch via mocks."""
    bridge = RealMailBridge()
    record = AgentEmailRecord(
        project_id="proj_mail_test",
        step_number=2,
        sender="agente_10_ciso@agentoffice.local",
        recipient="agente_04_fastapi@agentoffice.local",
        cc=[],
        subject="Bloqueo de seguridad",
        body_summary="Parchear SSRF inmediatamente",
        attached_deliverable_path="",
        priority="CRITICAL",
    )

    mock_imap = MagicMock()
    mock_imap.list.return_value = ("OK", [b'(\\HasNoChildren) "." "INBOX"'])
    mock_imap.create.return_value = ("OK", [b"Folder created"])
    mock_imap.append.return_value = ("OK", [b"Message appended"])

    mock_smtp = MagicMock()

    with (
        patch("imaplib.IMAP4_SSL", return_value=mock_imap),
        patch("smtplib.SMTP_SSL", return_value=mock_smtp),
    ):
        success = await bridge.sync_email_record(record, send_smtp=True)
        assert success is True

        # Verify IMAP calls
        mock_imap.login.assert_called_once_with("testbot@strato.de", "supersecretpassword")
        assert mock_imap.create.call_count >= 2
        mock_imap.append.assert_called_once()
        mock_imap.logout.assert_called_once()

        # Verify SMTP calls
        mock_smtp.login.assert_called_once_with("testbot@strato.de", "supersecretpassword")
        mock_smtp.send_message.assert_called_once()
        mock_smtp.quit.assert_called_once()


# =====================================================================
# 2. ProjectBackfillService Tests
# =====================================================================


@pytest.mark.asyncio
async def test_backfill_project_execution(test_env: dict[str, Any]) -> None:
    """Test scanning historical deliverables, rebuilding SQLite conversations, and emails."""
    workspaces = test_env["workspaces"]
    proj_dir = workspaces / "proj_backfill_demo"
    proj_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create step 1 (PM)
    md1 = """---
origen: "agente_01_pm"
destino_siguiente: "agente_02_architect"
estado_entregable: "PRE_SDD_LISTO"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---
# Pre-SDD
Especificación funcional completa.
"""
    (proj_dir / "01_agente_01_pm.md").write_text(md1, encoding="utf-8")

    # 2. Create step 20 (CISO rejection)
    md20 = """---
origen: "agente_10_ciso"
destino_siguiente: "agente_04_fastapi"
estado_entregable: "BLOQUEADO_POR_CIBERSEGURIDAD"
veredicto: "BLOQUEADO"
puntuacion: 42
culpable_detectado: "agente_04_fastapi"
---
# Dictamen CISO
Vulnerabilidad SSRF detectada.
"""
    (proj_dir / "20_agente_10_ciso.md").write_text(md20, encoding="utf-8")

    store = OfficeStore(db_path=test_env["office_db"])
    await store.init_db()
    mail_svc = MailService(store)
    mock_bridge = MagicMock(spec=RealMailBridge)
    mock_bridge.sync_email_record = MagicMock(return_value=asyncio.Future())
    mock_bridge.sync_email_record.return_value.set_result(True)

    notion_adapter = LocalNotionMirrorAdapter(workspaces_dir=workspaces)

    service = ProjectBackfillService(
        office_store=store,
        mail_service=mail_svc,
        workspaces_dir=workspaces,
        prompts_dir=test_env["prompts"],
        real_mail_bridge=mock_bridge,
        knowledge_sync=notion_adapter,
    )

    res = await service.backfill_project(
        project_id="proj_backfill_demo",
        sync_real_mail=True,
        sync_notion=True,
    )

    assert res["project_id"] == "proj_backfill_demo"
    assert res["total_deliverables_found"] == 2
    assert res["conversations_added"] == 2
    assert res["emails_added"] >= 2
    assert res["real_mail_synced"] >= 2
    assert res["notion_synced"] == 2

    # Check store persistence
    convs = await store.get_conversations("proj_backfill_demo")
    assert len(convs) == 2
    assert convs[0].agent_id == AgentID.AGENTE_01_PM
    assert convs[1].agent_id == AgentID.AGENTE_10_CISO
    assert convs[1].status == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
    assert convs[1].culprit == "agente_04_fastapi"

    # Check emails persistence and priority
    emails = await store.get_emails("proj_backfill_demo")
    assert len(emails) >= 2
    ciso_email = next(e for e in emails if e.step_number == 20)
    assert ciso_email.priority == "CRITICAL"
    assert "agente_04_fastapi" in ciso_email.recipient

    # Idempotency check: run backfill again
    res2 = await service.backfill_project("proj_backfill_demo", sync_real_mail=False)
    assert res2["conversations_added"] == 0
    assert res2["emails_added"] == 0


@pytest.mark.asyncio
async def test_backfill_non_existent_project(test_env: dict[str, Any]) -> None:
    """Test that attempting to backfill an unknown project raises FileNotFoundError."""
    service = ProjectBackfillService(workspaces_dir=test_env["workspaces"])
    with pytest.raises(FileNotFoundError):
        await service.backfill_project("proj_unknown_12345")


# =====================================================================
# 3. GitHubPublisherService Tests
# =====================================================================


@pytest.mark.asyncio
async def test_github_publisher_flow(test_env: dict[str, Any]) -> None:
    """Test GitHub repository creation and force push using mocked HTTP and git CLI."""
    workspaces = test_env["workspaces"]
    proj_dir = workspaces / "proj_git_test"
    build_dir = proj_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "main.py").write_text("print('hello')", encoding="utf-8")
    (build_dir / "Dockerfile").write_text("FROM python:3.12-slim", encoding="utf-8")

    publisher = GitHubPublisherService(
        github_token="ghp_mocksecrettoken",
        github_username="testuser",
        workspaces_dir=workspaces,
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://api.github.com/user":
            return httpx.Response(200, json={"login": "testuser"})
        if "/repos/testuser/awesome-repo" in url:
            return httpx.Response(404)
        if url == "https://api.github.com/user/repos":
            return httpx.Response(201, json={"html_url": "https://github.com/testuser/awesome-repo"})
        return httpx.Response(200)

    transport = httpx.MockTransport(mock_handler)

    with (
        patch("httpx.AsyncClient", return_value=httpx.AsyncClient(transport=transport)),
        patch.object(publisher, "_run_git_command", return_value="origin\nmain"),
    ):
        res = await publisher.publish_project_build(
            project_id="proj_git_test",
            repo_name="awesome-repo",
            private=True,
        )

        assert res["project_id"] == "proj_git_test"
        assert res["repo_name"] == "awesome-repo"
        assert res["repo_url"] == "https://github.com/testuser/awesome-repo"
        assert res["private"] is True
        assert res["pushed"] is True
        assert res["total_files"] == 2


@pytest.mark.asyncio
async def test_github_publisher_missing_token() -> None:
    """Test that missing GITHUB_TOKEN raises ValueError."""
    publisher = GitHubPublisherService(github_token="")
    with pytest.raises(ValueError, match="GITHUB_TOKEN no configurado"):
        await publisher.publish_project_build("p1", "r1")


# =====================================================================
# 4. LocalSandboxDeployer Tests
# =====================================================================


@pytest.mark.asyncio
async def test_local_deployer_stack_preparation_and_patching(test_env: dict[str, Any]) -> None:
    """Test applying CISO patches and generating docker-compose.local.yml."""
    workspaces = test_env["workspaces"]
    proj_dir = workspaces / "proj_deploy_test"
    build_dir = proj_dir / "build"
    adapters_dir = build_dir / "app" / "infrastructure" / "adapters"
    workers_dir = build_dir / "app" / "workers"
    adapters_dir.mkdir(parents=True, exist_ok=True)
    workers_dir.mkdir(parents=True, exist_ok=True)

    # Initial unpatched probe
    probe_file = adapters_dir / "raw_socket_smtp_probe.py"
    probe_file.write_text(
        "# vulnerable probe\nclass DistributedMxSemaphore:\n    pass\n",
        encoding="utf-8",
    )

    # Initial unpatched consumer
    consumer_file = workers_dir / "stream_consumer.py"
    consumer_code = """
class StreamConsumer:
    def _resolve_disk_path(self, raw_file_path: str) -> str:
        return raw_file_path
"""
    consumer_file.write_text(consumer_code, encoding="utf-8")

    # Create step 20 CISO markdown with patch
    ciso_md = """---
origen: "agente_10_ciso"
destino_siguiente: "agente_04_fastapi"
estado_entregable: "BLOQUEADO_POR_CIBERSEGURIDAD"
veredicto: "BLOQUEADO"
puntuacion: 42
culpable_detectado: "agente_04_fastapi"
---
# CISO Report
```python
# app/infrastructure/adapters/raw_socket_smtp_probe.py
# Hardened CISO implementation anti-SSRF
class DistributedMxSemaphore:
    \"\"\"Strict IP pinning and anti-SSRF.\"\"\"
    pass
```

```python
    def _resolve_disk_path(self, raw_file_path: str) -> str:
        # Hardened Anti-Path Traversal
        clean = raw_file_path.replace("\\\\", "/")
        return clean
```
"""
    (proj_dir / "20_agente_10_ciso.md").write_text(ciso_md, encoding="utf-8")

    deployer = LocalSandboxDeployer()
    res = await deployer.prepare_and_check_local_stack(
        project_id="proj_deploy_test",
        start_containers=False,
        workspaces_dir=workspaces,
    )

    assert res["project_id"] == "proj_deploy_test"
    assert res["ciso_patch_applied"] is True
    assert res["compose_file"] == "docker-compose.local.yml"
    assert (build_dir / "docker-compose.local.yml").exists()
    assert (build_dir / ".env.local").exists()
    assert res["ports"]["postgres"] == 15432
    assert res["ports"]["redis"] == 16379
    assert res["ports"]["engine_fastapi"] == 18000

    # Verify patched files
    updated_probe = probe_file.read_text(encoding="utf-8")
    assert "Hardened CISO implementation anti-SSRF" in updated_probe

    updated_consumer = consumer_file.read_text(encoding="utf-8")
    assert "Hardened Anti-Path Traversal" in updated_consumer


# =====================================================================
# 5. CLI Commands Tests
# =====================================================================


@pytest.mark.asyncio
async def test_cli_commands_execution(test_env: dict[str, Any]) -> None:
    """Test CLI commands: backfill, publish-git, and deploy-local."""
    workspaces = test_env["workspaces"]
    proj_dir = workspaces / "proj_cli_test"
    proj_dir.mkdir(parents=True, exist_ok=True)
    build_dir = proj_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    md = """---
origen: "agente_01_pm"
destino_siguiente: "agente_02_architect"
estado_entregable: "PRE_SDD_LISTO"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---
# Pre-SDD
"""
    (proj_dir / "01_agente_01_pm.md").write_text(md, encoding="utf-8")

    # Test backfill command
    await backfill_command("proj_cli_test", real_mail=False, notion=False)

    # Test deploy-local command
    await deploy_local_command("proj_cli_test", up=False)

    # Test publish-git command with mocked GitHub publisher
    with patch(
        "app.services.github_publisher.GitHubPublisherService.publish_project_build",
        return_value={
            "repo_url": "https://github.com/testuser/cli-repo",
            "total_files": 5,
        },
    ):
        await publish_git_command("proj_cli_test", "cli-repo", public=False)
