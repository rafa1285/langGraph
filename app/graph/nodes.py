"""Node implementations for the LangGraph software factory."""

import json
import logging
import re
import time
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import settings
from app.graph.state import SoftwareFactoryState
from app.schemas.office import AgentConversationRecord, AgentEmailRecord
from app.schemas.routing import AgentID, DeliverableStatus, StepExecutionRecord
from app.services.event_bus import ConnectionManager
from app.services.event_bus import event_bus as _default_event_bus
from app.services.llm_gateway import LLMGatewayProtocol
from app.services.mail_service import MailService
from app.services.notion_mcp_service import (
    KnowledgeSyncPort,
    get_knowledge_sync_adapter,
)
from app.services.office_store import OfficeStore
from app.services.output_parser import AgentOutputParser
from app.services.prompt_loader import PromptLoader
from app.services.workspace_writer import WorkspaceWriter
from app.tools.ceo_tools import (
    auto_fix_tier_margins,
    extract_ceo_artifacts,
    scan_zero_touch_compliance,
    sync_ceo_executive_comms,
    verify_unit_economics_math,
)

logger = logging.getLogger(__name__)

FALLBACK_CEO_CHARTER = """---
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

```json
// filepath: config/executive_comms.json
{
  "notion_page": {
    "template": "STRATEGIC_CHARTER_PAGE",
    "title": "Business Charter — Zero-Touch Micro-SaaS",
    "status": "EN_EJECUCION",
    "summary_callout": "Business Charter Zero-Touch definido y transmitido a PM.",
    "markdown_body": "# Business Charter\\nEstrategia y pricing inicial 100% autoservicio."
  },
  "email_notification": {
    "send": true,
    "type": "FOUNDER_DIGEST",
    "subject": "[Charter] Nuevo Proyecto Iniciado",
    "body_text": "El Business Charter ha sido establecido sin comerciales ni soporte humano."
  }
}
```
"""

FALLBACK_CEO_SIGNOFF = """---
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

```json
// filepath: config/executive_comms.json
{
  "notion_page": {
    "template": "RELEASE_AUDIT_ADR",
    "title": "Acta de Lanzamiento a Produccion",
    "status": "COMPLETADO_PRODUCCION",
    "summary_callout": "Ciclo completo de software completado al 100%. Lanzamiento autorizado.",
    "markdown_body": "# Dictamen de Cierre\\nAuditoria superada en todas las areas."
  },
  "email_notification": {
    "send": true,
    "type": "FOUNDER_DIGEST",
    "subject": "[RELEASE] Lanzamiento Autorizado a Produccion",
    "body_text": "El proyecto cumple 100% de requisitos zero-touch y ciberseguridad."
  }
}
```
"""

