"""Unit and integration tests for Phase 7: Code Materializer and Local Deployer."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

from app.services.code_materializer import CodeMaterializerService
from app.services.local_deployer import LocalSandboxDeployer
from app.services.mail_service import MailService
from app.services.office_store import OfficeStore
from cli import materialize_command


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory for test isolation."""
    ws = tmp_path / "workspaces"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def temp_office_store(tmp_path: Path) -> OfficeStore:
    """Create an isolated OfficeStore SQLite database for test verification."""
    db_file = tmp_path / "test_office.sqlite"
    return OfficeStore(db_path=db_file)


class TestCodeMaterializerService:
    """Test suite verifying code extraction heuristics, file ordering, and MANIFEST.json."""

    def test_extract_files_by_header(self) -> None:
        """Verify extraction when files are defined with markdown headers."""
        service = CodeMaterializerService()
        markdown = """
### Implementación de Código

#### `app/core/config.py`
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "TestApp"
```

#### 4.1. Archivo `docker-compose.prod.yml`
```yaml
services:
  web:
    image: nginx:alpine
```
"""
        extracted = service.extract_files_from_markdown(markdown)
        paths = [p for p, _ in extracted]
        assert "app/core/config.py" in paths
        assert "docker-compose.prod.yml" in paths

    def test_extract_files_by_fence_tag_and_comments(self) -> None:
        """Verify extraction through fence language tags and first-line comments."""
        service = CodeMaterializerService()
        markdown = """
```python:app/main.py
print("Hello World")
```

```python
# app/services/processor.py
def process():
    return True
```

```php
// app/Models/User.php
namespace App\\Models;
class User {}
```
"""
        extracted = service.extract_files_from_markdown(markdown)
        paths = [p for p, _ in extracted]
        assert "app/main.py" in paths
        assert "app/services/processor.py" in paths
        assert "app/Models/User.php" in paths

    def test_extract_files_by_php_namespace_and_class(self) -> None:
        """Verify automatic deduction of PHP file paths from namespace and class."""
        service = CodeMaterializerService()
        markdown = """
```php
<?php
declare(strict_types=1);

namespace App\\Domain\\Enums;

enum JobStatus: string {
    case QUEUED = 'QUEUED';
}
```
"""
        extracted = service.extract_files_from_markdown(markdown)
        assert len(extracted) == 1
        assert extracted[0][0] == "app/Domain/Enums/JobStatus.php"
        assert "enum JobStatus" in extracted[0][1]

    def test_reject_unsafe_and_invalid_paths(self) -> None:
        """Ensure path traversal and non-code candidates are strictly ignored."""
        service = CodeMaterializerService()
        assert not service.is_valid_file_path("../../etc/passwd")
        assert not service.is_valid_file_path("http://evil.com/shell.sh")
        assert not service.is_valid_file_path("redis.asyncio")
        assert not service.is_valid_file_path("invalid file with spaces.py")
        assert service.is_valid_file_path("app/core/config.py")
        assert service.is_valid_file_path("Dockerfile")
        assert service.is_valid_file_path(".env.example")

    def test_chronological_overwrite_and_manifest(self, temp_workspace: Path) -> None:
        """Verify later steps overwrite earlier patches and MANIFEST.json reflects final state."""
        project_id = f"proj_{uuid.uuid4().hex[:8]}"
        proj_dir = temp_workspace / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        # Step 03: FastAPI initial implementation (v1)
        step_03_content = """---
origen: "agente_04_fastapi"
destino_siguiente: "agente_06_qa_python"
---
#### `app/main.py`
```python
# app/main.py v1
app_version = "1.0.0"
```
#### `app/core/config.py`
```python
# app/core/config.py
DATABASE_URL = "sqlite:///:memory:"
```
"""
        (proj_dir / "03_agente_04_fastapi.md").write_text(step_03_content, encoding="utf-8")

        # Step 16: FastAPI refactored patch (v2)
        step_16_content = """---
origen: "agente_04_fastapi"
destino_siguiente: "agente_10_ciso"
---
#### `app/main.py`
```python
# app/main.py v2 - Security patched
app_version = "1.0.1-secure"
```
"""
        (proj_dir / "16_agente_04_fastapi.md").write_text(step_16_content, encoding="utf-8")

        # Step 19: DevOps Docker orchestration
        step_19_content = """---
origen: "agente_07_devops"
destino_siguiente: "agente_10_ciso"
---
#### 4.1. Archivo `docker-compose.prod.yml`
```yaml
services:
  app:
    image: python:3.12-slim
```
#### 4.2. Variables ` .env.example`
```ini
ENVIRONMENT=production
```
"""
        (proj_dir / "19_agente_07_devops.md").write_text(step_19_content, encoding="utf-8")

        service = CodeMaterializerService(workspaces_dir=temp_workspace)
        build_dir, manifest = service.materialize_project(project_id, init_git=True)

        assert build_dir.exists()
        # Verify app/main.py has v2 content from step 16
        main_content = (build_dir / "app/main.py").read_text(encoding="utf-8")
        assert "v2 - Security patched" in main_content
        assert 'app_version = "1.0.1-secure"' in main_content

        # Verify app/core/config.py persists from step 03
        config_content = (build_dir / "app/core/config.py").read_text(encoding="utf-8")
        assert "sqlite:///:memory:" in config_content

        # Verify DevOps files exist
        assert (build_dir / "docker-compose.prod.yml").exists()
        assert (build_dir / ".env.example").exists()

        # Verify MANIFEST.json structure
        manifest_file = build_dir / "MANIFEST.json"
        assert manifest_file.exists()
        loaded_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert loaded_manifest["project_id"] == project_id
        assert loaded_manifest["total_files"] == 4

        main_entry = next(f for f in loaded_manifest["files"] if f["path"] == "app/main.py")
        assert main_entry["author_agent"] == "agente_04_fastapi"
        assert main_entry["step_number"] == 16
        assert len(main_entry["sha256"]) == 64

        # Verify Git initialization
        assert (build_dir / ".git").exists()
        log_res = subprocess.run(
            ["git", "log", "-n", "1", "--oneline"],
            cwd=build_dir,
            capture_output=True,
            text=True,
        )
        assert "chore: initial automated build from AgentOffice" in log_res.stdout


