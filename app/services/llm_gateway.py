"""LLM Gateway service providing protocol, Gemini client, and testing mock."""

import asyncio
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings
from app.schemas.routing import AgentID


class LLMGatewayProtocol(Protocol):
    """Protocol interface defining operations for language model gateways."""

    async def invoke_agent(
        self,
        agent_id: AgentID,
        system_prompt: str,
        user_payload: str,
    ) -> str:
        """Invoke an agent with prompts and payload, returning the raw response string."""
        ...


class GeminiLLMGateway:
    """Production LLM Gateway using Google Gemini via ChatGoogleGenerativeAI."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the Gemini client with an optional custom API key."""
        self.api_key = api_key or settings.GEMINI_API_KEY

    async def invoke_agent(
        self,
        agent_id: AgentID,
        system_prompt: str,
        user_payload: str,
    ) -> str:
        """Invoke Gemini with rate limiting, per-agent config, and exponential retry on quota."""
        if settings.RATE_LIMIT_DELAY_SECONDS > 0:
            await asyncio.sleep(settings.RATE_LIMIT_DELAY_SECONDS)

        model_name = settings.get_agent_model(agent_id)
        temperature = settings.get_agent_temperature(agent_id)

        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=self.api_key,
            temperature=temperature,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_payload),
        ]

        max_retries = 3
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                response = await llm.ainvoke(messages)
                if isinstance(response.content, str):
                    return response.content
                if isinstance(response.content, list):
                    parts: list[str] = []
                    for part in response.content:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict) and "text" in part:
                            parts.append(str(part["text"]))
                        else:
                            parts.append(str(part))
                    return "".join(parts)
                return str(response.content)
            except Exception as e:
                err_str = str(e).lower()
                is_quota = (
                    "429" in err_str
                    or "resourceexhausted" in err_str
                    or "quota" in err_str
                    or "rate limit" in err_str
                )
                if is_quota and attempt < max_retries - 1:
                    backoff = 2 ** (attempt + 1)
                    await asyncio.sleep(backoff)
                    last_error = e
                else:
                    raise e

        if last_error:
            raise last_error
        raise RuntimeError("Unexpected failure during Gemini invocation.")


