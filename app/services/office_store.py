"""Persistent SQLite storage for agent conversations, internal emails, and telemetry."""

import json
import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import aiosqlite

from app.core.config import settings
from app.schemas.brownfield import AuditReport
from app.schemas.chat import ChatTurn
from app.schemas.office import (
    AgentConversationRecord,
    AgentEmailRecord,
    AgentLLMConfig,
    AgentLLMConfigUpdate,
    AssignedModelItem,
    EmailPriority,
    LLMModelCatalogCreate,
    LLMModelCatalogItem,
    LLMModelCatalogUpdate,
    MarketingChannelConfig,
    MarketingChannelID,
    MarketingToolID,
    MarketingToolTestResponse,
    MarketingType,
    ProjectMarketingProfile,
    ProjectMarketingToolConfig,
)
from app.schemas.routing import AgentID, DeliverableStatus

logger = logging.getLogger(__name__)

_AGENT_ID_ALIASES: dict[str, str] = {
    "00_ceo": "agente_00_ceo",
    "01_pm": "agente_01_pm",
    "02_architect": "agente_02_architect",
    "03_laravel": "agente_03_laravel",
    "03_laravel_dev": "agente_03_laravel",
    "04_fastapi": "agente_04_fastapi",
    "04_fastapi_dev": "agente_04_fastapi",
    "05_qa_php": "agente_05_qa_php",
    "06_qa_python": "agente_06_qa_python",
    "07_devops": "agente_07_devops",
    "08_docs": "agente_08_docs",
    "08_docs_rag": "agente_08_docs",
    "09_growth": "agente_09_growth",
    "10_ciso": "agente_10_ciso",
    "11_ui_ux": "agente_11_ui_ux",
    "12_marketing": "agente_12_marketing",
    "13_sales_analytics": "agente_13_sales_analytics",
    "14_qa_ui_ux": "agente_14_qa_ui_ux",
}


def normalize_agent_id(agent_id: str | AgentID) -> str:
    """Normalize agent id strings or AgentID enums to canonical 'agente_XX_...'."""
    raw = agent_id.value if isinstance(agent_id, AgentID) else str(agent_id).strip().lower()
    if raw in _AGENT_ID_ALIASES:
        return _AGENT_ID_ALIASES[raw]
    if raw.startswith("agente_"):
        return raw
    candidate = f"agente_{raw}"
    if candidate in _AGENT_ID_ALIASES.values():
        return candidate
    return raw


def has_env_key(api_key_env: str) -> bool:
    """Check whether the given API key variable is present and non-empty in settings or env."""
    if not api_key_env:
        return False
    val = getattr(settings, api_key_env, None)
    if val is not None and str(val).strip():
        return True
    env_val = os.environ.get(api_key_env)
    return bool(env_val and str(env_val).strip())


