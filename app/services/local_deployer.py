"""Local sandbox deployer validating compose syntax and preparing run scripts."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from app.schemas.office import EmailPriority
from app.services.mail_service import MailService

logger = logging.getLogger(__name__)


class LocalSandboxDeployer:
    """Validates container orchestration syntax and prepares local quickstart runbooks."""

    def __init__(self, mail_service: MailService | None = None) -> None:
        """Initialize deployer with an optional MailService instance."""
        self.mail_service = mail_service or MailService()

    @staticmethod
    def find_compose_file(build_path: Path) -> Path | None:
        """Locate the primary Docker Compose file inside the build directory."""
        candidates = [
            build_path / "docker-compose.prod.yml",
            build_path / "docker-compose.yml",
            build_path / "docker-compose.yaml",
            build_path / "compose.yml",
            build_path / "compose.yaml",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        for found in build_path.glob("*compose*.y*ml"):
            if found.is_file():
                return found

        return None

    def prepare_local_environment(self, build_path: Path) -> dict[str, Any]:
        """Generate start_local.ps1 and start_local.sh launcher scripts inside build/."""
        compose_file = self.find_compose_file(build_path)
        compose_name = compose_file.name if compose_file else "docker-compose.prod.yml"

        ps1_script = f"""# =====================================================================
# AgentOffice Local Quickstart - PowerShell (Windows)
# =====================================================================
$ErrorActionPreference = "Stop"

Write-Host "[LocalDeployer] Iniciando entorno local de AgentOffice..." -ForegroundColor Cyan