class MockLLMGateway:
    """Mock LLM Gateway simulating deterministic responses for all 10 agents."""

    def __init__(
        self,
        fail_qa_php_once: bool = False,
        fail_qa_python_once: bool = False,
        always_fail_qa_php: bool = False,
        always_fail_qa_python: bool = False,
        fail_ciso_target: AgentID | None = None,
        fail_ciso_once: bool = False,
        sdd_requires_php: bool = True,
        sdd_requires_python: bool = True,
        qa_php_failures_before_pass: int = 0,
        qa_python_failures_before_pass: int = 0,
        ciso_failures_sequence: list[AgentID] | None = None,
    ) -> None:
        """Initialize mock gateway with scenario control flags."""
        self.fail_qa_php_once = fail_qa_php_once
        self.fail_qa_python_once = fail_qa_python_once
        self.always_fail_qa_php = always_fail_qa_php
        self.always_fail_qa_python = always_fail_qa_python
        self.fail_ciso_target = fail_ciso_target
        self.fail_ciso_once = fail_ciso_once
        self.sdd_requires_php = sdd_requires_php
        self.sdd_requires_python = sdd_requires_python
        self.qa_php_failures_before_pass = qa_php_failures_before_pass
        self.qa_python_failures_before_pass = qa_python_failures_before_pass
        self.ciso_failures_sequence: list[AgentID] = (
            list(ciso_failures_sequence) if ciso_failures_sequence is not None else []
        )

        self.qa_php_calls: int = 0
        self.qa_python_calls: int = 0
        self.ciso_calls: int = 0
        self.invocations: list[tuple[AgentID, str, str]] = []
        self.invocation_counts: dict[AgentID, int] = dict.fromkeys(AgentID, 0)

    async def invoke_agent(
        self,
        agent_id: AgentID,
        system_prompt: str,
        user_payload: str,
    ) -> str:
        """Return simulated realistic response matching agent contract and test conditions."""
        self.invocations.append((agent_id, system_prompt, user_payload))
        self.invocation_counts[agent_id] = self.invocation_counts.get(agent_id, 0) + 1

        match agent_id:
            case AgentID.AGENTE_01_PM:
                return f"""---
origen: "agente_01_pm"
destino_siguiente: "agente_02_architect"
estado_entregable: "PRE_SDD_LISTO"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---

# Pre-SDD Funcional
Especificación generada a partir de: {user_payload}
"""
            case AgentID.AGENTE_02_ARCHITECT:
                php_line = (
                    "Controladores y modelos Eloquent."
                    if self.sdd_requires_php
                    else "N/A"
                )
                python_line = (
                    "Microservicios REST con FastAPI."
                    if self.sdd_requires_python
                    else "No aplica"
                )
                return f"""---
origen: "agente_02_architect"
destino_siguiente: "agente_03_laravel, agente_04_fastapi"
estado_entregable: "APROBADO_PARA_DESARROLLO"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---

# SDD Arquitectura Técnica
## 1. Visión General
Arquitectura modular desacoplada.

## 5. Reparto de tareas
- Backend PHP (Laravel): {php_line}
- Backend Python (FastAPI): {python_line}
"""
            case AgentID.AGENTE_03_LARAVEL:
                return """---
origen: "agente_03_laravel"
destino_siguiente: "agente_05_qa_php"
estado_entregable: "IMPLEMENTADO_PARA_REVISION"
veredicto: "IMPLEMENTADO"
puntuacion: null
culpable_detectado: null
---

# Implementación Laravel 11
<?php
namespace App\\Http\\Controllers;
class TaskController {}
"""
            case AgentID.AGENTE_04_FASTAPI:
                return """---
origen: "agente_04_fastapi"
destino_siguiente: "agente_06_qa_python"
estado_entregable: "IMPLEMENTADO_PARA_REVISION"
veredicto: "IMPLEMENTADO"
puntuacion: null
culpable_detectado: null
---

# Implementación FastAPI
from fastapi import FastAPI
app = FastAPI()
"""
            case AgentID.AGENTE_05_QA_PHP:
                self.qa_php_calls += 1
                if self.always_fail_qa_php:
                    should_fail = True
                elif self.qa_php_failures_before_pass > 0:
                    should_fail = self.qa_php_calls <= self.qa_php_failures_before_pass
                elif self.fail_qa_php_once:
                    should_fail = self.qa_php_calls == 1
                else:
                    should_fail = False

                if should_fail:
                    return """---
origen: "agente_05_qa_php"
destino_siguiente: "agente_03_laravel"
estado_entregable: "RECHAZADO_PARA_REFACTOR"
veredicto: "RECHAZADO"
puntuacion: 40
culpable_detectado: null
---

# Reporte QA PHP
RECHAZADO: Se encontraron fallos de validación en controladores Laravel.
"""
                return """---
origen: "agente_05_qa_php"
destino_siguiente: "qa_sync_barrier"
estado_entregable: "APROBADO_PARA_DESPLIEGUE"
veredicto: "APROBADO"
puntuacion: 95
culpable_detectado: null
---

# Reporte QA PHP
APROBADO: Cobertura de pruebas completa y cumplimiento estricto de PSR-12.
"""
            case AgentID.AGENTE_06_QA_PYTHON:
                self.qa_python_calls += 1
                if self.always_fail_qa_python:
                    should_fail = True
                elif self.qa_python_failures_before_pass > 0:
                    should_fail = self.qa_python_calls <= self.qa_python_failures_before_pass
                elif self.fail_qa_python_once:
                    should_fail = self.qa_python_calls == 1
                else:
                    should_fail = False

                if should_fail:
                    return """---
origen: "agente_06_qa_python"
destino_siguiente: "agente_04_fastapi"
estado_entregable: "RECHAZADO_PARA_REFACTOR"
veredicto: "RECHAZADO"
puntuacion: 40
culpable_detectado: null
---

# Reporte QA Python
RECHAZADO: Fallos detectados en mypy --strict y pruebas de endpoints asíncronos.
"""
                return """---
origen: "agente_06_qa_python"
destino_siguiente: "qa_sync_barrier"
estado_entregable: "APROBADO_PARA_DESPLIEGUE"
veredicto: "APROBADO"
puntuacion: 95
culpable_detectado: null
---

# Reporte QA Python
APROBADO: Mypy estricto sin errores y tests unitarios aprobados.
"""
            case AgentID.AGENTE_07_DEVOPS:
                return """---
origen: "agente_07_devops"
destino_siguiente: "agente_10_ciso"
estado_entregable: "INFRAESTRUCTURA_LISTA_PARA_PRODUCCION"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---

# Infraestructura Docker
Dockerfiles multi-stage y docker-compose.yml configurados.
"""
            case AgentID.AGENTE_10_CISO:
                self.ciso_calls += 1
                target: AgentID | None = None
                should_fail = False

                if self.ciso_failures_sequence:
                    if self.ciso_calls <= len(self.ciso_failures_sequence):
                        should_fail = True
                        target = self.ciso_failures_sequence[self.ciso_calls - 1]
                elif self.fail_ciso_target:
                    should_fail = not self.fail_ciso_once or self.ciso_calls == 1
                    if should_fail:
                        target = self.fail_ciso_target

                if should_fail and target is not None:
                    return f"""---
origen: "agente_10_ciso"
destino_siguiente: "{target.value}"
estado_entregable: "BLOQUEADO_POR_CIBERSEGURIDAD"
veredicto: "BLOQUEADO"
puntuacion: 30
culpable_detectado: "{target.value}"
---

# Dictamen CISO
BLOQUEADO: Vulnerabilidad crítica de seguridad atribuida a {target.value}.
"""
                return """---
origen: "agente_10_ciso"
destino_siguiente: "agente_08_docs"
estado_entregable: "BLINDADO_APTO_PRODUCCION"
veredicto: "BLINDADO"
puntuacion: 98
culpable_detectado: null
---

# Dictamen CISO
BLINDADO: Auditoría de seguridad OWASP Top 10 superada sin observaciones.
"""
            case AgentID.AGENTE_08_DOCS:
                return """---
origen: "agente_08_docs"
destino_siguiente: "agente_09_growth"
estado_entregable: "DOCUMENTACION_Y_RAG_LISTOS"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---

# Documentación y RAG
Especificación OpenAPI y fragmentos para base de conocimiento vectorial.
"""
            case AgentID.AGENTE_09_GROWTH:
                return """---
origen: "agente_09_growth"
destino_siguiente: "end_pipeline"
estado_entregable: "CICLO_DE_SOFTWARE_COMPLETADO_100"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---

# Estrategia Growth
Plan de lanzamiento, métricas operativas y checklist de producción.
"""
            case _:
                return """---
origen: "unknown"
destino_siguiente: "end_pipeline"
estado_entregable: "CICLO_DE_SOFTWARE_COMPLETADO_100"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---

# Salida Genérica
"""