DEFAULT_CATALOG_MODELS: list[dict[str, Any]] = [
    {
        "model_id": "gemini-3.5-pro",
        "display_name": "Gemini 3.5 Pro",
        "provider": "google",
        "base_url": None,
        "api_key_env": "GEMINI_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 8192,
        "is_active": True,
    },
    {
        "model_id": "gemini-3.6-flash",
        "display_name": "Gemini 3.6 Flash",
        "provider": "google",
        "base_url": None,
        "api_key_env": "GEMINI_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 8192,
        "is_active": True,
    },
    {
        "model_id": "gemini-3.5-flash-lite",
        "display_name": "Gemini 3.5 Flash Lite",
        "provider": "google",
        "base_url": None,
        "api_key_env": "GEMINI_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
    {
        "model_id": "gemini-3.5-flash",
        "display_name": "Gemini 3.5 Flash",
        "provider": "google",
        "base_url": None,
        "api_key_env": "GEMINI_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 8192,
        "is_active": True,
    },
    {
        "model_id": "mistral-large-latest",
        "display_name": "Mistral Large Latest",
        "provider": "mistral",
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
    {
        "model_id": "codestral-latest",
        "display_name": "Codestral Latest",
        "provider": "mistral",
        "base_url": "https://codestral.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "tier": "free",
        "default_temperature": 0.1,
        "default_max_tokens": 8192,
        "is_active": True,
    },
    {
        "model_id": "qwen/qwen3-32b",
        "display_name": "Qwen 3 32B (Groq)",
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
    {
        "model_id": "llama-3.3-70b-versatile",
        "display_name": "Llama 3.3 70B (Groq)",
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
    {
        "model_id": "llama-3.1-8b-instant",
        "display_name": "Llama 3.1 8B (Groq)",
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
    {
        "model_id": "meta-llama/llama-4-scout-17b-16e-instruct",
        "display_name": "Llama 4 Scout 17B (Groq)",
        "provider": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "tier": "free",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
    {
        "model_id": "claude-3-5-sonnet-latest",
        "display_name": "Claude 3.5 Sonnet",
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "tier": "paid",
        "default_temperature": 0.2,
        "default_max_tokens": 8192,
        "is_active": True,
    },
    {
        "model_id": "o3-mini",
        "display_name": "o3-mini",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "tier": "paid",
        "default_temperature": 1.0,
        "default_max_tokens": 8192,
        "is_active": True,
    },
    {
        "model_id": "gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "tier": "paid",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
    {
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "tier": "paid",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
    {
        "model_id": "deepseek-chat",
        "display_name": "DeepSeek Chat (V3)",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "tier": "paid",
        "default_temperature": 0.2,
        "default_max_tokens": 4096,
        "is_active": True,
    },
]

DEFAULT_AGENT_CHAINS: dict[str, dict[str, Any]] = {
    "agente_02_architect": {
        "assigned": [
            ("gemini-3.5-pro", True, 1),
            ("gemini-3.6-flash", True, 2),
            ("mistral-large-latest", True, 3),
            ("claude-3-5-sonnet-latest", False, 4),
            ("o3-mini", False, 5),
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    },
    "agente_10_ciso": {
        "assigned": [
            ("gemini-3.5-pro", True, 1),
            ("mistral-large-latest", True, 2),
            ("qwen/qwen3-32b", True, 3),
            ("o3-mini", False, 4),
            ("claude-3-5-sonnet-latest", False, 5),
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    },
    "agente_01_pm": {
        "assigned": [
            ("gemini-3.6-flash", True, 1),
            ("llama-3.3-70b-versatile", True, 2),
            ("mistral-large-latest", True, 3),
            ("gpt-4o-mini", False, 4),
        ],
        "temperature": 0.2,
        "max_tokens": 8192,
    },
    "agente_03_laravel": {
        "assigned": [
            ("gemini-3.6-flash", True, 1),
            ("codestral-latest", True, 2),
            ("qwen/qwen3-32b", True, 3),
            ("claude-3-5-sonnet-latest", False, 4),
            ("deepseek-chat", False, 5),
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    },
    "agente_04_fastapi": {
        "assigned": [
            ("gemini-3.6-flash", True, 1),
            ("codestral-latest", True, 2),
            ("qwen/qwen3-32b", True, 3),
            ("claude-3-5-sonnet-latest", False, 4),
            ("deepseek-chat", False, 5),
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    },
    "agente_11_ui_ux": {
        "assigned": [
            ("gemini-3.5-pro", True, 1),
            ("gemini-3.6-flash", True, 2),
            ("codestral-latest", True, 3),
            ("claude-3-5-sonnet-latest", False, 4),
        ],
        "temperature": 0.2,
        "max_tokens": 8192,
    },
    "agente_05_qa_php": {
        "assigned": [
            ("qwen/qwen3-32b", True, 1),
            ("codestral-latest", True, 2),
            ("gemini-3.5-flash-lite", True, 3),
            ("deepseek-chat", False, 4),
            ("gpt-4o-mini", False, 5),
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    },
    "agente_06_qa_python": {
        "assigned": [
            ("qwen/qwen3-32b", True, 1),
            ("codestral-latest", True, 2),
            ("gemini-3.5-flash-lite", True, 3),
            ("deepseek-chat", False, 4),
            ("gpt-4o-mini", False, 5),
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    },
    "agente_14_qa_ui_ux": {
        "assigned": [
            ("gemini-3.6-flash", True, 1),
            ("qwen/qwen3-32b", True, 2),
            ("gemini-3.5-flash-lite", True, 3),
            ("gemini-3.5-flash", False, 4),
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    },
    "agente_07_devops": {
        "assigned": [
            ("codestral-latest", True, 1),
            ("qwen/qwen3-32b", True, 2),
            ("gemini-3.5-flash-lite", True, 3),
            ("gpt-4o-mini", False, 4),
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    },
    "agente_08_docs": {
        "assigned": [
            ("gemini-3.6-flash", True, 1),
            ("gemini-3.5-flash-lite", True, 2),
            ("mistral-large-latest", True, 3),
            ("gemini-3.5-flash", False, 4),
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    },
    "agente_09_growth": {
        "assigned": [
            ("llama-3.3-70b-versatile", True, 1),
            ("mistral-large-latest", True, 2),
            ("llama-3.1-8b-instant", True, 3),
            ("gpt-4o-mini", False, 4),
        ],
        "temperature": 0.4,
        "max_tokens": 4096,
    },
    "agente_12_marketing": {
        "assigned": [
            ("llama-3.3-70b-versatile", True, 1),
            ("mistral-large-latest", True, 2),
            ("llama-3.1-8b-instant", True, 3),
            ("gpt-4o-mini", False, 4),
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    },
    "agente_13_sales_analytics": {
        "assigned": [
            ("gemini-3.6-flash", True, 1),
            ("mistral-large-latest", True, 2),
            ("gemini-3.5-flash-lite", True, 3),
            ("gpt-4o-mini", False, 4),
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    },
    "agente_00_ceo": {
        "assigned": [
            ("meta-llama/llama-4-scout-17b-16e-instruct", True, 1),
            ("gemini-3.5-flash-lite", True, 2),
            ("qwen/qwen3-32b", True, 3),
            ("gpt-4o-mini", False, 4),
            ("gpt-4o", False, 5),
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    },
}

MARKETING_CHANNELS_CATALOG: list[dict[str, Any]] = [
    {
        "channel_id": "linkedin",
        "name": "LinkedIn",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Enfoque B2B corporativo, thought leadership, carruseles y casos de uso."
        ),
    },
    {
        "channel_id": "x_twitter",
        "name": "X / Twitter",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Tono técnico directo, hilos de código, release notes y changelog público."
        ),
    },
    {
        "channel_id": "instagram_meta",
        "name": "Instagram / Meta",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Enfoque visual, infografías, Reels de demostración y stories destacadas."
        ),
    },
    {
        "channel_id": "tiktok",
        "name": "TikTok",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Formato vertical dinámico, hook en los primeros 3 segundos y estilo dev-friendly."
        ),
    },
    {
        "channel_id": "producthunt",
        "name": "Product Hunt",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Lanzamiento con tagline llamativo, primera demo GIF y makers comment estructurado."
        ),
    },
    {
        "channel_id": "google_ads",
        "name": "Google Ads",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Búsqueda transaccional y copy orientado a alta intención de conversión."
        ),
    },
    {
        "channel_id": "reddit_devto",
        "name": "Reddit & Dev.to",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Contenido técnico honesto en comunidades relevantes y zero-spam."
        ),
    },
    {
        "channel_id": "telegram_discord",
        "name": "Telegram & Discord",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Anuncios a la comunidad, alertas tempranas de updates y soporte self-service."
        ),
    },
    {
        "channel_id": "email_newsletter",
        "name": "Email Newsletter",
        "account_handle_or_url": "",
        "credentials": {},
        "custom_instructions": (
            "Bienvenida/onboarding, nutrición de leads técnicos y resúmenes periódicos."
        ),
    },
]

MARKETING_TOOLS_CATALOG: list[dict[str, Any]] = [
    {
        "tool_id": "market_research_seo",
        "name": "Market Research & SEO Scraper",
        "description": (
            "Investigación automatizada de palabras clave, competidores y tendencias."
        ),
        "credentials": {},
        "settings": {
            "competitor_urls": [],
            "seed_keywords": [],
            "search_depth": "deep",
        },
        "is_configured": True,
    },
    {
        "tool_id": "seo_landing_injector",
        "name": "SEO Landing & Metadata Injector",
        "description": (
            "Generación e inyección de OpenGraph, sitemap.xml, robots.txt y landing pages."
        ),
        "credentials": {},
        "settings": {
            "domain_url": "",
            "generate_landing_html": True,
            "generate_sitemap_robots": True,
            "target_keywords": [],
        },
        "is_configured": True,
    },
    {
        "tool_id": "email_campaign_manager",
        "name": "Email Campaign & Outreach Manager",
        "description": (
            "Secuencias de email marketing, newsletters de captación y onboarding."
        ),
        "credentials": {},
        "settings": {
            "email_provider": "smtp",
            "sender_email": "",
            "sender_name": "",
            "recipient_list": [],
            "send_mode": "dry_run",
        },
        "is_configured": True,
    },
    {
        "tool_id": "social_ads_publisher",
        "name": "Social & Ads Campaign Publisher",
        "description": (
            "Publicación y gestión de campañas publicitarias en redes y buscadores."
        ),
        "credentials": {},
        "settings": {
            "target_platforms": ["meta", "google"],
            "daily_budget_limit": 50,
            "ad_format": "responsive",
        },
        "is_configured": True,
    },
]


def get_marketing_preset(
    marketing_type: str | MarketingType,
    project_id: str = "",
    project_name: str | None = None,
) -> ProjectMarketingProfile:
    """Generate default ProjectMarketingProfile preset based on marketing archetype."""
    m_type_str = str(marketing_type).lower().strip()
    valid_types = (
        "none",
        "saas_b2b",
        "b2c_app_ecommerce",
        "devtools_api",
        "internal_rollout",
        "custom",
    )
    m_type: MarketingType = cast(
        MarketingType, m_type_str if m_type_str in valid_types else "saas_b2b"
    )

    enabled = True
    include_growth = True
    include_sales = True
    active_tools: set[str] = set()
    active_channels: set[str] = set()
    brand_voice = "persuasivo-profesional"
    target_audience = ""

    if m_type == "none":
        enabled = False
        include_growth = False
        include_sales = False
        active_tools = set()
        active_channels = set()
        brand_voice = "neutral"
        target_audience = "Sin marketing activo"

    elif m_type == "saas_b2b":
        enabled = True
        include_growth = True
        include_sales = True
        active_tools = {
            "market_research_seo",
            "seo_landing_injector",
            "email_campaign_manager",
            "social_ads_publisher",
        }
        active_channels = {
            "linkedin",
            "x_twitter",
            "producthunt",
            "google_ads",
            "email_newsletter",
        }
        brand_voice = "persuasivo-profesional"
        target_audience = "Empresas B2B, fundadores, CTOs y líderes de producto"

    elif m_type == "b2c_app_ecommerce":
        enabled = True
        include_growth = True
        include_sales = True
        active_tools = {
            "market_research_seo",
            "seo_landing_injector",
            "email_campaign_manager",
            "social_ads_publisher",
        }
        active_channels = {
            "instagram_meta",
            "tiktok",
            "google_ads",
            "email_newsletter",
            "x_twitter",
        }
        brand_voice = "enérgico-cercano"
        target_audience = "Consumidores finales, early adopters y usuarios móviles"

    elif m_type == "devtools_api":
        enabled = True
        include_growth = True
        include_sales = True
        active_tools = {
            "market_research_seo",
            "seo_landing_injector",
            "social_ads_publisher",
        }
        active_channels = {
            "producthunt",
            "reddit_devto",
            "x_twitter",
            "linkedin",
            "telegram_discord",
        }
        brand_voice = "técnico-riguroso"
        target_audience = "Desarrolladores de software, ingenieros de datos y DevOps"

    elif m_type == "internal_rollout":
        enabled = True
        include_growth = False
        include_sales = False
        active_tools = {
            "email_campaign_manager",
        }
        active_channels = {
            "email_newsletter",
            "telegram_discord",
        }
        brand_voice = "claro-formativo"
        target_audience = "Equipos internos, empleados y stakeholders corporativos"

    elif m_type == "custom":
        enabled = True
        include_growth = True
        include_sales = True
        active_tools = {
            "market_research_seo",
            "seo_landing_injector",
        }
        active_channels = {
            "linkedin",
            "x_twitter",
        }
        brand_voice = "persuasivo-profesional"
        target_audience = "Audiencia personalizada"

    channels: list[MarketingChannelConfig] = [
        MarketingChannelConfig(
            channel_id=cast(MarketingChannelID, ch["channel_id"]),
            name=ch["name"],
            enabled=ch["channel_id"] in active_channels,
            account_handle_or_url=ch.get("account_handle_or_url", ""),
            credentials=dict(ch.get("credentials", {})),
            custom_instructions=ch.get("custom_instructions", ""),
        )
        for ch in MARKETING_CHANNELS_CATALOG
    ]

    tools: list[ProjectMarketingToolConfig] = [
        ProjectMarketingToolConfig(
            tool_id=cast(MarketingToolID, t["tool_id"]),
            name=t["name"],
            description=t["description"],
            enabled=t["tool_id"] in active_tools,
            credentials=dict(t.get("credentials", {})),
            settings=dict(t.get("settings", {})),
            is_configured=t.get("is_configured", True),
        )
        for t in MARKETING_TOOLS_CATALOG
    ]

    return ProjectMarketingProfile(
        project_id=project_id,
        project_name=project_name,
        marketing_enabled=enabled,
        include_growth_agent=include_growth,
        include_sales_analytics_agent=include_sales,
        marketing_type=m_type,
        brand_voice=brand_voice,
        target_audience=target_audience,
        language="es",
        channels=channels,
        tools=tools,
        last_execution_status="idle" if enabled else "disabled",
        last_executed_at=None,
    )


class OfficeStore:
    """Async store managing conversations, emails, and telemetry persisted in SQLite."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialize the store with a specific or default SQLite database path."""
        if db_path is None:
            self.db_path = Path(settings.OFFICE_DB_PATH)
        else:
            self.db_path = Path(db_path)

    async def init_db(self) -> None:
        """Initialize database tables and indexes if they do not already exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            await db.execute("PRAGMA busy_timeout = 5000;")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_conversations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    agent_id TEXT NOT NULL,
                    system_prompt TEXT NOT NULL,
                    user_payload TEXT NOT NULL,
                    raw_response TEXT NOT NULL,
                    status TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    score INTEGER,
                    culprit TEXT,
                    duration_ms INTEGER NOT NULL,
                    estimated_tokens_in INTEGER NOT NULL,
                    estimated_tokens_out INTEGER NOT NULL,
                    is_visible INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                """
            )
            # Ensure is_visible column exists on existing databases
            async with db.execute("PRAGMA table_info(agent_conversations);") as cur:
                existing_cols = [r[1] for r in await cur.fetchall()]
                if "is_visible" not in existing_cols:
                    await db.execute(
                        "ALTER TABLE agent_conversations "
                        "ADD COLUMN is_visible INTEGER NOT NULL DEFAULT 1;"
                    )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_emails (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    cc TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body_summary TEXT NOT NULL,
                    attached_deliverable_path TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_project "
                "ON agent_conversations(project_id, step_number);"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_email_recipient "
                "ON agent_emails(project_id, recipient, is_read);"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    project_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_session "
                "ON chat_sessions(session_id, created_at);"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS brownfield_audits (
                    project_id TEXT PRIMARY KEY,
                    repo_url TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    depth TEXT NOT NULL,
                    health_score INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_bf_status "
                "ON brownfield_audits(status, created_at);"
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_models_catalog (
                    model_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    base_url TEXT,
                    api_key_env TEXT NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'free',
                    default_temperature REAL NOT NULL DEFAULT 0.2,
                    default_max_tokens INTEGER NOT NULL DEFAULT 4096,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_llm_configs (
                    agent_id TEXT PRIMARY KEY,
                    assigned_models TEXT NOT NULL,
                    temperature REAL NOT NULL DEFAULT 0.2,
                    max_tokens INTEGER NOT NULL DEFAULT 4096,
                    timeout INTEGER NOT NULL DEFAULT 60,
                    max_retries INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS project_marketing_configs (
                    project_id TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_marketing_updated "
                "ON project_marketing_configs(updated_at);"
            )
            # Auto-seed catalog if empty
            async with db.execute("SELECT COUNT(*) FROM llm_models_catalog;") as cur:
                row = await cur.fetchone()
                if row and row[0] == 0:
                    await self._seed_catalog(db)

            # Auto-seed agent configs if empty
            async with db.execute("SELECT COUNT(*) FROM agent_llm_configs;") as cur:
                row = await cur.fetchone()
                if row and row[0] == 0:
                    await self._seed_agent_configs(db)

            await db.commit()

    async def save_conversation(self, record: AgentConversationRecord) -> None:
        """Persist an agent conversation record to SQLite."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO agent_conversations (
                    id, project_id, step_number, agent_id, system_prompt,
                    user_payload, raw_response, status, verdict, score,
                    culprit, duration_ms, estimated_tokens_in,
                    estimated_tokens_out, is_visible, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(record.id),
                    record.project_id,
                    record.step_number,
                    record.agent_id.value,
                    record.system_prompt,
                    record.user_payload,
                    record.raw_response,
                    record.status.value,
                    record.verdict,
                    record.score,
                    record.culprit,
                    record.duration_ms,
                    record.estimated_tokens_in,
                    record.estimated_tokens_out,
                    record.is_visible,
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()

    async def get_conversations(
        self,
        project_id: str,
        agent_id: AgentID | None = None,
    ) -> list[AgentConversationRecord]:
        """Retrieve stored conversations for a project, optionally filtered by agent."""
        await self.init_db()
        query = (
            "SELECT id, project_id, step_number, agent_id, system_prompt, "
            "user_payload, raw_response, status, verdict, score, culprit, "
            "duration_ms, estimated_tokens_in, estimated_tokens_out, created_at, "
            "COALESCE(is_visible, 1) "
            "FROM agent_conversations WHERE project_id = ?"
        )
        params: list[str] = [project_id]
        if agent_id is not None:
            query += " AND agent_id = ?"
            params.append(agent_id.value)
        query += " ORDER BY created_at ASC, step_number ASC"

        records: list[AgentConversationRecord] = []
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    try:
                        rec_id = UUID(str(row[0]))
                    except (ValueError, TypeError):
                        import uuid as _uuid
                        rec_id = _uuid.uuid4()

                    try:
                        aid = AgentID(row[3])
                    except ValueError:
                        aid = AgentID.AGENTE_00_CEO

                    try:
                        st_val = DeliverableStatus(row[7])
                    except ValueError:
                        st_val = DeliverableStatus.PENDIENTE

                    records.append(
                        AgentConversationRecord(
                            id=rec_id,
                            project_id=row[1],
                            step_number=row[2],
                            agent_id=aid,
                            system_prompt=row[4],
                            user_payload=row[5],
                            raw_response=row[6],
                            status=st_val,
                            verdict=row[8],
                            score=row[9],
                            culprit=row[10],
                            duration_ms=row[11],
                            estimated_tokens_in=row[12],
                            estimated_tokens_out=row[13],
                            created_at=row[14],
                            is_visible=int(row[15]),
                        )
                    )
        return records

    async def save_email(self, email: AgentEmailRecord) -> None:
        """Persist an internal agent email to SQLite."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO agent_emails (
                    id, project_id, step_number, sender, recipient,
                    cc, subject, body_summary, attached_deliverable_path,
                    priority, is_read, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(email.id),
                    email.project_id,
                    email.step_number,
                    email.sender,
                    email.recipient,
                    json.dumps(email.cc),
                    email.subject,
                    email.body_summary,
                    email.attached_deliverable_path,
                    email.priority,
                    1 if email.is_read else 0,
                    email.created_at.isoformat(),
                ),
            )
            await db.commit()

    async def get_emails(
        self,
        project_id: str,
        agent_id: AgentID | None = None,
        recipient: str | None = None,
        sender: str | None = None,
        priority: EmailPriority | None = None,
        unread_only: bool = False,
    ) -> list[AgentEmailRecord]:
        """Query emails for a project with optional filters for recipient, sender, and priority."""
        await self.init_db()
        query = (
            "SELECT id, project_id, step_number, sender, recipient, cc, "
            "subject, body_summary, attached_deliverable_path, priority, "
            "is_read, created_at FROM agent_emails WHERE project_id = ?"
        )
        params: list[str | int] = [project_id]

        if agent_id is not None:
            agent_addr = f"%{agent_id.value}%"
            query += " AND (recipient LIKE ? OR sender LIKE ?)"
            params.extend([agent_addr, agent_addr])

        if recipient is not None:
            query += " AND recipient LIKE ?"
            params.append(f"%{recipient}%")

        if sender is not None:
            query += " AND sender LIKE ?"
            params.append(f"%{sender}%")

        if priority is not None:
            query += " AND priority = ?"
            params.append(priority)

        if unread_only:
            query += " AND is_read = 0"

        query += " ORDER BY created_at ASC, step_number ASC"

        emails: list[AgentEmailRecord] = []
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    emails.append(
                        AgentEmailRecord(
                            id=UUID(row[0]),
                            project_id=row[1],
                            step_number=row[2],
                            sender=row[3],
                            recipient=row[4],
                            cc=cast(list[str], json.loads(row[5])),
                            subject=row[6],
                            body_summary=row[7],
                            attached_deliverable_path=row[8],
                            priority=cast(EmailPriority, row[9]),
                            is_read=bool(row[10]),
                            created_at=row[11],
                        )
                    )
        return emails

    async def get_email_by_id(self, email_id: UUID | str) -> AgentEmailRecord | None:
        """Find and return an email by its unique ID."""
        await self.init_db()
        str_id = str(email_id)
        query = (
            "SELECT id, project_id, step_number, sender, recipient, cc, "
            "subject, body_summary, attached_deliverable_path, priority, "
            "is_read, created_at FROM agent_emails WHERE id = ?"
        )
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(query, [str_id]) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return AgentEmailRecord(
                    id=UUID(row[0]),
                    project_id=row[1],
                    step_number=row[2],
                    sender=row[3],
                    recipient=row[4],
                    cc=cast(list[str], json.loads(row[5])),
                    subject=row[6],
                    body_summary=row[7],
                    attached_deliverable_path=row[8],
                    priority=cast(EmailPriority, row[9]),
                    is_read=bool(row[10]),
                    created_at=row[11],
                )

    async def mark_emails_as_read(self, email_ids: list[UUID | str]) -> None:
        """Mark a list of email IDs as read."""
        if not email_ids:
            return
        await self.init_db()
        placeholders = ",".join("?" for _ in email_ids)
        str_ids = [str(eid) for eid in email_ids]
        query = f"UPDATE agent_emails SET is_read = 1 WHERE id IN ({placeholders})"
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(query, str_ids)
            await db.commit()

    async def get_all_projects_summary(self) -> dict[str, dict[str, Any]]:
        """Retrieve aggregated telemetry and latest status per project from SQLite."""
        await self.init_db()
        telemetry_query = (
            "SELECT project_id, COUNT(id), COALESCE(SUM(duration_ms), 0), "
            "COALESCE(SUM(estimated_tokens_in), 0), COALESCE(SUM(estimated_tokens_out), 0), "
            "MAX(created_at) FROM agent_conversations WHERE is_visible = 1 GROUP BY project_id"
        )
        status_query = (
            "SELECT project_id, status FROM agent_conversations WHERE is_visible = 1 "
            "ORDER BY created_at ASC, step_number ASC"
        )
        email_projects_query = (
            "SELECT DISTINCT project_id FROM agent_emails "
            "WHERE project_id IN ("
            "    SELECT DISTINCT project_id FROM agent_conversations WHERE is_visible = 1"
            ")"
        )

        summaries: dict[str, dict[str, Any]] = {}
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(telemetry_query) as cursor:
                for row in await cursor.fetchall():
                    summaries[row[0]] = {
                        "project_id": row[0],
                        "steps_completed": row[1],
                        "total_duration_ms": row[2],
                        "total_tokens_in": row[3],
                        "total_tokens_out": row[4],
                        "updated_at": row[5] or "",
                        "current_status": "COMPLETED",
                    }
            async with db.execute(status_query) as cursor:
                for row in await cursor.fetchall():
                    pid, st = row[0], row[1]
                    if pid in summaries:
                        prev = summaries[pid].get("current_status")
                        is_final = prev in (
                            "LANZAMIENTO_AUTORIZADO",
                            "CICLO_DE_SOFTWARE_COMPLETADO_100",
                        )
                        if is_final and st not in (
                            "LANZAMIENTO_AUTORIZADO",
                            "CICLO_DE_SOFTWARE_COMPLETADO_100",
                        ):
                            continue
                        summaries[pid]["current_status"] = st
            async with db.execute(email_projects_query) as cursor:
                for row in await cursor.fetchall():
                    pid = row[0]
                    if pid not in summaries:
                        summaries[pid] = {
                            "project_id": pid,
                            "steps_completed": 0,
                            "total_duration_ms": 0,
                            "total_tokens_in": 0,
                            "total_tokens_out": 0,
                            "updated_at": "",
                            "current_status": "PENDIENTE",
                        }
            try:
                bf_query = "SELECT project_id, repo_url, status, updated_at FROM brownfield_audits"
                async with db.execute(bf_query) as cursor:
                    for row in await cursor.fetchall():
                        pid = row[0]
                        if pid not in summaries:
                            summaries[pid] = {
                                "project_id": pid,
                                "steps_completed": 1,
                                "total_duration_ms": 0,
                                "total_tokens_in": 0,
                                "total_tokens_out": 0,
                                "updated_at": row[3] or "",
                                "current_status": row[2] or "AUDITED",
                                "project_name": row[1],
                            }
            except Exception:
                pass
        return summaries

    async def save_chat_turn(
        self,
        turn_id: str,
        session_id: str,
        agent_id: str,
        project_id: str | None,
        role: str,
        content: str,
    ) -> None:
        """Persist a single chat turn to SQLite."""
        await self.init_db()
        from datetime import UTC, datetime

        created_at = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT INTO chat_sessions (
                    id, session_id, agent_id, project_id, role, content, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (turn_id, session_id, agent_id, project_id, role, content, created_at),
            )
            await db.commit()

    async def get_chat_history(
        self, session_id: str, limit: int = 50
    ) -> list[ChatTurn]:
        """Retrieve turns for a chat session, ordered chronologically (oldest first)."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, session_id, agent_id, project_id, role, content, created_at
                FROM chat_sessions
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (session_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            ChatTurn(
                id=str(row["id"]),
                session_id=str(row["session_id"]),
                agent_id=str(row["agent_id"]),
                project_id=row["project_id"],
                role=str(row["role"]),
                content=str(row["content"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    async def save_audit_report(self, report: AuditReport) -> None:
        """Persist or update an executive brownfield audit report."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO brownfield_audits (
                    project_id, repo_url, branch, depth, health_score,
                    report_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.project_id,
                    report.repo_url,
                    report.branch,
                    report.depth,
                    report.health_score,
                    report.model_dump_json(),
                    report.status,
                    report.created_at,
                    report.updated_at,
                ),
            )
            await db.commit()

    async def get_audit_report(self, project_id: str) -> AuditReport | None:
        """Retrieve a saved brownfield audit report by its project_id."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT report_json FROM brownfield_audits WHERE project_id = ?
                """,
                (project_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        return AuditReport.model_validate_json(row["report_json"])

    async def update_audit_status(self, project_id: str, new_status: str) -> None:
        """Update audit report status (e.g. pending_approval -> approved | rejected)."""
        report = await self.get_audit_report(project_id)
        if report is None:
            raise KeyError(f"Informe de auditoría para '{project_id}' no encontrado.")

        from datetime import UTC, datetime

        now_iso = datetime.now(UTC).isoformat()
        updated_report = report.model_copy(
            update={"status": new_status, "updated_at": now_iso}
        )
        await self.save_audit_report(updated_report)

    # ── LLM Models Catalog & Agent Routing Configuration ───────────────────

    async def _seed_catalog(self, db: aiosqlite.Connection) -> None:
        """Seed initial LLM models catalog."""
        now_iso = datetime.now(UTC).isoformat()
        for m in DEFAULT_CATALOG_MODELS:
            await db.execute(
                """
                INSERT OR IGNORE INTO llm_models_catalog (
                    model_id, display_name, provider, base_url, api_key_env,
                    tier, default_temperature, default_max_tokens, is_active,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    m["model_id"],
                    m["display_name"],
                    m["provider"],
                    m.get("base_url"),
                    m["api_key_env"],
                    m.get("tier", "free"),
                    m.get("default_temperature", 0.2),
                    m.get("default_max_tokens", 4096),
                    1 if m.get("is_active", True) else 0,
                    now_iso,
                    now_iso,
                ),
            )

    async def _seed_agent_configs(self, db: aiosqlite.Connection) -> None:
        """Seed initial fallback routing chains for all 15 agents."""
        now_iso = datetime.now(UTC).isoformat()
        for agent_id, chain_info in DEFAULT_AGENT_CHAINS.items():
            assigned = [
                {"model_id": mid, "enabled": enabled, "priority": priority}
                for mid, enabled, priority in chain_info["assigned"]
            ]
            await db.execute(
                """
                INSERT OR IGNORE INTO agent_llm_configs (
                    agent_id, assigned_models, temperature, max_tokens, timeout, max_retries,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    agent_id,
                    json.dumps(assigned),
                    chain_info.get("temperature", 0.2),
                    chain_info.get("max_tokens", 4096),
                    60,
                    1,
                    now_iso,
                    now_iso,
                ),
            )

    async def get_llm_catalog(self) -> list[LLMModelCatalogItem]:
        """List all LLM models in the catalog enriched with credential availability."""
        await self.init_db()
        models: list[LLMModelCatalogItem] = []
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT model_id, display_name, provider, base_url, api_key_env,
                       tier, default_temperature, default_max_tokens, is_active,
                       created_at, updated_at
                FROM llm_models_catalog
                ORDER BY tier ASC, provider ASC, display_name ASC;
                """
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    api_key_env = str(row["api_key_env"])
                    models.append(
                        LLMModelCatalogItem(
                            model_id=str(row["model_id"]),
                            display_name=str(row["display_name"]),
                            provider=str(row["provider"]),
                            base_url=row["base_url"],
                            api_key_env=api_key_env,
                            tier=str(row["tier"]),
                            default_temperature=float(row["default_temperature"]),
                            default_max_tokens=int(row["default_max_tokens"]),
                            is_active=bool(row["is_active"]),
                            has_api_key=has_env_key(api_key_env),
                            created_at=row["created_at"],
                            updated_at=row["updated_at"],
                        )
                    )
        return models

    async def get_llm_model(self, model_id: str) -> LLMModelCatalogItem | None:
        """Retrieve a specific LLM model by model_id."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT model_id, display_name, provider, base_url, api_key_env,
                       tier, default_temperature, default_max_tokens, is_active,
                       created_at, updated_at
                FROM llm_models_catalog
                WHERE model_id = ?;
                """,
                (model_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                api_key_env = str(row["api_key_env"])
                return LLMModelCatalogItem(
                    model_id=str(row["model_id"]),
                    display_name=str(row["display_name"]),
                    provider=str(row["provider"]),
                    base_url=row["base_url"],
                    api_key_env=api_key_env,
                    tier=str(row["tier"]),
                    default_temperature=float(row["default_temperature"]),
                    default_max_tokens=int(row["default_max_tokens"]),
                    is_active=bool(row["is_active"]),
                    has_api_key=has_env_key(api_key_env),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

    async def create_llm_model(self, item: LLMModelCatalogCreate) -> LLMModelCatalogItem:
        """Register a new LLM model in the global catalog."""
        await self.init_db()
        now_iso = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT INTO llm_models_catalog (
                    model_id, display_name, provider, base_url, api_key_env,
                    tier, default_temperature, default_max_tokens, is_active,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    item.model_id,
                    item.display_name,
                    item.provider,
                    item.base_url,
                    item.api_key_env,
                    item.tier,
                    item.default_temperature,
                    item.default_max_tokens,
                    1 if item.is_active else 0,
                    now_iso,
                    now_iso,
                ),
            )
            await db.commit()

        created = await self.get_llm_model(item.model_id)
        if created is None:
            raise RuntimeError("Error al persistir el nuevo modelo en SQLite.")
        return created

    async def update_llm_model(
        self, model_id: str, item: LLMModelCatalogUpdate
    ) -> LLMModelCatalogItem | None:
        """Update fields for an existing LLM model in the catalog."""
        existing = await self.get_llm_model(model_id)
        if existing is None:
            return None

        fields: list[str] = []
        params: list[Any] = []

        if item.display_name is not None:
            fields.append("display_name = ?")
            params.append(item.display_name)
        if item.provider is not None:
            fields.append("provider = ?")
            params.append(item.provider)
        if item.base_url is not None:
            fields.append("base_url = ?")
            params.append(item.base_url)
        if item.api_key_env is not None:
            fields.append("api_key_env = ?")
            params.append(item.api_key_env)
        if item.tier is not None:
            fields.append("tier = ?")
            params.append(item.tier)
        if item.default_temperature is not None:
            fields.append("default_temperature = ?")
            params.append(item.default_temperature)
        if item.default_max_tokens is not None:
            fields.append("default_max_tokens = ?")
            params.append(item.default_max_tokens)
        if item.is_active is not None:
            fields.append("is_active = ?")
            params.append(1 if item.is_active else 0)

        if not fields:
            return existing

        now_iso = datetime.now(UTC).isoformat()
        fields.append("updated_at = ?")
        params.append(now_iso)
        params.append(model_id)

        query = f"UPDATE llm_models_catalog SET {', '.join(fields)} WHERE model_id = ?;"
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(query, params)
            await db.commit()

        return await self.get_llm_model(model_id)

    async def delete_llm_model(self, model_id: str) -> bool:
        """Delete an LLM model from the catalog."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(
                "DELETE FROM llm_models_catalog WHERE model_id = ?;", (model_id,)
            ) as cur:
                await db.commit()
                return cur.rowcount > 0

    async def get_agent_llm_config(self, agent_id: str | AgentID) -> AgentLLMConfig:
        """Retrieve dynamic LLM configuration for an agent, enriched with catalog details."""
        await self.init_db()
        norm_id = normalize_agent_id(agent_id)
        catalog_map = {m.model_id: m for m in await self.get_llm_catalog()}

        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT agent_id, assigned_models, temperature, max_tokens, timeout,
                       max_retries, updated_at
                FROM agent_llm_configs WHERE agent_id = ?;
                """,
                (norm_id,),
            ) as cur:
                row = await cur.fetchone()

        if row is None:
            return await self.reset_agent_llm_config(norm_id)

        try:
            assigned_raw = json.loads(row["assigned_models"])
        except Exception:
            assigned_raw = []

        assigned_models: list[AssignedModelItem] = []
        for item in assigned_raw:
            mid = item.get("model_id", "")
            cat_item = catalog_map.get(mid)
            dname = cat_item.display_name if cat_item else item.get("display_name", mid)
            prov = cat_item.provider if cat_item else item.get("provider", "custom")
            tier_val = cat_item.tier if cat_item else item.get("tier", "free")
            assigned_models.append(
                AssignedModelItem(
                    model_id=mid,
                    enabled=bool(item.get("enabled", True)),
                    priority=int(item.get("priority", 1)),
                    display_name=dname,
                    provider=prov,
                    tier=tier_val,
                    has_api_key=cat_item.has_api_key if cat_item else False,
                )
            )

        assigned_models.sort(key=lambda x: x.priority)

        return AgentLLMConfig(
            agent_id=norm_id,
            assigned_models=assigned_models,
            temperature=float(row["temperature"]),
            max_tokens=int(row["max_tokens"]),
            timeout=int(row["timeout"]),
            max_retries=int(row["max_retries"]),
            updated_at=row["updated_at"],
        )

    async def save_agent_llm_config(
        self, agent_id: str | AgentID, config: AgentLLMConfigUpdate
    ) -> AgentLLMConfig:
        """Update and persist agent LLM routing configuration."""
        await self.init_db()
        norm_id = normalize_agent_id(agent_id)
        current = await self.get_agent_llm_config(norm_id)

        now_iso = datetime.now(UTC).isoformat()
        new_assigned = [
            {
                "model_id": item.model_id,
                "enabled": item.enabled,
                "priority": item.priority,
            }
            for item in config.assigned_models
        ]
        new_assigned.sort(key=lambda x: x["priority"])

        temperature = config.temperature if config.temperature is not None else current.temperature
        max_tokens = config.max_tokens if config.max_tokens is not None else current.max_tokens
        timeout = config.timeout if config.timeout is not None else current.timeout
        max_retries = config.max_retries if config.max_retries is not None else current.max_retries

        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO agent_llm_configs (
                    agent_id, assigned_models, temperature, max_tokens, timeout, max_retries,
                    created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM agent_llm_configs WHERE agent_id = ?), ?),
                    ?
                );
                """,
                (
                    norm_id,
                    json.dumps(new_assigned),
                    temperature,
                    max_tokens,
                    timeout,
                    max_retries,
                    norm_id,
                    now_iso,
                    now_iso,
                ),
            )
            await db.commit()

        return await self.get_agent_llm_config(norm_id)

    async def reset_agent_llm_config(self, agent_id: str | AgentID) -> AgentLLMConfig:
        """Reset an agent's LLM configuration to its factory default chain."""
        await self.init_db()
        norm_id = normalize_agent_id(agent_id)
        now_iso = datetime.now(UTC).isoformat()
        default_chain = DEFAULT_AGENT_CHAINS.get(norm_id)

        if default_chain:
            assigned = [
                {"model_id": mid, "enabled": enabled, "priority": priority}
                for mid, enabled, priority in default_chain["assigned"]
            ]
            temp = float(default_chain.get("temperature", 0.2))
            tokens = int(default_chain.get("max_tokens", 4096))
        else:
            assigned = [
                {"model_id": "gemini-3.6-flash", "enabled": True, "priority": 1},
                {"model_id": "gemini-3.5-flash-lite", "enabled": True, "priority": 2},
            ]
            temp = 0.2
            tokens = 4096

        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO agent_llm_configs (
                    agent_id, assigned_models, temperature, max_tokens, timeout, max_retries,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    norm_id,
                    json.dumps(assigned),
                    temp,
                    tokens,
                    60,
                    1,
                    now_iso,
                    now_iso,
                ),
            )
            await db.commit()

        return await self.get_agent_llm_config(norm_id)

    def get_marketing_preset(
        self,
        marketing_type: str | MarketingType,
        project_id: str = "",
        project_name: str | None = None,
    ) -> ProjectMarketingProfile:
        """Helper on store instance to retrieve a marketing archetype preset."""
        return get_marketing_preset(
            marketing_type, project_id=project_id, project_name=project_name
        )

    async def list_marketing_projects(self) -> list[dict[str, Any]]:
        """List marketing configuration summaries for all registered projects."""
        await self.init_db()
        results: list[dict[str, Any]] = []
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(
                """
                SELECT project_id, config_json, updated_at
                FROM project_marketing_configs
                ORDER BY updated_at DESC;
                """
            ) as cursor:
                rows = await cursor.fetchall()
                for pid, c_json, updated_at in rows:
                    try:
                        prof = ProjectMarketingProfile.model_validate_json(c_json)
                        results.append(
                            {
                                "project_id": prof.project_id,
                                "project_name": prof.project_name,
                                "marketing_enabled": prof.marketing_enabled,
                                "marketing_type": prof.marketing_type,
                                "include_growth_agent": prof.include_growth_agent,
                                "include_sales_analytics_agent": prof.include_sales_analytics_agent,
                                "active_channels": [
                                    c.channel_id for c in prof.channels if c.enabled
                                ],
                                "active_tools": [t.tool_id for t in prof.tools if t.enabled],
                                "last_execution_status": prof.last_execution_status,
                                "last_executed_at": prof.last_executed_at,
                                "updated_at": updated_at,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Error parsing marketing profile %s: %s", pid, exc)
        return results

    async def get_project_marketing_config(
        self, project_id: str
    ) -> ProjectMarketingProfile:
        """Retrieve stored marketing configuration for a project, or default preset."""
        await self.init_db()
        async with aiosqlite.connect(str(self.db_path)) as db:
            async with db.execute(
                "SELECT config_json FROM project_marketing_configs WHERE project_id = ?;",
                (project_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    try:
                        return ProjectMarketingProfile.model_validate_json(row[0])
                    except Exception as exc:
                        logger.warning("Invalid JSON in marketing config %s: %s", project_id, exc)
        return get_marketing_preset("saas_b2b", project_id=project_id)

    def get_project_marketing_config_sync(
        self, project_id: str
    ) -> ProjectMarketingProfile:
        """Synchronously query marketing config for fast router decision in LangGraph."""
        if not Path(self.db_path).exists():
            return get_marketing_preset("saas_b2b", project_id=project_id)
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS project_marketing_configs (
                        project_id TEXT PRIMARY KEY,
                        config_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                cursor.execute(
                    "SELECT config_json FROM project_marketing_configs WHERE project_id = ?;",
                    (project_id,),
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return ProjectMarketingProfile.model_validate_json(row[0])
        except Exception as exc:
            logger.warning("Sync marketing fetch error for %s: %s", project_id, exc)
        return get_marketing_preset("saas_b2b", project_id=project_id)

    async def save_project_marketing_config(
        self, project_id: str, profile: ProjectMarketingProfile
    ) -> ProjectMarketingProfile:
        """Persist or update marketing profile for a project."""
        await self.init_db()
        profile.project_id = project_id
        now_iso = datetime.now(UTC).isoformat()
        config_json = profile.model_dump_json()
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO project_marketing_configs (
                    project_id, config_json, updated_at
                ) VALUES (?, ?, ?);
                """,
                (project_id, config_json, now_iso),
            )
            await db.commit()
        return profile

    async def apply_preset_to_project(
        self, project_id: str, marketing_type: str
    ) -> ProjectMarketingProfile:
        """Apply marketing preset to a project while retaining configured credentials/handles."""
        current = await self.get_project_marketing_config(project_id)
        new_preset = get_marketing_preset(
            marketing_type,
            project_id=project_id,
            project_name=current.project_name,
        )

        # Merge channels preserving custom credentials, handle/url and instructions
        existing_channels = {ch.channel_id: ch for ch in current.channels}
        for ch in new_preset.channels:
            if ch.channel_id in existing_channels:
                old = existing_channels[ch.channel_id]
                if old.account_handle_or_url:
                    ch.account_handle_or_url = old.account_handle_or_url
                if old.credentials:
                    ch.credentials = {**ch.credentials, **old.credentials}
                if old.custom_instructions:
                    ch.custom_instructions = old.custom_instructions

        # Merge tools preserving custom credentials and project settings
        existing_tools = {t.tool_id: t for t in current.tools}
        for t in new_preset.tools:
            if t.tool_id in existing_tools:
                old = existing_tools[t.tool_id]
                if old.credentials:
                    t.credentials = {**t.credentials, **old.credentials}
                if old.settings:
                    t.settings = {**t.settings, **old.settings}

        if current.brand_voice:
            new_preset.brand_voice = current.brand_voice
        if current.target_audience:
            new_preset.target_audience = current.target_audience
        if current.language:
            new_preset.language = current.language

        return await self.save_project_marketing_config(project_id, new_preset)

    async def test_marketing_tool(
        self, project_id: str, tool_id: str
    ) -> MarketingToolTestResponse:
        """Diagnose connection or credentials for an individual marketing tool in a project."""
        from app.services.marketing_tools import test_project_marketing_tool

        profile = await self.get_project_marketing_config(project_id)
        matching_tools = [t for t in profile.tools if t.tool_id == tool_id]
        if not matching_tools:
            return MarketingToolTestResponse(
                project_id=project_id,
                tool_id=tool_id,
                success=False,
                status="error",
                message=f"Herramienta '{tool_id}' no encontrada en el perfil del proyecto.",
            )
        tool = matching_tools[0]
        return await test_project_marketing_tool(project_id, tool, profile.channels)