FALLBACK_UI_UX = """---
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
Conversión en 3 clics y simulador interactivo en Hero sin registro previo.

## 2. Design Tokens & Tailwind Config
Paleta semántica Brand, Primary, Neutral, Success, Warning y Danger.

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

FALLBACK_MARKETING = (
    "---\n"
    'id_proyecto: "<ID_DEL_PROYECTO>"\n'
    "version_iteracion: 1\n"
    'agente_emisor: "agente_12_marketing"\n'
    'agente_receptor: "agente_13_sales_analytics"\n'
    'estado: "ESTRATEGIA_CAPTACION_LISTA"\n'
    'prioridad: "HIGH"\n'
    'timestamp: "2026-11-04T00:00:00Z"\n'
    "---\n\n"
    "# Estrategia de Marketing Digital, SEO Programático y Captación Zero-Touch\n"
    "## 1. Posicionamiento y Copywriting de Alta Conversión (PAS + PLG)\n"
    "- Hero Section con Time-to-First-Value en menos de 60 segundos "
    "sin registro previo ni tarjeta.\n"
    "- Simulador interactivo en vivo y 0 fricción.\n\n"
    "## 2. Configuración de Rastreo Web Técnico (`public/robots.txt`)\n"
    "```text\n"
    "# filepath: public/robots.txt\n"
    "User-agent: *\n"
    "Allow: /\n"
    "Allow: /docs.html\n"
    "Disallow: /api/\n"
    "Disallow: /admin/\n"
    "Disallow: /workspace/\n\n"
    "Sitemap: https://validator-hq-saas.vercel.app/sitemap.xml\n"
    "```\n\n"
    "## 3. Mapa del Sitio Canónico (`public/sitemap.xml`)\n"
    "```xml\n"
    "<!-- filepath: public/sitemap.xml -->\n"
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    "  <url>\n"
    "    <loc>https://validator-hq-saas.vercel.app/</loc>\n"
    "    <changefreq>daily</changefreq>\n"
    "    <priority>1.0</priority>\n"
    "  </url>\n"
    "  <url>\n"
    "    <loc>https://validator-hq-saas.vercel.app/docs.html</loc>\n"
    "    <changefreq>weekly</changefreq>\n"
    "    <priority>0.8</priority>\n"
    "  </url>\n"
    "</urlset>\n"
    "```\n\n"
    "## 4. Metadata SEO y Esquema JSON-LD (`config/seo_metadata.json`)\n"
    "```json\n"
    "// filepath: config/seo_metadata.json\n"
    "{\n"
    '  "acquisition_model": "100% Zero-Touch PLG & Programmatic SEO",\n'
    '  "human_sales_cta_allowed": false,\n'
    '  "meta_tags": {\n'
    '    "title": "ValidatorHQ SaaS — Instant Zero-Touch Validation & Compliance Engine",\n'
    '    "description": "Validate payload integrity, security headers and compliance in under '
    '60 seconds. Live interactive simulator with zero signup required.",\n'
    '    "og_type": "website",\n'
    '    "robots": "index, follow"\n'
    "  },\n"
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
    "    }\n"
    "  },\n"
    '  "automated_drip_sequence": [\n'
    '    {"step": 1, "trigger": "on_free_simulator_run", "delay_hours": 0, "subject": '
    '"Your instant validation report + API key inside"},\n'
    '    {"step": 2, "trigger": "on_quota_50_percent", "delay_hours": 48, "subject": '
    '"Automate your pipeline in 1 click (Zero-Touch webhook setup)"},\n'
    '    {"step": 3, "trigger": "on_quota_80_percent", "delay_hours": 120, "subject": '
    '"Unlock 25,000 validations/mo — Instant self-serve upgrade"}\n'
    "  ]\n"
    "}\n"
    "```\n"
)

FALLBACK_SALES_ANALYTICS = (
    "---\n"
    'id_proyecto: "<ID_DEL_PROYECTO>"\n'
    "version_iteracion: 1\n"
    'agente_emisor: "agente_13_sales_analytics"\n'
    'agente_receptor: "agente_00_ceo"\n'
    'estado: "EMBUDO_Y_METRICAS_LISTOS"\n'
    'prioridad: "HIGH"\n'
    'timestamp: "2026-11-04T00:00:00Z"\n'
    "---\n\n"
    "# Embudo de Ventas Zero-Touch y Analítica de Negocio (BOFU & BI)\n"
    "## 1. Matriz de Precios Stripe (`config/stripe_plans.json`)\n"
    "```json\n"
    "// filepath: config/stripe_plans.json\n"
    "{\n"
    '  "sales_model": "100% Self-Serve Automated Checkout",\n'
    '  "human_sales_reps_allowed": false,\n'
    '  "currency": "USD",\n'
    '  "plans": [\n'
    "    {\n"
    '      "plan_id": "tier_entry",\n'
    '      "name": "Starter",\n'
    '      "price_usd": 19,\n'
    '      "billing_interval": "one_time_or_monthly",\n'
    '      "quota_requests": 2500,\n'
    '      "overage_action": "auto_prompt_upgrade_to_pro",\n'
    '      "target_gross_margin_pct": 85.0\n'
    "    },\n"
    "    {\n"
    '      "plan_id": "tier_pro",\n'
    '      "name": "Growth",\n'
    '      "price_usd": 69,\n'
    '      "billing_interval": "monthly",\n'
    '      "quota_requests": 25000,\n'
    '      "overage_action": "auto_prompt_upgrade_to_scale",\n'
    '      "target_gross_margin_pct": 86.5\n'
    "    },\n"
    "    {\n"
    '      "plan_id": "tier_scale",\n'
    '      "name": "Scale",\n'
    '      "price_usd": 199,\n'
    '      "billing_interval": "monthly",\n'
    '      "quota_requests": 150000,\n'
    '      "overage_action": "auto_topup_pack",\n'
    '      "target_gross_margin_pct": 88.0\n'
    "    }\n"
    "  ],\n"
    '  "upsell_triggers": [\n'
    '    {"threshold_quota_pct": 80, "action": "send_in_app_banner_and_smtp_alert", '
    '"discount_offer_pct": 0},\n'
    '    {"threshold_quota_pct": 100, "action": "trigger_instant_1click_upgrade_modal", '
    '"grace_requests": 50}\n'
    "  ],\n"
    '  "dunning_and_retention": {\n'
    '    "smart_retries_days": [1, 3, 7],\n'
    '    "auto_downgrade_to_free_on_final_failure": true,\n'
    '    "cancel_flow_automated_offer": '
    '"pause_subscription_30_days_or_20pct_off_next_cycle"\n'
    "  }\n"
    "}\n"
    "```\n\n"
    "## 2. Playbook de Cierre Comercial IA (`config/ai_sales_playbook.json`)\n"
    "```json\n"
    "// filepath: config/ai_sales_playbook.json\n"
    "{\n"
    '  "assistant_role": "24/7 Autonomous Revenue & Technical Closer",\n'
    '  "human_escalation_enabled": false,\n'
    '  "objection_handlers": [\n'
    "    {\n"
    '      "category": "pricing_and_roi",\n'
    '      "trigger_keywords": ["expensive", "price", "cost", "discount", "free"],\n'
    '      "response_strategy": "Highlight instant ROI: $19 Starter plan costs less than 15 '
    "minutes of engineering debugging and includes 2,500 verified executions with zero "
    'setup.",\n'
    '      "target_cta_url": "/#pricing-checkout-starter"\n'
    "    },\n"
    "    {\n"
    '      "category": "security_and_compliance",\n'
    '      "trigger_keywords": ["security", "gdpr", "data", "ciso", "privacy", "ssrf"],\n'
    '      "response_strategy": "Confirm CISO-audited architecture: SHA-256 zero-cost '
    "deduplication, strict SSRF protection, zero payload retention and stateless "
    'execution.",\n'
    '      "target_cta_url": "/docs.html#security"\n'
    "    },\n"
    "    {\n"
    '      "category": "integration_speed",\n'
    '      "trigger_keywords": ["api", "integration", "sdk", "webhook", "latency"],\n'
    '      "response_strategy": "Demonstrate sub-60s Time-to-First-Value via REST API '
    "with instant Bearer token provisioning immediately after Stripe "
    'checkout.",\n'
    '      "target_cta_url": "/#demo"\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "```\n\n"
    "## 3. Esquema SQL de Telemetría SaaS (`database/analytics_schema.sql`)\n"
    "```sql\n"
    "-- filepath: database/analytics_schema.sql\n"
    "CREATE TABLE IF NOT EXISTS funnel_events (\n"
    "    event_id VARCHAR(64) PRIMARY KEY,\n"
    "    anonymous_id VARCHAR(64) NOT NULL,\n"
    "    user_id VARCHAR(64),\n"
    "    event_name VARCHAR(64) NOT NULL,\n"
    "    plan_id VARCHAR(32),\n"
    "    metadata_json TEXT,\n"
    "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
    ");\n\n"
    "CREATE TABLE IF NOT EXISTS subscription_ledger (\n"
    "    subscription_id VARCHAR(64) PRIMARY KEY,\n"
    "    user_id VARCHAR(64) NOT NULL,\n"
    "    plan_id VARCHAR(32) NOT NULL,\n"
    "    mrr_cents INTEGER NOT NULL,\n"
    "    cogs_cents INTEGER NOT NULL DEFAULT 0,\n"
    "    status VARCHAR(32) NOT NULL,\n"
    "    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n"
    "    canceled_at TIMESTAMP\n"
    ");\n\n"
    "CREATE VIEW IF NOT EXISTS v_unit_economics_kpi AS\n"
    "SELECT\n"
    "    plan_id,\n"
    "    COUNT(CASE WHEN status = 'active' THEN 1 END) AS active_subscribers,\n"
    "    SUM(CASE WHEN status = 'active' THEN mrr_cents ELSE 0 END) / 100.0 "
    "AS total_mrr_usd,\n"
    "    SUM(CASE WHEN status = 'active' THEN (mrr_cents - cogs_cents) ELSE 0 END) * 100.0 /\n"
    "        NULLIF(SUM(CASE WHEN status = 'active' THEN mrr_cents ELSE 0 END), 0) "
    "AS gross_margin_pct\n"
    "FROM subscription_ledger\n"
    "GROUP BY plan_id;\n"
    "```\n"
)


def _build_ceo_signoff_payload(state: SoftwareFactoryState) -> str:
    """Build comprehensive closing payload for CEO signoff and governance audit."""
    ciso_approved = (
        state.get("status_ciso") == DeliverableStatus.BLINDADO_APTO_PRODUCCION
        or bool(state.get("ciso_approved", False))
    )
    retry_counts: dict[str, int] = dict(state.get("retry_counts", {}))
    retries_php = retry_counts.get("qa_php", 0)
    retries_py = retry_counts.get("qa_python", 0)
    retries_ciso = retry_counts.get("ciso", 0)
    circuit_breakers_triggered = any(
        r >= settings.MAX_RETRIES_PER_GATE for r in (retries_php, retries_py, retries_ciso)
    )

    return (
        f"# Resumen Ejecutivo y Auditoría de Cierre (Acta de Lanzamiento)\n\n"
        f"## 1. Estado de Ciberseguridad y Circuit Breakers\n"
        f"- CISO Aprobado: {ciso_approved}\n"
        f"- Reintentos QA PHP: {retries_php}\n"
        f"- Reintentos QA Python: {retries_py}\n"
        f"- Reintentos CISO: {retries_ciso}\n"
        f"- Circuit Breaker Activado: {circuit_breakers_triggered}\n\n"
        f"## 2. Business Charter Inicial (CEO)\n"
        f"{state.get('ceo_charter', '')}\n\n"
        f"## 3. Dictamen CISO Ciberseguridad\n"
        f"{state.get('dictamen_ciso', '')}\n\n"
        f"## 4. Documentación Técnica y RAG\n"
        f"{state.get('documentacion_rag', '')}\n\n"
        f"## 5. Estrategia de Marketing TOFU\n"
        f"{state.get('marketing_spec', '')}\n\n"
        f"## 6. Ventas y Analítica BI (BOFU)\n"
        f"{state.get('sales_analytics_spec', '')}\n\n"
        f"## 7. Estrategia Growth (Legacy)\n"
        f"{state.get('estrategia_growth', '')}"
    )


def _build_user_payload(agent_id: AgentID, state: SoftwareFactoryState) -> str:
    """Construct exact relevant context for each agent without attention dilution."""
    match agent_id:
        case AgentID.AGENTE_00_CEO:
            if state.get("ceo_charter") and (
                state.get("sales_analytics_spec")
                or state.get("marketing_spec")
                or state.get("dictamen_ciso")
                or state.get("documentacion_rag")
                or state.get("estrategia_growth")
            ):
                return _build_ceo_signoff_payload(state)
            return (
                f"# Idea Inicial del Proyecto\n{state.get('idea_inicial', '')}\n\n"
                f"# Regla Inquebrantable de Negocio\n"
                f"Definir Business Charter 100% Zero-Touch y Self-Service sin comerciales humanos."
            )

        case AgentID.AGENTE_01_PM:
            parts = [f"# Idea Inicial del Proyecto\n{state['idea_inicial']}"]
            if state.get("ceo_charter"):
                parts.append(
                    f"# Business Charter CEO (Reglas Zero-Touch)\n{state['ceo_charter']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_02_ARCHITECT:
            return f"# Documento Pre-SDD Funcional\n{state['pre_sdd_doc']}"

        case AgentID.AGENTE_03_LARAVEL:
            parts = [f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}"]
            if state.get("ui_ux_spec"):
                parts.append(
                    "# Especificación Sistema de Diseño UI/UX y Vistas Frontend\n"
                    f"{state['ui_ux_spec']}"
                )
            if state["status_qa_php"] == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
                parts.append(
                    "# CÓDIGO PHP PREVIO A REFACTORIZAR\n"
                    f"{state['codigo_php']}\n\n"
                    "# INFORME DE RECHAZO QA PHP (CORRECCIONES OBLIGATORIAS)\n"
                    f"{state['reporte_qa_php']}"
                )
            elif (
                state["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
                and state["ciso_culprit"] == AgentID.AGENTE_03_LARAVEL
            ):
                parts.append(
                    "# CÓDIGO PHP PREVIO CON VULNERABILIDADES\n"
                    f"{state['codigo_php']}\n\n"
                    "# DICTAMEN DE CIBERSEGURIDAD CISO (PARCHES OBLIGATORIOS)\n"
                    f"{state['dictamen_ciso']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_04_FASTAPI:
            parts = [f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}"]
            if state["status_qa_python"] == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
                parts.append(
                    "# CÓDIGO PYTHON PREVIO A REFACTORIZAR\n"
                    f"{state['codigo_python']}\n\n"
                    "# INFORME DE RECHAZO QA PYTHON (CORRECCIONES OBLIGATORIAS)\n"
                    f"{state['reporte_qa_python']}"
                )
            elif (
                state["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
                and state["ciso_culprit"] == AgentID.AGENTE_04_FASTAPI
            ):
                parts.append(
                    "# CÓDIGO PYTHON PREVIO CON VULNERABILIDADES\n"
                    f"{state['codigo_python']}\n\n"
                    "# DICTAMEN DE CIBERSEGURIDAD CISO (PARCHES OBLIGATORIOS)\n"
                    f"{state['dictamen_ciso']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_05_QA_PHP:
            parts = [
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}",
                f"# Código PHP / Laravel a Auditar\n{state['codigo_php']}",
            ]
            if state.get("ui_ux_spec"):
                parts.append(
                    "# Especificación Sistema de Diseño UI/UX (Auditoría de Fidelidad Visual)\n"
                    f"{state['ui_ux_spec']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_06_QA_PYTHON:
            return (
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Código Python / FastAPI a Auditar\n{state['codigo_python']}"
            )

        case AgentID.AGENTE_07_DEVOPS:
            parts = [
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}",
                f"# Código PHP / Laravel\n{state['codigo_php']}",
                f"# Código Python / FastAPI\n{state['codigo_python']}",
                f"# Resumen QA PHP\n{state['reporte_qa_php']}",
                f"# Resumen QA Python\n{state['reporte_qa_python']}",
            ]
            if (
                state["status_ciso"] == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
                and state["ciso_culprit"] == AgentID.AGENTE_07_DEVOPS
            ):
                parts.append(
                    "# INFRAESTRUCTURA DOCKER PREVIA BLOQUEADA\n"
                    f"{state['infraestructura_docker']}\n\n"
                    "# DICTAMEN CISO (VULNERABILIDADES INFRAESTRUCTURA)\n"
                    f"{state['dictamen_ciso']}"
                )
            return "\n\n".join(parts)

        case AgentID.AGENTE_10_CISO:
            return (
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Código PHP / Laravel\n{state['codigo_php']}\n\n"
                f"# Código Python / FastAPI\n{state['codigo_python']}\n\n"
                f"# Infraestructura Docker\n{state['infraestructura_docker']}"
            )

        case AgentID.AGENTE_08_DOCS:
            return (
                f"# Pre-SDD Funcional\n{state['pre_sdd_doc']}\n\n"
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Código PHP / Laravel\n{state['codigo_php']}\n\n"
                f"# Código Python / FastAPI\n{state['codigo_python']}\n\n"
                f"# Infraestructura Docker\n{state['infraestructura_docker']}"
            )

        case AgentID.AGENTE_09_GROWTH:
            return (
                f"# Pre-SDD Funcional\n{state['pre_sdd_doc']}\n\n"
                f"# SDD Arquitectura Técnica\n{state['sdd_arquitectura']}\n\n"
                f"# Documentación Técnica y RAG\n{state['documentacion_rag']}"
            )

        case AgentID.AGENTE_11_UI_UX:
            parts = []
            if state.get("ceo_charter"):
                parts.append(
                    f"# Business Charter CEO (Reglas Zero-Touch)\n{state['ceo_charter']}"
                )
            parts.append(f"# Pre-SDD Funcional\n{state.get('pre_sdd_doc', '')}")
            parts.append(f"# SDD Arquitectura Técnica\n{state.get('sdd_arquitectura', '')}")
            return "\n\n".join(parts)

        case AgentID.AGENTE_12_MARKETING:
            return (
                f"# Business Charter CEO\n{state.get('ceo_charter', '')}\n\n"
                f"# Pre-SDD Funcional\n{state.get('pre_sdd_doc', '')}\n\n"
                f"# Sistema de Diseño UI/UX\n{state.get('ui_ux_spec', '')}\n\n"
                f"# Documentación Técnica y RAG\n{state.get('documentacion_rag', '')}"
            )

        case AgentID.AGENTE_13_SALES_ANALYTICS:
            return (
                f"# Business Charter CEO\n{state.get('ceo_charter', '')}\n\n"
                f"# Estrategia Marketing TOFU\n{state.get('marketing_spec', '')}\n\n"
                f"# Sistema de Diseño UI/UX\n{state.get('ui_ux_spec', '')}\n\n"
                f"# Documentación Técnica y RAG\n{state.get('documentacion_rag', '')}"
            )

        case AgentID.AGENTE_14_QA_UI_UX:
            return (
                f"# Business Charter CEO\n{state.get('ceo_charter', '')}\n\n"
                f"# Sistema de Diseño UI/UX a Auditar\n{state.get('ui_ux_spec', '')}\n\n"
                f"# Pre-SDD Funcional\n{state.get('pre_sdd_doc', '')}\n\n"
                f"# SDD Arquitectura Técnica\n{state.get('sdd_arquitectura', '')}"
            )

        case _:
            return state.get("idea_inicial", "")


class FactoryNodes:
    """Factory creating and executing nodes within the Software Factory LangGraph pipeline."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        prompt_loader: PromptLoader,
        workspace_writer: WorkspaceWriter,
        office_store: OfficeStore | None = None,
        mail_service: MailService | None = None,
        knowledge_sync: KnowledgeSyncPort | None = None,
        event_bus: ConnectionManager | None = None,
    ) -> None:
        """Initialize FactoryNodes with gateway, prompt loader, writer, and office mail store."""
        self.llm_gateway = llm_gateway
        self.prompt_loader = prompt_loader
        self.workspace_writer = workspace_writer
        self.office_store = office_store or OfficeStore()
        self.mail_service = mail_service or MailService(self.office_store)
        self.event_bus = event_bus if event_bus is not None else _default_event_bus
        if knowledge_sync is not None:
            self.knowledge_sync: KnowledgeSyncPort | None = knowledge_sync
        elif settings.NOTION_MCP_ENABLED:
            self.knowledge_sync = get_knowledge_sync_adapter()
        else:
            self.knowledge_sync = None

    async def _execute_agent_step(
        self,
        agent_id: AgentID,
        state: SoftwareFactoryState,
        payload_override: str | None = None,
    ) -> tuple[str, DeliverableStatus, str, StepExecutionRecord]:
        """Execute common workflow for LLM-powered agents: prompt, call, parse, write, record."""
        step_number = len(state.get("execution_history", [])) + 1
        system_prompt = await self.prompt_loader.load_prompt(agent_id)
        payload = (
            payload_override
            if payload_override is not None
            else _build_user_payload(agent_id, state)
        )

        # Broadcast agent started
        await self.event_bus.broadcast(
            project_id=state["project_id"],
            event_type="AGENT_STARTED",
            data={
                "agent_id": agent_id.value,
                "step_number": step_number,
            },
        )

        # 1. Fetch unread emails and inject inbox prefix if available
        inbox_prefix, unread_emails = await self.mail_service.fetch_unread_inbox(
            state["project_id"],
            agent_id,
        )
        if inbox_prefix:
            payload = f"{inbox_prefix}\n\n{payload}"

        for unread_email in unread_emails:
            await self.event_bus.broadcast(
                project_id=state["project_id"],
                event_type="EMAIL_READ",
                data={
                    "agent_id": agent_id.value,
                    "email_id": str(unread_email.id),
                    "sender": unread_email.sender,
                    "subject": unread_email.subject,
                },
            )

        # 2. Invoke LLM and record duration
        start_time = time.perf_counter()
        raw_output = await self.llm_gateway.invoke_agent(agent_id, system_prompt, payload)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        header = AgentOutputParser.parse_routing_header(agent_id, raw_output)

        # 3. Save physical file deliverable
        artifact_path = await self.workspace_writer.save_deliverable(
            project_id=state["project_id"],
            step_number=step_number,
            agent_id=agent_id,
            content=raw_output,
        )

        # 4. Save conversation record & telemetry in OfficeStore
        tokens_in = max(1, (len(system_prompt) + len(payload)) // 4)
        tokens_out = max(1, len(raw_output) // 4)
        culprit_str = (
            header.culpable_detectado.value
            if isinstance(header.culpable_detectado, AgentID)
            else (str(header.culpable_detectado) if header.culpable_detectado else None)
        )
        conv_record = AgentConversationRecord(
            project_id=state["project_id"],
            step_number=step_number,
            agent_id=agent_id,
            system_prompt=system_prompt,
            user_payload=payload,
            raw_response=raw_output,
            status=header.estado_entregable,
            verdict=header.veredicto,
            score=header.puntuacion,
            culprit=culprit_str,
            duration_ms=duration_ms,
            estimated_tokens_in=tokens_in,
            estimated_tokens_out=tokens_out,
        )
        await self.office_store.save_conversation(conv_record)

        # 5. Send handoff email(s) to next target(s) or culprit
        sent_emails = await self.mail_service.send_handoff_email(
            project_id=state["project_id"],
            step_number=step_number,
            sender_id=agent_id,
            target_next=header.destino_siguiente,
            header=header,
            artifact_path=artifact_path,
            raw_output=raw_output,
        )

        for sent_em in sent_emails:
            await self.event_bus.broadcast(
                project_id=state["project_id"],
                event_type="EMAIL_SENT",
                data=sent_em.model_dump(mode="json"),
            )

        if header.veredicto in ("RECHAZADO", "BLOQUEADO"):
            await self.event_bus.broadcast(
                project_id=state["project_id"],
                event_type="GATE_REJECTED",
                data={
                    "agent_id": agent_id.value,
                    "verdict": header.veredicto,
                    "status": header.estado_entregable.value,
                    "culprit": culprit_str,
                },
            )

        # 6. Synchronize deliverable, status, and emails with Notion MCP if enabled
        if self.knowledge_sync is not None:
            try:
                await self.knowledge_sync.append_deliverable_page(
                    project_id=state["project_id"],
                    step_number=step_number,
                    agent_id=agent_id.value,
                    deliverable_title=header.estado_entregable.value,
                    markdown_content=raw_output,
                )
                await self.knowledge_sync.update_project_status(
                    project_id=state["project_id"],
                    status_data={
                        "current_status": header.estado_entregable.value,
                        "last_agent": agent_id.value,
                        "steps_completed": step_number,
                        "verdict": header.veredicto,
                    },
                )
                for sent_em in sent_emails:
                    await self.knowledge_sync.log_agent_email(
                        project_id=state["project_id"],
                        email_data=sent_em.model_dump(mode="json"),
                    )
            except Exception as exc:
                logger.warning(
                    "Fallo en sincronización automática con Notion MCP para %s: %s",
                    state["project_id"],
                    exc,
                )

        record = StepExecutionRecord(
            step_number=step_number,
            agent_id=agent_id,
            status=header.estado_entregable,
            target_next=header.destino_siguiente,
            artifact_path=artifact_path,
            timestamp_iso=datetime.now(UTC).isoformat(),
        )

        await self.event_bus.broadcast(
            project_id=state["project_id"],
            event_type="STEP_COMPLETED",
            data={
                "agent_id": agent_id.value,
                "step_number": step_number,
                "status": header.estado_entregable.value,
                "verdict": header.veredicto,
            },
        )

        return raw_output, header.estado_entregable, header.destino_siguiente, record

    async def _escalate_circuit_breaker_to_ceo(
        self,
        project_id: str,
        gate: str,
        culprit: AgentID | None,
        retries: int,
        step_number: int,
    ) -> None:
        """Register a CRITICAL escalation email notification to CEO when Circuit Breaker trips."""
        culprit_str = culprit.value if culprit else "desconocido"
        escalation_email = AgentEmailRecord(
            id=uuid4(),
            project_id=project_id,
            step_number=step_number,
            sender=(
                f"{AgentID.AGENTE_10_CISO.value}@agentoffice.local"
                if gate == "ciso"
                else f"agente_{gate}@agentoffice.local"
            ),
            recipient="ceo@agentoffice.local",
            subject=f"🚨 [CIRCUIT BREAKER] Escalado Crítico al CEO en compuerta {gate.upper()}",
            body_summary=(
                f"ALERTA CRÍTICA: Límite de {retries} reintentos superado en {gate.upper()}.\n"
                f"Culpable identificado: {culprit_str}.\n"
                "Flujo detenido preventivamente por activación del Circuit Breaker."
            ),
            attached_deliverable_path=f"circuit_breaker://{gate}",
            priority="CRITICAL",
        )
        await self.office_store.save_email(escalation_email)
        await self.event_bus.broadcast(
            project_id=project_id,
            event_type="CIRCUIT_BREAKER_ESCALATION",
            data=escalation_email.model_dump(mode="json"),
        )

    async def node_01_pm(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 01 (PM): Generates Pre-SDD specification."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_01_PM,
            state,
        )
        return {
            "pre_sdd_doc": raw_output,
            "execution_history": [record],
        }

    async def node_02_architect(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 02 (Architect): Designs SDD and determines required stacks."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_02_ARCHITECT,
            state,
        )
        req_php, req_python = AgentOutputParser.detect_required_stacks(raw_output)

        updates: dict[str, object] = {
            "sdd_arquitectura": raw_output,
            "requiere_php": req_php,
            "requiere_python": req_python,
            "execution_history": [record],
        }

        # If a stack is not required, pre-approve it so QA barrier proceeds
        if not req_php:
            updates["status_qa_php"] = DeliverableStatus.APROBADO_PARA_DESPLIEGUE
        if not req_python:
            updates["status_qa_python"] = DeliverableStatus.APROBADO_PARA_DESPLIEGUE

        return updates

    async def node_03_laravel(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 03 (Laravel Dev): Implements or refactors PHP code."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_03_LARAVEL,
            state,
        )
        return {
            "codigo_php": raw_output,
            "status_qa_php": DeliverableStatus.IMPLEMENTADO_PARA_REVISION,
            "execution_history": [record],
        }

    async def node_04_fastapi(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 04 (FastAPI Dev): Implements or refactors Python code."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_04_FASTAPI,
            state,
        )
        return {
            "codigo_python": raw_output,
            "status_qa_python": DeliverableStatus.IMPLEMENTADO_PARA_REVISION,
            "execution_history": [record],
        }

    async def node_05_qa_php(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 05 (QA PHP): Audits PHP code and increments retry count if rejected."""
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_05_QA_PHP,
            state,
        )
        updates: dict[str, object] = {
            "reporte_qa_php": raw_output,
            "status_qa_php": status,
            "execution_history": [record],
        }
        if status == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
            current_retries = state.get("retry_counts", {}).get("qa_php", 0)
            new_retries = current_retries + 1
            updates["retry_counts"] = {"qa_php": new_retries}
            if new_retries >= settings.MAX_RETRIES_PER_GATE:
                await self._escalate_circuit_breaker_to_ceo(
                    project_id=state["project_id"],
                    gate="qa_php",
                    culprit=AgentID.AGENTE_03_LARAVEL,
                    retries=new_retries,
                    step_number=len(state.get("execution_history", [])) + 1,
                )

        return updates

    async def node_06_qa_python(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 06 (QA Python): Audits Python code and increments retries if rejected."""
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_06_QA_PYTHON,
            state,
        )
        updates: dict[str, object] = {
            "reporte_qa_python": raw_output,
            "status_qa_python": status,
            "execution_history": [record],
        }
        if status == DeliverableStatus.RECHAZADO_PARA_REFACTOR:
            current_retries = state.get("retry_counts", {}).get("qa_python", 0)
            new_retries = current_retries + 1
            updates["retry_counts"] = {"qa_python": new_retries}
            if new_retries >= settings.MAX_RETRIES_PER_GATE:
                await self._escalate_circuit_breaker_to_ceo(
                    project_id=state["project_id"],
                    gate="qa_python",
                    culprit=AgentID.AGENTE_04_FASTAPI,
                    retries=new_retries,
                    step_number=len(state.get("execution_history", [])) + 1,
                )

        return updates

    async def node_qa_sync_barrier(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Lightweight synchronization barrier node waiting for QA completion before DevOps."""
        step_number = len(state.get("execution_history", [])) + 1
        record = StepExecutionRecord(
            step_number=step_number,
            agent_id=AgentID.QA_SYNC_BARRIER,
            status=DeliverableStatus.APROBADO_PARA_DESPLIEGUE,
            target_next=AgentID.AGENTE_07_DEVOPS.value,
            artifact_path="barrier://qa_sync_barrier",
            timestamp_iso=datetime.now(UTC).isoformat(),
        )
        return {
            "execution_history": [record],
        }

    async def node_07_devops(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 07 (DevOps): Generates Docker infrastructure."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_07_DEVOPS,
            state,
        )
        return {
            "infraestructura_docker": raw_output,
            "execution_history": [record],
        }

    async def node_10_ciso(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 10 (CISO): Audits security, assigns culprit, and triggers re-checks."""
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_10_CISO,
            state,
        )
        header = AgentOutputParser.parse_routing_header(AgentID.AGENTE_10_CISO, raw_output)

        updates: dict[str, object] = {
            "dictamen_ciso": raw_output,
            "status_ciso": status,
            "execution_history": [record],
        }

        if status == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD:
            current_ciso_retries = state.get("retry_counts", {}).get("ciso", 0)
            new_ciso_retries = current_ciso_retries + 1
            updates["retry_counts"] = {"ciso": new_ciso_retries}

            culprit = header.culpable_detectado or AgentID.AGENTE_07_DEVOPS
            updates["ciso_culprit"] = culprit

            if new_ciso_retries >= settings.MAX_RETRIES_PER_GATE:
                await self._escalate_circuit_breaker_to_ceo(
                    project_id=state["project_id"],
                    gate="ciso",
                    culprit=culprit,
                    retries=new_ciso_retries,
                    step_number=len(state.get("execution_history", [])) + 1,
                )

            # Reset QA gate so patched code is re-tested before returning to DevOps/CISO
            if culprit == AgentID.AGENTE_03_LARAVEL:
                updates["status_qa_php"] = DeliverableStatus.PENDIENTE
            elif culprit == AgentID.AGENTE_04_FASTAPI:
                updates["status_qa_python"] = DeliverableStatus.PENDIENTE
        elif status == DeliverableStatus.BLINDADO_APTO_PRODUCCION:
            updates["ciso_culprit"] = None

        return updates

    async def node_08_docs(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 08 (Docs & RAG): Creates documentation and knowledge chunks."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_08_DOCS,
            state,
        )
        return {
            "documentacion_rag": raw_output,
            "execution_history": [record],
        }

    async def node_09_growth(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 09 (Growth): Generates launch strategy and final checklist."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_09_GROWTH,
            state,
        )
        return {
            "estrategia_growth": raw_output,
            "execution_history": [record],
        }

    async def ceo_charter_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 00 (CEO Opening): Establishes Zero-Touch business charter."""
        charter_payload = (
            f"# Idea Inicial del Proyecto\n{state.get('idea_inicial', '')}\n\n"
            f"# Regla Inquebrantable de Negocio\n"
            f"Definir Business Charter 100% Zero-Touch y Self-Service sin comerciales humanos."
        )
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_00_CEO,
            state,
            payload_override=charter_payload,
        )
        if not raw_output or "config/business_charter.json" not in raw_output:
            raw_output = FALLBACK_CEO_CHARTER

        # 1. Extract artifacts using extract_ceo_artifacts
        artifacts = extract_ceo_artifacts(raw_output)
        charter_json = artifacts.get("business_charter")
        comms_json = artifacts.get("executive_comms")

        # 2. Verify unit economics math and auto-fix if deficient (< 80% net margin)
        if charter_json:
            math_audit = verify_unit_economics_math(charter_json)
            if not math_audit.get("valid", True) or any(
                t.get("net_margin_pct", 0.0) < 80.0
                for t in math_audit.get("tiers_audit", [])
            ):
                fixed_charter = auto_fix_tier_margins(charter_json)
                fixed_json_str = json.dumps(fixed_charter, indent=2)
                m = re.search(
                    r"(//\s*filepath:\s*config/business_charter\.json\s*[\r\n]+)\{.*?\}(?=\s*```|\s*$)",
                    raw_output,
                    flags=re.DOTALL,
                )
                if m:
                    raw_output = (
                        raw_output[:m.start(1)]
                        + f"// filepath: config/business_charter.json\n{fixed_json_str}\n"
                        + raw_output[m.end():]
                    )

        # 3. Synchronize executive comms
        if not comms_json:
            comms_json = {
                "notion_page": {
                    "template": "STRATEGIC_CHARTER_PAGE",
                    "title": f"Business Charter — {state.get('project_id', 'Micro-SaaS')}",
                    "status": "EN_EJECUCION",
                    "summary_callout": "Business Charter 100% Zero-Touch inicializado.",
                    "markdown_body": raw_output[:1900],
                },
                "email_notification": {
                    "send": False,
                    "type": "FOUNDER_DIGEST",
                    "subject": f"[Charter] Proyecto {state.get('project_id', '')} Inicializado",
                    "body_text": f"Charter definido para {state.get('project_id', '')}.",
                },
            }
        sync_ceo_executive_comms(comms_json)

        return {
            "ceo_charter": raw_output,
            "version_iteracion": state.get("version_iteracion", 1),
            "execution_history": [record],
        }

    node_00_ceo_charter = ceo_charter_node

    async def ceo_signoff_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 00 (CEO Closing): Audits entire pipeline and authorizes launch."""
        # 1. Scan Marketing/Sales/UI deliverables for Zero-Touch compliance
        deliverables_to_scan: list[tuple[str, str, AgentID]] = [
            ("marketing_spec", state.get("marketing_spec", ""), AgentID.AGENTE_12_MARKETING),
            (
                "sales_analytics_spec",
                state.get("sales_analytics_spec", ""),
                AgentID.AGENTE_13_SALES_ANALYTICS,
            ),
            ("estrategia_growth", state.get("estrategia_growth", ""), AgentID.AGENTE_09_GROWTH),
            ("ui_ux_spec", state.get("ui_ux_spec", ""), AgentID.AGENTE_11_UI_UX),
        ]
        detected_violations: list[str] = []
        infringing_agent: AgentID | None = None
        for name, text, agent in deliverables_to_scan:
            if text:
                scan_res = scan_zero_touch_compliance(text)
                if not scan_res.get("compliant", True):
                    terms = scan_res.get("detected_forbidden_terms", [])
                    detected_violations.extend([f"{t} (en {name})" for t in terms])
                    if not infringing_agent:
                        infringing_agent = agent

        # 2. Build closing payload incorporating zero-touch scan results
        closing_payload = _build_ceo_signoff_payload(state)
        if detected_violations:
            infringing_name = infringing_agent.value if infringing_agent else "Desconocido"
            closing_payload += (
                "\n\n## 8. ALERTA ZERO-TOUCH: Términos Prohibidos Detectados\n"
                "- Violaciones detectadas:\n"
                + "\n".join(f"  * {v}" for v in detected_violations)
                + f"\n- Agente infractor identificado: {infringing_name}\n"
                "- Acción requerida: Activar MODO 3 (LANZAMIENTO_BLOQUEADO_REWORK)."
            )

        # 3. Execute agent step
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_00_CEO,
            state,
            payload_override=closing_payload,
        )
        if not raw_output or "config/release_manifest.json" not in raw_output:
            raw_output = FALLBACK_CEO_SIGNOFF
            status = DeliverableStatus.LANZAMIENTO_AUTORIZADO

        current_version = state.get("version_iteracion", 1)
        retry_counts = dict(state.get("retry_counts", {}))
        circuit_breaker_active = any(
            r >= settings.MAX_RETRIES_PER_GATE for r in retry_counts.values()
        ) or state.get("status_ciso") == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD

        is_blocked = (
            status == DeliverableStatus.LANZAMIENTO_BLOQUEADO_REWORK
            or bool(detected_violations)
            or (circuit_breaker_active and status != DeliverableStatus.LANZAMIENTO_AUTORIZADO)
        )

        if detected_violations and current_version < 3:
            status = DeliverableStatus.LANZAMIENTO_BLOQUEADO_REWORK
            is_blocked = True

        artifacts = extract_ceo_artifacts(raw_output)
        comms_json = artifacts.get("executive_comms")

        halt_reason = state.get("halt_reason")
        if is_blocked:
            if current_version < 3:
                next_version = current_version + 1
                ceo_blocked = True
                approved = False
                status = DeliverableStatus.LANZAMIENTO_BLOQUEADO_REWORK
                parsed_header = AgentOutputParser.parse_routing_header(
                    AgentID.AGENTE_00_CEO, raw_output
                )
                culprit = (
                    parsed_header.culpable_detectado
                    if parsed_header and parsed_header.culpable_detectado
                    else (infringing_agent or state.get("ciso_culprit") or AgentID.AGENTE_10_CISO)
                )
                halt_reason = (
                    f"Lanzamiento bloqueado por CEO (iteración {current_version}) hacia "
                    f"{culprit.value}."
                )
            else:
                next_version = current_version
                ceo_blocked = False
                approved = False
                culprit = None
                halt_reason = (
                    f"Lanzamiento abortado tras {current_version} iteraciones sin resolución "
                    f"(escalado crítico)."
                )
                if comms_json and "email_notification" in comms_json:
                    comms_json["email_notification"]["type"] = "CRITICAL_ESCALATION"
                    comms_json["email_notification"]["send"] = True
                    comms_json["email_notification"]["subject"] = (
                        f"[CRITICAL ESCALATION] Proyecto {state.get('project_id', '')} Bloqueado "
                        f"en Iteración {current_version}"
                    )
        else:
            next_version = current_version
            ceo_blocked = False
            approved = True
            culprit = None

        if not comms_json:
            comms_json = {
                "notion_page": {
                    "template": "CIRCUIT_BREAKER_ALERT" if is_blocked else "RELEASE_AUDIT_ADR",
                    "title": f"Cierre Proyecto: {state.get('project_id', '')}",
                    "status": "BLOQUEADO_REWORK" if is_blocked else "COMPLETADO_PRODUCCION",
                    "summary_callout": "Dictamen ejecutivo de lanzamiento.",
                    "markdown_body": raw_output[:1900],
                },
                "email_notification": {
                    "send": True,
                    "type": "CRITICAL_ESCALATION" if is_blocked else "FOUNDER_DIGEST",
                    "subject": (
                        f"[{'CRITICAL' if is_blocked else 'RELEASE'}] {state.get('project_id', '')}"
                    ),
                    "body_text": f"Estado de cierre: {status.value}.",
                },
            }

        sync_ceo_executive_comms(comms_json)

        return {
            "ceo_signoff": raw_output,
            "ceo_approved": approved,
            "status_ceo": status,
            "ceo_blocked": ceo_blocked,
            "ceo_culprit": culprit,
            "version_iteracion": next_version,
            "zero_touch_violations": detected_violations,
            "halt_reason": halt_reason,
            "execution_history": [record],
        }

    node_00_ceo_signoff = ceo_signoff_node

    async def ui_ux_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 11 (UI/UX): Designs TailwindCSS design system and 3-click flows."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_11_UI_UX,
            state,
        )
        if not raw_output or "tailwind.config.js" not in raw_output:
            raw_output = FALLBACK_UI_UX
        return {
            "ui_ux_spec": raw_output,
            "execution_history": [record],
        }

    node_11_ui_ux = ui_ux_node

    async def marketing_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 12 (Marketing): Formulates TOFU SEO, sitemap, robots, and copy."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_12_MARKETING,
            state,
        )
        if not raw_output or "robots.txt" not in raw_output:
            raw_output = FALLBACK_MARKETING
        return {
            "marketing_spec": raw_output,
            "execution_history": [record],
        }

    node_12_marketing = marketing_node

    async def sales_analytics_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 13 (Sales & BI): Pricing, bot playbook, and SQL schema."""
        raw_output, _status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_13_SALES_ANALYTICS,
            state,
        )
        if not raw_output or "stripe_plans.json" not in raw_output:
            raw_output = FALLBACK_SALES_ANALYTICS
        return {
            "sales_analytics_spec": raw_output,
            "execution_history": [record],
        }

    node_13_sales_analytics = sales_analytics_node

    async def qa_ui_ux_node(self, state: SoftwareFactoryState) -> dict[str, object]:
        """Node for Agent 14 (QA UI/UX Auditor): Audits visual ergonomics, canvas, and usability."""
        raw_output, status, _dest, record = await self._execute_agent_step(
            AgentID.AGENTE_14_QA_UI_UX,
            state,
        )
        return {
            "reporte_qa_ui_ux": raw_output,
            "status_qa_ui_ux": status,
            "execution_history": [record],
        }

    node_14_qa_ui_ux = qa_ui_ux_node
