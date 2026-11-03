"""GitHub publisher service creating remote repositories and pushing materialized builds."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.code_materializer import CodeMaterializerService

logger = logging.getLogger(__name__)


class GitHubPublisherService:
    """Manages automatic repository creation and git push operations to GitHub."""

    def __init__(
        self,
        github_token: str | None = None,
        github_username: str | None = None,
        workspaces_dir: Path | str | None = None,
        materializer: CodeMaterializerService | None = None,
    ) -> None:
        """Initialize publisher with credentials, workspaces root, and materializer."""
        self.github_token = (
            github_token if github_token is not None else settings.GITHUB_TOKEN
        )
        self.github_username = (
            github_username if github_username is not None else settings.GITHUB_USERNAME
        )
        self.workspaces_dir = Path(workspaces_dir or settings.WORKSPACES_DIR)
        self.materializer = materializer or CodeMaterializerService(self.workspaces_dir)

    def _run_git_command(self, args: list[str], cwd: Path) -> str:
        """Execute git command synchronously inside target working directory."""
        res = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return res.stdout.strip()

    async def publish_project_build(
        self,
        project_id: str,
        repo_name: str,
        private: bool = True,
    ) -> dict[str, Any]:
        """Verify build materialization, create GitHub repo via API, and push main branch."""
        if not self.github_token:
            raise ValueError(
                "GITHUB_TOKEN no configurado en entorno o parámetros de servicio."
            )

        build_dir = self.workspaces_dir / project_id / "build"
        if not build_dir.exists() or not any(build_dir.iterdir()):
            logger.info("Directorio build/ ausente; materializando código de %s...", project_id)
            build_dir, _ = self.materializer.materialize_project(project_id)

        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        owner = self.github_username

        async with httpx.AsyncClient(timeout=30.0) as client:
            if not owner:
                user_res = await client.get("https://api.github.com/user", headers=headers)
                if user_res.status_code == 200:
                    owner = user_res.json().get("login")
                else:
                    owner = "user"

            # Check if repo exists
            repo_res = await client.get(
                f"https://api.github.com/repos/{owner}/{repo_name}",
                headers=headers,
            )

            if repo_res.status_code == 404:
                logger.info("Creando repositorio GitHub '%s/%s'...", owner, repo_name)
                create_payload = {
                    "name": repo_name,
                    "description": f"AgentOffice Automated Factory Build - {project_id}",
                    "private": private,
                    "auto_init": False,
                }
                create_res = await client.post(
                    "https://api.github.com/user/repos",
                    headers=headers,
                    json=create_payload,
                )
                if create_res.status_code not in (200, 201, 422):
                    raise RuntimeError(
                        f"Error de GitHub API al crear repositorio ({create_res.status_code}): "
                        f"{create_res.text}"
                    )
            elif repo_res.status_code != 200:
                logger.warning(
                    "Respuesta inesperada de GitHub API al verificar repo: %s",
                    repo_res.status_code,
                )

        # Configure local git repository inside build/
        if not (build_dir / ".git").exists():
            await asyncio.to_thread(self._run_git_command, ["git", "init"], build_dir)
            await asyncio.to_thread(self._run_git_command, ["git", "add", "."], build_dir)
            await asyncio.to_thread(
                self._run_git_command,
                [
                    "git",
                    "-c",
                    "user.name=AgentOffice Bot",
                    "-c",
                    "user.email=bot@agentoffice.local",
                    "commit",
                    "-m",
                    "chore: initial automated build from AgentOffice",
                ],
                build_dir,
            )

        remote_url = f"https://{self.github_token}@github.com/{owner}/{repo_name}.git"

        # Check existing remotes
        remotes = await asyncio.to_thread(
            self._run_git_command,
            ["git", "remote"],
            build_dir,
        )
        if "origin" in remotes.split():
            await asyncio.to_thread(
                self._run_git_command,
                ["git", "remote", "set-url", "origin", remote_url],
                build_dir,
            )
        else:
            await asyncio.to_thread(
                self._run_git_command,
                ["git", "remote", "add", "origin", remote_url],
                build_dir,
            )

        await asyncio.to_thread(
            self._run_git_command,
            ["git", "branch", "-M", "main"],
            build_dir,
        )
        await asyncio.to_thread(
            self._run_git_command,
            ["git", "push", "-u", "origin", "main", "--force"],
            build_dir,
        )

        total_files = len(
            [
                p
                for p in build_dir.rglob("*")
                if p.is_file() and not any(part.startswith(".git") for part in p.parts)
            ]
        )

        repo_url = f"https://github.com/{owner}/{repo_name}"
        logger.info(
            "Proyecto %s publicado exitosamente en GitHub: %s (%d archivos)",
            project_id,
            repo_url,
            total_files,
        )

        return {
            "project_id": project_id,
            "repo_name": repo_name,
            "repo_url": repo_url,
            "private": private,
            "total_files": total_files,
            "pushed": True,
        }
