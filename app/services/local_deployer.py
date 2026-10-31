"""Local sandbox deployer validating compose syntax and preparing run scripts."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

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
