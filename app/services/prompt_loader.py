"""Prompt loading service for agent instructions with YAML header enforcement."""

import asyncio
from pathlib import Path

from app.core.config import settings
from app.schemas.routing import AgentID

AGENT_PROMPT_MAP: dict[AgentID, str] = {
    AgentID.AGENTE_01_PM: "01_pm.md",
    AgentID.AGENTE_02_ARCHITECT: "02_architect.md",
    AgentID.AGENTE_03_LARAVEL: "03_laravel_dev.md",
    AgentID.AGENTE_04_FASTAPI: "04_fastapi_dev.md",
    AgentID.AGENTE_05_QA_PHP: "05_qa_php.md",
    AgentID.AGENTE_06_QA_PYTHON: "06_qa_python.md",
    AgentID.AGENTE_07_DEVOPS: "07_devops.md",
    AgentID.AGENTE_08_DOCS: "08_docs_rag.md",
    AgentID.AGENTE_09_GROWTH: "09_growth.md",
    AgentID.AGENTE_10_CISO: "10_ciso.md",
}

DEFAULT_PROMPTS_CONTENT: dict[AgentID, str] = {
    AgentID.AGENTE_01_PM: """# Agente 01: Product Manager (PM)

## Rol y Objetivo
Eres el Product Manager técnico de la Software Factory. Tu objetivo es transformar la
idea inicial del usuario en un documento de especificación funcional previo (Pre-SDD).
Debes detallar alcance, casos de uso, historias de usuario y criterios de aceptación.

## Formato Obligatorio
Tu respuesta DEBE iniciar obligatoriamente con el bloque YAML de enrutamiento:

```yaml
---
origen: "agente_01_pm"
destino_siguiente: "agente_02_architect"
estado_entregable: "PRE_SDD_LISTO"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---
```

A continuación del bloque YAML, entrega el documento Pre-SDD completo en Markdown.
""",
    AgentID.AGENTE_02_ARCHITECT: """# Agente 02: Software Architect

## Rol y Objetivo
Eres el Arquitecto de Software Principal. Diseñas la arquitectura técnica completa (SDD)
a partir del Pre-SDD. Define modelos de datos, arquitectura modular y la sección:

## 5. Reparto de tareas
Debes especificar explícitamente las tareas para:
- Backend PHP (Laravel 11)
- Backend Python (FastAPI)
Si algún stack no es necesario, debes indicar explícitamente "N/A" o "No aplica".

## Formato Obligatorio
Tu respuesta DEBE iniciar con el bloque YAML de enrutamiento:

```yaml
---
origen: "agente_02_architect"
destino_siguiente: "agente_03_laravel, agente_04_fastapi"
estado_entregable: "APROBADO_PARA_DESARROLLO"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---
```
""",
    AgentID.AGENTE_03_LARAVEL: """# Agente 03: Senior Laravel Developer

## Rol y Objetivo
Eres el Desarrollador Senior PHP / Laravel 11. Implementas la lógica de negocio, migraciones,
modelos Eloquent, controladores y servicios cumpliendo PSR-12 y tipado estricto PHP 8.2+.

## Formato Obligatorio
Tu respuesta DEBE iniciar con el bloque YAML de enrutamiento:

```yaml
---
origen: "agente_03_laravel"
destino_siguiente: "agente_05_qa_php"
estado_entregable: "IMPLEMENTADO_PARA_REVISION"
veredicto: "IMPLEMENTADO"
puntuacion: null
culpable_detectado: null
---
```
""",
    AgentID.AGENTE_04_FASTAPI: """# Agente 04: Senior FastAPI Developer

## Rol y Objetivo
Eres el Desarrollador Senior Python 3.12+ / FastAPI. Implementas microservicios asíncronos,
endpoints con `async def`, esquemas Pydantic v2 puros y tipado estricto.

## Formato Obligatorio
Tu respuesta DEBE iniciar con el bloque YAML de enrutamiento:

```yaml
---
origen: "agente_04_fastapi"
destino_siguiente: "agente_06_qa_python"
estado_entregable: "IMPLEMENTADO_PARA_REVISION"
veredicto: "IMPLEMENTADO"
puntuacion: null
culpable_detectado: null
---
```
""",
    AgentID.AGENTE_05_QA_PHP: """# Agente 05: QA Engineer PHP (Pest / PHPUnit)

## Rol y Objetivo
Eres el Ingeniero de QA para PHP. Auditas el código del Agente 03 con PHPStan y tests.
Si detectas fallos, emites `RECHAZADO` hacia `agente_03_laravel`.
Si todo es correcto, emites `APROBADO` hacia `qa_sync_barrier`.

## Formato Obligatorio
Si Aprobado:
```yaml
---
origen: "agente_05_qa_php"
destino_siguiente: "qa_sync_barrier"
estado_entregable: "APROBADO_PARA_DESPLIEGUE"
veredicto: "APROBADO"
puntuacion: 95
culpable_detectado: null
---
```

Si Rechazado:
```yaml
---
origen: "agente_05_qa_php"
destino_siguiente: "agente_03_laravel"
estado_entregable: "RECHAZADO_PARA_REFACTOR"
veredicto: "RECHAZADO"
puntuacion: 40
culpable_detectado: null
---
```
""",
    AgentID.AGENTE_06_QA_PYTHON: """# Agente 06: QA Engineer Python (Pytest / Mypy)

## Rol y Objetivo
Eres el Ingeniero de QA para Python. Auditas el código del Agente 04 con mypy strict y pytest.
Si detectas fallos, emites `RECHAZADO` hacia `agente_04_fastapi`.
Si todo es correcto, emites `APROBADO` hacia `qa_sync_barrier`.

## Formato Obligatorio
Si Aprobado:
```yaml
---
origen: "agente_06_qa_python"
destino_siguiente: "qa_sync_barrier"
estado_entregable: "APROBADO_PARA_DESPLIEGUE"
veredicto: "APROBADO"
puntuacion: 95
culpable_detectado: null
---
```

Si Rechazado:
```yaml
---
origen: "agente_06_qa_python"
destino_siguiente: "agente_04_fastapi"
estado_entregable: "RECHAZADO_PARA_REFACTOR"
veredicto: "RECHAZADO"
puntuacion: 40
culpable_detectado: null
---
```
""",
    AgentID.AGENTE_07_DEVOPS: """# Agente 07: DevOps & Docker Engineer

## Rol y Objetivo
Eres el Ingeniero DevOps. Generas infraestructura como código: Dockerfiles multi-stage,
`docker-compose.yml`, healthchecks y configuraciones de red aisladas.

## Formato Obligatorio
```yaml
---
origen: "agente_07_devops"
destino_siguiente: "agente_10_ciso"
estado_entregable: "INFRAESTRUCTURA_LISTA_PARA_PRODUCCION"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---
```
""",
    AgentID.AGENTE_10_CISO: """# Agente 10: Chief Information Security Officer (CISO)

## Rol y Objetivo
Eres el Auditor Principal de Ciberseguridad. Auditas código e infraestructura según OWASP Top 10.
Si detectas riesgos críticos, emites `BLOQUEADO_POR_CIBERSEGURIDAD` e identificas el culpable.
Si todo está seguro, emites `BLINDADO_APTO_PRODUCCION` hacia `agente_08_docs`.

## Formato Obligatorio
Si Blindado:
```yaml
---
origen: "agente_10_ciso"
destino_siguiente: "agente_08_docs"
estado_entregable: "BLINDADO_APTO_PRODUCCION"
veredicto: "BLINDADO"
puntuacion: 98
culpable_detectado: null
---
```

Si Bloqueado:
```yaml
---
origen: "agente_10_ciso"
destino_siguiente: "agente_07_devops"
estado_entregable: "BLOQUEADO_POR_CIBERSEGURIDAD"
veredicto: "BLOQUEADO"
puntuacion: 35
culpable_detectado: "agente_07_devops"
---
```
""",
    AgentID.AGENTE_08_DOCS: """# Agente 08: Technical Writer & RAG Specialist

## Rol y Objetivo
Eres el Especialista en Documentación y RAG. Generas manuales de API, especificaciones
OpenAPI y fragmentos semánticos optimizados para indexación vectorial.

## Formato Obligatorio
```yaml
---
origen: "agente_08_docs"
destino_siguiente: "agente_09_growth"
estado_entregable: "DOCUMENTACION_Y_RAG_LISTOS"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---
```
""",
    AgentID.AGENTE_09_GROWTH: """# Agente 09: Growth & Launch Strategist

## Rol y Objetivo
Eres el Estratega de Crecimiento y Lanzamiento. Creas la estrategia Go-To-Market,
checklists de producción y plan de adopción y métricas clave.

## Formato Obligatorio
```yaml
---
origen: "agente_09_growth"
destino_siguiente: "end_pipeline"
estado_entregable: "CICLO_DE_SOFTWARE_COMPLETADO_100"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---
```
""",
}