class TestLocalSandboxDeployer:
    """Test suite verifying startup script generation, syntax validation, and email delivery."""

    def test_prepare_local_environment(self, tmp_path: Path) -> None:
        """Verify start_local.ps1 and start_local.sh are created with correct targets."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "docker-compose.prod.yml").write_text("services:\n  web:\n    image: nginx\n")

        deployer = LocalSandboxDeployer()
        res = deployer.prepare_local_environment(build_dir)

        assert res["compose_file"] == "docker-compose.prod.yml"
        assert "start_local.ps1" in res["scripts"]
        assert "start_local.sh" in res["scripts"]

        ps1_file = build_dir / "start_local.ps1"
        sh_file = build_dir / "start_local.sh"
        assert ps1_file.exists()
        assert sh_file.exists()

        ps1_text = ps1_file.read_text(encoding="utf-8")
        assert "docker compose -f $composeFile up -d --build" in ps1_text
        assert "docker compose -f \"$COMPOSE_FILE\" up -d --build" in sh_file.read_text(
            encoding="utf-8"
        )

    @pytest.mark.asyncio
    async def test_validate_compose_syntax_success(
        self,
        tmp_path: Path,
        temp_office_store: OfficeStore,
    ) -> None:
        """Verify compose syntax validation passes and reports via internal email."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compose_content = """services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: testdb
"""
        (build_dir / "docker-compose.prod.yml").write_text(compose_content, encoding="utf-8")

        mail_service = MailService(store=temp_office_store)
        deployer = LocalSandboxDeployer(mail_service=mail_service)

        is_valid = await deployer.validate_compose_syntax(
            build_path=build_dir,
            project_id="proj_test_deploy",
            mail_service=mail_service,
        )
        assert is_valid is True

        emails = await temp_office_store.get_emails(project_id="proj_test_deploy")
        assert len(emails) == 1
        email = emails[0]
        assert email.sender == "agente_07_devops@agentoffice.local"
        assert email.recipient == "ceo@agentoffice.local"
        assert "[DESPLIEGUE] [OK]" in email.subject
        assert "VALIDACIÓN SINTAXIS: APROBADA" in email.body_summary

    @pytest.mark.asyncio
    async def test_validate_compose_syntax_missing_file(
        self,
        tmp_path: Path,
        temp_office_store: OfficeStore,
    ) -> None:
        """Verify failure email sent when no compose file exists."""
        build_dir = tmp_path / "build_empty"
        build_dir.mkdir()

        mail_service = MailService(store=temp_office_store)
        deployer = LocalSandboxDeployer(mail_service=mail_service)

        is_valid = await deployer.validate_compose_syntax(
            build_path=build_dir,
            project_id="proj_missing_compose",
            mail_service=mail_service,
        )
        assert is_valid is False

        emails = await temp_office_store.get_emails(project_id="proj_missing_compose")
        assert len(emails) == 1
        email = emails[0]
        assert "[ERROR] Fallo de empaquetado" in email.subject
        assert email.priority == "CRITICAL"


class TestMaterializeIntegration:
    """Integration test suite executing materialize CLI commands and checking existing builds."""

    @pytest.mark.asyncio
    async def test_materialize_command_execution(
        self,
        temp_workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify materialize_command executes successfully end-to-end via CLI routine."""
        project_id = f"proj_{uuid.uuid4().hex[:8]}"
        proj_dir = temp_workspace / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        deliverable = """---
origen: "agente_07_devops"
destino_siguiente: "agente_10_ciso"
---
#### `docker-compose.prod.yml`
```yaml
services:
  app:
    image: nginx:alpine
```
#### `.env.example`
```ini
APP_ENV=local
```
"""
        (proj_dir / "12_agente_07_devops.md").write_text(deliverable, encoding="utf-8")

        monkeypatch.setattr("app.core.config.settings.WORKSPACES_DIR", str(temp_workspace))

        await materialize_command(project_id=project_id, skip_deployer=False)

        build_dir = proj_dir / "build"
        assert (build_dir / "docker-compose.prod.yml").exists()
        assert (build_dir / ".env.example").exists()
        assert (build_dir / "start_local.ps1").exists()
        assert (build_dir / "start_local.sh").exists()
        assert (build_dir / "MANIFEST.json").exists()

    def test_real_project_materialization_artifacts(self) -> None:
        """Verify real project proj_88c9fd46 contains valid build deliverables and manifest."""
        real_build = Path("workspaces/proj_88c9fd46/build")
        if not real_build.exists():
            pytest.skip("workspaces/proj_88c9fd46 no presente en el entorno.")

        manifest_file = real_build / "MANIFEST.json"
        assert manifest_file.exists()

        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert data["project_id"] == "proj_88c9fd46"
        assert data["total_files"] >= 70

        assert (real_build / "docker-compose.prod.yml").exists()
        assert (real_build / "start_local.ps1").exists()
        assert (real_build / "start_local.sh").exists()
        assert (real_build / ".git").exists()
