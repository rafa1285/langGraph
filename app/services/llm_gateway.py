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
        self._semaphore = asyncio.Semaphore(1)

    async def invoke_agent(
        self,
        agent_id: AgentID,
        system_prompt: str,
        user_payload: str,
    ) -> str:
        """Invoke Gemini with rate limiting, semaphore serialization, and transient error retry."""
        async with self._semaphore:
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

            max_retries = 5
            backoff_delays = [10.0, 20.0, 40.0, 60.0]
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
                    exc_name = type(e).__name__.lower()
                    is_transient = (
                        "429" in err_str
                        or "resourceexhausted" in err_str
                        or "quota" in err_str
                        or "rate limit" in err_str
                        or "503" in err_str
                        or "500" in err_str
                        or "unavailable" in err_str
                        or "servererror" in err_str
                        or "googleapierror" in err_str
                        or "service unavailable" in err_str
                        or "server error" in err_str
                        or "servererror" in exc_name
                        or "googleapierror" in exc_name
                    )
                    if is_transient and attempt < max_retries - 1:
                        backoff = backoff_delays[min(attempt, len(backoff_delays) - 1)]
                        print(
                            f"\n[Gemini Gateway] Aviso: Error transitorio en {agent_id.value}: "
                            f"{e}. Reintentando ({attempt + 2}/{max_retries}) en {backoff:.0f}s..."
                        )
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
            case AgentID.AGENTE_00_CEO:
                if any(
                    k in user_payload
                    for k in (
                        "Resumen Ejecutivo",
                        "Charter Inicial",
                        "Dictamen CISO",
                        "Acta",
                        "Auditoría de Cierre",
                    )
                ):
                    return """---
id_proyecto: "<ID_DEL_PROYECTO>"
version_iteracion: 1
agente_emisor: "agente_00_ceo"
agente_receptor: "broadcast_all"
estado: "LANZAMIENTO_AUTORIZADO"
estado_global: "CICLO_DE_SOFTWARE_COMPLETADO_100"
prioridad: "HIGH"
timestamp: "2026-11-04T00:00:00Z"
---

# Acta de Cierre Ejecutivo y Lanzamiento a Producción
Auditoría completada para Ingeniería, CISO, Documentación, Marketing y Ventas/BI.
- Circuit Breaker: INACTIVO (0 fallos críticos).
- Modelo de Negocio: 100% Zero-Touch validado.
- Veredicto: Lanzamiento comercial y productivo formalmente autorizado.

```json
// filepath: config/release_manifest.json
{
  "release_status": "AUTHORIZED_FOR_PRODUCTION",
  "zero_touch_compliance": true,
  "security_shield_verified": true,
  "circuit_breaker_triggered": false,
  "approved_departments": [
    "agente_01_pm",
    "agente_02_architect",
    "agente_11_ui_ux",
    "agente_03_laravel",
    "agente_04_fastapi",
    "agente_05_qa_php",
    "agente_06_qa_python",
    "agente_07_devops",
    "agente_10_ciso",
    "agente_08_docs",
    "agente_12_marketing",
    "agente_13_sales_analytics"
  ]
}
```
"""
                return """---
id_proyecto: "<ID_DEL_PROYECTO>"
version_iteracion: 1
agente_emisor: "agente_00_ceo"
agente_receptor: "agente_01_pm"
estado: "CHARTER_NEGOCIO_LISTO"
prioridad: "HIGH"
timestamp: "2026-11-04T00:00:00Z"
---

# Business Charter y Reglas de Negocio Zero-Touch
## 1. Tesis de Negocio y Reposicionamiento Zero-Touch
Plataforma SaaS moderna de verificación y saneamiento de datos 100% autoservicio sin comerciales.
## 2. Ingeniería de Unit Economics y Pricing Tier Matrix
- Starter: $19
- Growth: $69
- Scale: $199
## 3. Mandatos Vinculantes por Departamento
- agente_01_pm: Enfoque estricto en MVP sin intervención manual.
- agente_02_architect: Stateless y Serverless-ready.
- agente_11_ui_ux: Conversión en 3 clics y simulador interactivo en Hero.

```json
// filepath: config/business_charter.json
{
  "business_model": "100% Zero-Touch Micro-SaaS",
  "human_touchpoints_allowed": false,
  "max_ttfv_seconds": 60,
  "target_gross_margin_pct": 85.0,
  "tiers": [
    {
      "id": "tier_entry",
      "name": "Starter",
      "price_usd": 19,
      "billing": "one_time_or_monthly",
      "hard_quota": 2500,
      "max_cogs_usd": 1.50
    },
    {
      "id": "tier_pro",
      "name": "Growth",
      "price_usd": 69,
      "billing": "monthly",
      "hard_quota": 25000,
      "max_cogs_usd": 6.00
    },
    {
      "id": "tier_scale",
      "name": "Scale",
      "price_usd": 199,
      "billing": "monthly",
      "hard_quota": 150000,
      "max_cogs_usd": 22.00
    }
  ],
  "kill_switch_rules": {
    "free_demo_rate_limit_per_ip_hour": 10,
    "sha256_deduplication_zero_cost": true,
    "auto_suspend_on_margin_below_pct": 50.0
  }
}
```
"""
            case AgentID.AGENTE_11_UI_UX:
                return """---
id_proyecto: "<ID_DEL_PROYECTO>"
version_iteracion: 1
agente_emisor: "agente_11_ui_ux"
agente_receptor: "agente_03_laravel"
estado: "SISTEMA_DISENO_UI_LISTO"
prioridad: "HIGH"
timestamp: "2026-11-04T00:00:00Z"
---

# Sistema de Diseño y Especificación de Vistas UI/UX
## 1. User Journey & Wireframe Map
Landing Hero con simulador interactivo de validación sin registro previo.
Flujo de conversión estricto en 3 clics y 4 estados por pantalla (Default, Loading, Empty, Error).

## 2. Design Tokens & Tailwind Config
Paleta semántica Brand, Primary, Neutral, Success, Warning y Danger.

## 3. Artefacto Técnico Extraíble (`tailwind.config.js`)
```javascript
// filepath: tailwind.config.js
module.exports = {
  content: [
    "./resources/**/*.blade.php",
    "./resources/**/*.js",
    "./public/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0fdf4',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
        },
      },
    },
  },
  plugins: [],
}
```

## 4. Artefacto Técnico Extraíble (`resources/css/design_tokens.css`)
```css
/* filepath: resources/css/design_tokens.css */
:root {
  --color-primary: #16a34a;
  --color-bg-base: #0f172a;
  --color-text-main: #f8fafc;
  --radius-box: 0.75rem;
}
```
"""
            case AgentID.AGENTE_12_MARKETING:
                return (
                    '---\n'
                    'id_proyecto: "<ID_DEL_PROYECTO>"\n'
                    'version_iteracion: 1\n'
                    'agente_emisor: "agente_12_marketing"\n'
                    'agente_receptor: "agente_13_sales_analytics"\n'
                    'estado: "ESTRATEGIA_CAPTACION_LISTA"\n'
                    'prioridad: "HIGH"\n'
                    'timestamp: "2026-11-04T00:00:00Z"\n'
                    '---\n\n'
                    '# Estrategia de Marketing Digital, SEO Programático y Captación Zero-Touch\n'
                    '## 1. Posicionamiento y Copywriting de Alta Conversión (PAS + PLG)\n'
                    '- Hero Section con Time-to-First-Value en menos de 60 segundos sin registro.\n'
                    '- Simulador interactivo en vivo y 0 fricción.\n\n'
                    '## 2. Configuración de Rastreo Web Técnico (`public/robots.txt`)\n'
                    '```text\n'
                    '# filepath: public/robots.txt\n'
                    'User-agent: *\n'
                    'Allow: /\n'
                    'Allow: /docs.html\n'
                    'Disallow: /api/\n'
                    'Disallow: /admin/\n'
                    'Disallow: /workspace/\n\n'
                    'Sitemap: https://validator-hq-saas.vercel.app/sitemap.xml\n'
                    '```\n\n'
                    '## 3. Mapa del Sitio Canónico (`public/sitemap.xml`)\n'
                    '```xml\n'
                    '<!-- filepath: public/sitemap.xml -->\n'
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                    '  <url>\n'
                    '    <loc>https://validator-hq-saas.vercel.app/</loc>\n'
                    '    <changefreq>daily</changefreq>\n'
                    '    <priority>1.0</priority>\n'
                    '  </url>\n'
                    '  <url>\n'
                    '    <loc>https://validator-hq-saas.vercel.app/docs.html</loc>\n'
                    '    <changefreq>weekly</changefreq>\n'
                    '    <priority>0.8</priority>\n'
                    '  </url>\n'
                    '</urlset>\n'
                    '```\n\n'
                    '## 4. Metadata SEO y Esquema JSON-LD (`config/seo_metadata.json`)\n'
                    '```json\n'
                    '// filepath: config/seo_metadata.json\n'
                    '{\n'
                    '  "acquisition_model": "100% Zero-Touch PLG & Programmatic SEO",\n'
                    '  "human_sales_cta_allowed": false,\n'
                    '  "meta_tags": {\n'
                    '    "title": "ValidatorHQ SaaS — Instant Zero-Touch Validation Engine",\n'
                    '    "description": "Validate payload integrity, security headers and '
                    'compliance in under 60 seconds. Live interactive simulator with zero signup '
                    'required.",\n'
                    '    "og_type": "website",\n'
                    '    "robots": "index, follow"\n'
                    '  },\n'
                    '  "json_ld_schema": {\n'
                    '    "@context": "https://schema.org",\n'
                    '    "@type": "SoftwareApplication",\n'
                    '    "name": "ValidatorHQ SaaS",\n'
                    '    "applicationCategory": "DeveloperApplication",\n'
                    '    "operatingSystem": "Web, Cloud",\n'
                    '    "offers": {\n'
                    '      "@type": "AggregateOffer",\n'
                    '      "lowPrice": "19.00",\n'
                    '      "highPrice": "199.00",\n'
                    '      "priceCurrency": "USD"\n'
                    '    }\n'
                    '  },\n'
                    '  "automated_drip_sequence": [\n'
                    '    {"step": 1, "trigger": "on_free_simulator_run", "delay_hours": 0, '
                    '"subject": "Your instant validation report + API key inside"},\n'
                    '    {"step": 2, "trigger": "on_quota_50_percent", "delay_hours": 48, '
                    '"subject": "Automate your pipeline in 1 click (Zero-Touch webhook setup)"},\n'
                    '    {"step": 3, "trigger": "on_quota_80_percent", "delay_hours": 120, '
                    '"subject": "Unlock 25,000 validations/mo — Instant self-serve upgrade"}\n'
                    '  ]\n'
                    '}\n'
                    '```\n'
                )
            case AgentID.AGENTE_13_SALES_ANALYTICS:
                return """---
origen: "agente_13_sales_analytics"
destino_siguiente: "agente_00_ceo"
estado_entregable: "EMBUDO_Y_METRICAS_LISTOS"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---

# Embudo de Ventas Zero-Touch y Analítica de Negocio (BOFU & BI)
## 1. Matriz de Precios Stripe
```json
// config/stripe_plans.json
{
  "currency": "usd",
  "plans": [
    {"id": "starter_19", "name": "Starter", "price": 19, "credits": 2500},
    {"id": "growth_69", "name": "Growth", "price": 69, "credits": 10000},
    {"id": "scale_199", "name": "Scale Pro", "price": 199, "credits": 50000}
  ]
}
```

## 2. Esquema SQL de Telemetría SaaS
```sql
-- database/analytics_schema.sql
CREATE TABLE IF NOT EXISTS saas_subscriptions (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    plan_id VARCHAR(32) NOT NULL,
    mrr_cents INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```
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