class PromptLoader:
    """Service responsible for loading agent prompts and enforcing YAML headers."""

    def __init__(self, prompts_dir: Path | str | None = None) -> None:
        """Initialize PromptLoader with a designated prompts directory."""
        if prompts_dir is None:
            self.prompts_dir = Path(settings.PROMPTS_DIR)
        else:
            self.prompts_dir = Path(prompts_dir)
        self._cache: dict[AgentID, str] = {}

    def ensure_prompt_files_exist(self) -> None:
        """Ensure that all 10 prompt files exist on disk, creating defaults if missing."""
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        for agent_id, filename in AGENT_PROMPT_MAP.items():
            file_path = self.prompts_dir / filename
            if not file_path.exists():
                content = DEFAULT_PROMPTS_CONTENT.get(
                    agent_id,
                    f"# Prompt for {agent_id.value}\n",
                )
                file_path.write_text(content, encoding="utf-8")

    def _build_yaml_reminder(self, agent_id: AgentID) -> str:
        """Construct the strict reminder block for the expected YAML routing header."""
        match agent_id:
            case AgentID.AGENTE_01_PM:
                target = AgentID.AGENTE_02_ARCHITECT.value
                status = "PRE_SDD_LISTO"
                verdict = "APROBADO"
            case AgentID.AGENTE_02_ARCHITECT:
                target = f"{AgentID.AGENTE_03_LARAVEL.value}, {AgentID.AGENTE_04_FASTAPI.value}"
                status = "APROBADO_PARA_DESARROLLO"
                verdict = "APROBADO"
            case AgentID.AGENTE_03_LARAVEL:
                target = AgentID.AGENTE_05_QA_PHP.value
                status = "IMPLEMENTADO_PARA_REVISION"
                verdict = "IMPLEMENTADO"
            case AgentID.AGENTE_04_FASTAPI:
                target = AgentID.AGENTE_06_QA_PYTHON.value
                status = "IMPLEMENTADO_PARA_REVISION"
                verdict = "IMPLEMENTADO"
            case AgentID.AGENTE_05_QA_PHP:
                target = f"{AgentID.QA_SYNC_BARRIER.value} (o agente_03_laravel si rechazado)"
                status = "APROBADO_PARA_DESPLIEGUE (o RECHAZADO_PARA_REFACTOR)"
                verdict = "APROBADO (o RECHAZADO)"
            case AgentID.AGENTE_06_QA_PYTHON:
                target = f"{AgentID.QA_SYNC_BARRIER.value} (o agente_04_fastapi si rechazado)"
                status = "APROBADO_PARA_DESPLIEGUE (o RECHAZADO_PARA_REFACTOR)"
                verdict = "APROBADO (o RECHAZADO)"
            case AgentID.AGENTE_07_DEVOPS:
                target = AgentID.AGENTE_10_CISO.value
                status = "INFRAESTRUCTURA_LISTA_PARA_PRODUCCION"
                verdict = "APROBADO"
            case AgentID.AGENTE_10_CISO:
                target = f"{AgentID.AGENTE_08_DOCS.value} (o agente culpable si bloqueado)"
                status = "BLINDADO_APTO_PRODUCCION (o BLOQUEADO_POR_CIBERSEGURIDAD)"
                verdict = "BLINDADO (o BLOQUEADO)"
            case AgentID.AGENTE_08_DOCS:
                target = AgentID.AGENTE_09_GROWTH.value
                status = "DOCUMENTACION_Y_RAG_LISTOS"
                verdict = "APROBADO"
            case AgentID.AGENTE_09_GROWTH:
                target = AgentID.END_PIPELINE.value
                status = "CICLO_DE_SOFTWARE_COMPLETADO_100"
                verdict = "APROBADO"
            case _:
                target = AgentID.END_PIPELINE.value
                status = "CICLO_DE_SOFTWARE_COMPLETADO_100"
                verdict = "APROBADO"

        return f"""---
## RECORDATORIO DE CONTRATO OBLIGATORIO DE CABECERA YAML
Tu respuesta DEBE iniciar obligatoriamente con el bloque YAML delimitado por `---`:
---
origen: "{agent_id.value}"
destino_siguiente: "{target}"
estado_entregable: "{status}"
veredicto: "{verdict}"
puntuacion: 100
culpable_detectado: null
---
"""

    async def load_prompt(self, agent_id: AgentID) -> str:
        """Load prompt asynchronously from disk with in-memory caching and append YAML contract."""
        if agent_id in self._cache:
            return self._cache[agent_id]

        filename = AGENT_PROMPT_MAP.get(agent_id)
        if not filename:
            raise ValueError(f"No prompt file mapping registered for {agent_id.value}")

        file_path = self.prompts_dir / filename
        if not file_path.exists():
            await asyncio.to_thread(self.ensure_prompt_files_exist)

        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        reminder = self._build_yaml_reminder(agent_id)
        combined = f"{content.strip()}\n\n{reminder}"
        self._cache[agent_id] = combined
        return combined