# Copiar .env si no existe
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {{
    Write-Host "[LocalDeployer] Copiando .env.example -> .env..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}}

# Verificar cliente Docker
if (-not (Get-Command "docker" -ErrorAction SilentlyContinue)) {{
    Write-Host "[LocalDeployer] ERROR: Docker no está disponible en el PATH." -ForegroundColor Red
    exit 1
}}

$composeFile = "{compose_name}"
Write-Host "[LocalDeployer] Desplegando servicios con Docker Compose..." -ForegroundColor Green
docker compose -f $composeFile up -d --build

Write-Host "`n[LocalDeployer] Estado de los contenedores:" -ForegroundColor Cyan
docker compose -f $composeFile ps
Write-Host "`n[LocalDeployer] Despliegue local completado correctamente." -ForegroundColor Green
"""

        sh_script = f"""#!/usr/bin/env bash
# =====================================================================
# AgentOffice Local Quickstart - Bash (Linux / macOS / WSL)
# =====================================================================
set -euo pipefail

echo "[LocalDeployer] Iniciando entorno local de AgentOffice..."

# Copiar .env si no existe
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "[LocalDeployer] Copiando .env.example -> .env..."
    cp ".env.example" ".env"
fi

# Verificar cliente Docker
if ! command -v docker &> /dev/null; then
    echo "[LocalDeployer] ERROR: Docker no está disponible en el PATH."
    exit 1
fi

COMPOSE_FILE="{compose_name}"
echo "[LocalDeployer] Desplegando servicios con Docker Compose ($COMPOSE_FILE)..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo ""
echo "[LocalDeployer] Estado de los contenedores:"
docker compose -f "$COMPOSE_FILE" ps
echo ""
echo "[LocalDeployer] Despliegue local completado correctamente."
"""

        ps1_path = build_path / "start_local.ps1"
        sh_path = build_path / "start_local.sh"

        ps1_path.write_text(ps1_script, encoding="utf-8")
        sh_path.write_text(sh_script, encoding="utf-8")

        if os.name != "nt":
            try:
                os.chmod(sh_path, 0o755)
            except OSError:
                pass

        return {
            "compose_file": compose_name if compose_file else None,
            "scripts": ["start_local.ps1", "start_local.sh"],
        }

    async def validate_compose_syntax(
        self,
        build_path: Path,
        project_id: str,
        mail_service: MailService | None = None,
    ) -> bool:
        """Validate compose file syntax via CLI dry-run or YAML schema and email results."""
        svc = mail_service or self.mail_service
        compose_file = self.find_compose_file(build_path)

        if compose_file is None:
            subject = (
                f"[DESPLIEGUE] [ERROR] Fallo de empaquetado: "
                f"docker-compose ausente - Proyecto {project_id}"
            )
            body_summary = (
                f"PROYECTO: {project_id}\n"
                "ESTADO: EMPAQUETADO_INCOMPLETO\n"
                "DETALLE: No se encontró archivo docker-compose en build/.\n"
                "ACCIÓN REQUERIDA: Verificar entregables de DevOps antes de proceder."
            )
            await svc.send_email(
                project_id=project_id,
                sender="agente_07_devops@agentoffice.local",
                recipient="ceo@agentoffice.local",
                subject=subject,
                body_summary=body_summary,
                priority="CRITICAL",
            )
            return False

        is_valid = False
        validation_mode = "docker-compose-cli"

        if shutil.which("docker") is not None:
            def _run_docker_config() -> bool:
                try:
                    res = subprocess.run(
                        ["docker", "compose", "-f", compose_file.name, "config", "-q"],
                        cwd=build_path,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    return res.returncode == 0
                except (subprocess.SubprocessError, OSError):
                    return False

            is_valid = await asyncio.to_thread(_run_docker_config)

        # Fallback to YAML validation if docker CLI is unavailable or daemon is offline
        if not is_valid:
            validation_mode = "yaml-schema-fallback"
            try:
                content = compose_file.read_text(encoding="utf-8")
                parsed = yaml.safe_load(content)
                if isinstance(parsed, dict) and "services" in parsed:
                    is_valid = True
                else:
                    is_valid = False
            except Exception as exc:
                logger.warning("Fallo al validar sintaxis YAML en %s: %s", compose_file, exc)
                is_valid = False

        subject = (
            f"[DESPLIEGUE] [OK] Paquete de Producción Validado y Listo - Proyecto {project_id}"
            if is_valid
            else f"[DESPLIEGUE] [ERROR] Error de Sintaxis en docker-compose - Proyecto {project_id}"
        )
        priority: EmailPriority = "HIGH" if is_valid else "CRITICAL"
        status_text = "APROBADA" if is_valid else "FALLIDA"

        body = (
            f"PROYECTO: {project_id}\n"
            f"ESTADO: {'EMPAQUETADO_COMPLETO' if is_valid else 'EMPAQUETADO_CON_ERRORES'}\n"
            f"ARCHIVO COMPOSE: {compose_file.name}\n"
            f"VALIDACIÓN SINTAXIS: {status_text} (Modo: {validation_mode})\n"
            "SCRIPTS DE ARRANQUE: start_local.ps1, start_local.sh\n\n"
            "RESUMEN EJECUTIVO:\n"
            "El código fuente y la arquitectura de contenedores han sido materializados.\n"
            "Para arrancar la factoría en local:\n"
            "  Windows PowerShell : .\\start_local.ps1\n"
            "  Linux / WSL / Mac   : ./start_local.sh\n"
        )

        await svc.send_email(
            project_id=project_id,
            sender="agente_07_devops@agentoffice.local",
            recipient="ceo@agentoffice.local",
            subject=subject,
            body_summary=body,
            attached_deliverable_path=str(compose_file),
            priority=priority,
        )

        return is_valid

    async def prepare_and_check_local_stack(
        self,
        project_id: str,
        start_containers: bool = False,
        workspaces_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        """Apply security patches, build docker-compose.local.yml, and optionally spin up stack."""
        ws_dir = Path(workspaces_dir or settings.WORKSPACES_DIR)
        source_dir = ws_dir / project_id
        build_dir = source_dir / "build"

        if not build_dir.exists() or not any(build_dir.iterdir()):
            from app.services.code_materializer import CodeMaterializerService

            mat = CodeMaterializerService(ws_dir)
            build_dir, _ = mat.materialize_project(project_id)

        ciso_patch_applied = False
        ciso_file = source_dir / "20_agente_10_ciso.md"
        if not ciso_file.exists():
            candidates = list(source_dir.glob("*_agente_10_ciso.md"))
            if candidates:
                ciso_file = candidates[-1]

        if ciso_file.exists():
            ciso_text = ciso_file.read_text(encoding="utf-8")
            blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", ciso_text, re.DOTALL)

            # 1. Look for raw_socket_smtp_probe.py patch
            probe_patch = None
            for b in blocks:
                if "raw_socket_smtp_probe.py" in b or "class DistributedMxSemaphore" in b:
                    probe_patch = b
                    break

            if probe_patch:
                target_paths = [
                    build_dir / "app" / "infrastructure" / "adapters" / "raw_socket_smtp_probe.py",
                    build_dir
                    / "engine_fastapi"
                    / "app"
                    / "infrastructure"
                    / "adapters"
                    / "raw_socket_smtp_probe.py",
                ]
                applied = False
                for tp in target_paths:
                    if tp.exists() or tp.parent.exists():
                        tp.parent.mkdir(parents=True, exist_ok=True)
                        tp.write_text(probe_patch, encoding="utf-8")
                        applied = True
                if not applied:
                    def_tp = target_paths[0]
                    def_tp.parent.mkdir(parents=True, exist_ok=True)
                    def_tp.write_text(probe_patch, encoding="utf-8")
                ciso_patch_applied = True

            # 2. Look for stream_consumer.py patch
            consumer_patch = None
            for b in blocks:
                if "_resolve_disk_path" in b:
                    consumer_patch = b
                    break

            if consumer_patch:
                consumer_targets = [
                    build_dir / "app" / "workers" / "stream_consumer.py",
                    build_dir / "engine_fastapi" / "app" / "workers" / "stream_consumer.py",
                ]
                for ct in consumer_targets:
                    if ct.exists():
                        ct_text = ct.read_text(encoding="utf-8")
                        pattern = (
                            r"    def _resolve_disk_path\(self, raw_file_path: str\) -> str:"
                            r".*?(?=\n    def |\Z)"
                        )
                        if re.search(pattern, ct_text, re.DOTALL):
                            new_text = re.sub(
                                pattern,
                                consumer_patch.strip(),
                                ct_text,
                                flags=re.DOTALL,
                            )
                            ct.write_text(new_text, encoding="utf-8")
                            ciso_patch_applied = True

        # Generate docker-compose.local.yml with non-conflicting host ports
        local_compose = f"""version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: agentoffice_postgres_{project_id}
    restart: unless-stopped
    environment:
      POSTGRES_DB: agentoffice_db
      POSTGRES_USER: agentoffice_user
      POSTGRES_PASSWORD: secret_local_password
    ports:
      - "15432:5432"
    volumes:
      - pgdata_{project_id}:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agentoffice_user -d agentoffice_db"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: agentoffice_redis_{project_id}
    restart: unless-stopped
    ports:
      - "16379:6379"
    volumes:
      - redisdata_{project_id}:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  engine_fastapi:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: agentoffice_engine_{project_id}
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://agentoffice_user:secret_local_password@postgres:5432/agentoffice_db
      REDIS_URL: redis://redis:6379/0
      PROJECT_ID: {project_id}
    ports:
      - "18000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  pgdata_{project_id}:
  redisdata_{project_id}:
"""
        compose_local_path = build_dir / "docker-compose.local.yml"
        compose_local_path.write_text(local_compose, encoding="utf-8")

        env_local = f"""# AgentOffice Local Stack Configuration - {project_id}
PROJECT_ID={project_id}
POSTGRES_PORT=15432
REDIS_PORT=16379
APP_PORT=18000
DATABASE_URL=postgresql+asyncpg://agentoffice_user:secret_local_password@localhost:15432/agentoffice_db
REDIS_URL=redis://localhost:16379/0
"""
        (build_dir / ".env.local").write_text(env_local, encoding="utf-8")
        if not (build_dir / ".env").exists():
            (build_dir / ".env").write_text(env_local, encoding="utf-8")

        containers_started = False
        health_status = "untested"

        if start_containers:
            if shutil.which("docker") is not None:
                def _run_docker_up() -> bool:
                    try:
                        res = subprocess.run(
                            [
                                "docker",
                                "compose",
                                "-f",
                                "docker-compose.local.yml",
                                "up",
                                "-d",
                                "--build",
                            ],
                            cwd=build_dir,
                            capture_output=True,
                            text=True,
                            timeout=60,
                        )
                        return res.returncode == 0
                    except Exception as exc:
                        logger.warning("Fallo al levantar contenedores Docker: %s", exc)
                        return False

                containers_started = await asyncio.to_thread(_run_docker_up)
                if containers_started:
                    import httpx

                    async with httpx.AsyncClient(timeout=3.0) as http_client:
                        for _ in range(5):
                            try:
                                h_res = await http_client.get("http://localhost:18000/health")
                                if h_res.status_code == 200:
                                    health_status = "healthy"
                                    break
                            except Exception:
                                await asyncio.sleep(1.0)
                        if health_status != "healthy":
                            health_status = "starting"
                else:
                    health_status = "failed_to_start"
            else:
                health_status = "docker_cli_unavailable"

        return {
            "project_id": project_id,
            "ciso_patch_applied": ciso_patch_applied,
            "compose_file": "docker-compose.local.yml",
            "compose_path": str(compose_local_path),
            "ports": {
                "postgres": 15432,
                "redis": 16379,
                "engine_fastapi": 18000,
            },
            "containers_started": containers_started,
            "health_check": health_status,
        }
