"""Application configuration module using Pydantic Settings."""

import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.routing import AgentID

# Automatically load .env into os.environ for LangSmith, LangChain, and other libraries
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)
else:
    load_dotenv()


class Settings(BaseSettings):
    """Central settings for the Software Factory LangGraph Backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GEMINI_API_KEY: str = "dummy-key-for-tests"
    USE_MOCK_LLM: bool = False
    DEFAULT_LLM_MODEL: str = "gemini-3.5-flash"
    LLM_INPUT_COST_PER_MILLION: float = 0.35
    LLM_OUTPUT_COST_PER_MILLION: float = 1.05
    AGENT_MODEL_OVERRIDES: dict[str, str] = {}
    RATE_LIMIT_DELAY_SECONDS: float = 4.0
    MAX_RETRIES_PER_GATE: int = 3
    CHECKPOINT_DB_PATH: str = "workspaces/checkpoints.sqlite"
    OFFICE_DB_PATH: str = "workspaces/office_data.sqlite"
    WORKSPACES_DIR: str = "workspaces"
    PROMPTS_DIR: str = "prompts"
    NOTION_API_KEY: str | None = None
    NOTION_PARENT_PAGE_ID: str | None = None
    NOTION_CEO_DATABASE_ID: str | None = None
    RESEND_API_KEY: str | None = None
    FOUNDER_ALERT_EMAIL: str | None = None
    TAVILY_API_KEY: str | None = None
    NOTION_MCP_ENABLED: bool = False
    REAL_MAIL_ENABLED: bool = False
    SMTP_HOST: str = "smtp.strato.com"
    SMTP_PORT: int = 465
    IMAP_HOST: str = "imap.strato.com"
    IMAP_PORT: int = 993
    MAIL_USERNAME: str | None = None
    MAIL_PASSWORD: str | None = None
    GITHUB_TOKEN: str | None = None
    GITHUB_USERNAME: str | None = None
    VERCEL_TOKEN: str | None = None
    VERCEL_TEAM_ID: str | None = None
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "agentoffice"
    LANGSMITH_ENDPOINT: str = "https://eu.api.smith.langchain.com"

    @field_validator("AGENT_MODEL_OVERRIDES", mode="before")
    @classmethod
    def parse_agent_overrides(cls, value: object) -> object:
        """Parse JSON string format if supplied via environment variables."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return {}
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {}
        return value

    def get_agent_temperature(self, agent_id: AgentID) -> float:
        """Return the exact temperature allocated for each agent role."""
        match agent_id:
            case AgentID.AGENTE_01_PM | AgentID.AGENTE_08_DOCS:
                return 0.2
            case AgentID.AGENTE_09_GROWTH:
                return 0.4
            case _:
                return 0.1

    def get_agent_model(self, agent_id: AgentID) -> str:
        """Return the model override if registered, otherwise DEFAULT_LLM_MODEL."""
        if agent_id.value in self.AGENT_MODEL_OVERRIDES:
            return self.AGENT_MODEL_OVERRIDES[agent_id.value]
        if agent_id.name in self.AGENT_MODEL_OVERRIDES:
            return self.AGENT_MODEL_OVERRIDES[agent_id.name]
        return self.DEFAULT_LLM_MODEL


settings = Settings()
