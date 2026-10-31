"""Application configuration module using Pydantic Settings."""

import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.routing import AgentID


class Settings(BaseSettings):
    """Central settings for the Software Factory LangGraph Backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GEMINI_API_KEY: str = "dummy-key-for-tests"
    USE_MOCK_LLM: bool = False
    DEFAULT_LLM_MODEL: str = "gemini-2.5-flash"
    AGENT_MODEL_OVERRIDES: dict[str, str] = {}
    RATE_LIMIT_DELAY_SECONDS: float = 4.0
    MAX_RETRIES_PER_GATE: int = 3
    CHECKPOINT_DB_PATH: str = "workspaces/checkpoints.sqlite"
    OFFICE_DB_PATH: str = "workspaces/office_data.sqlite"
    WORKSPACES_DIR: str = "workspaces"
    PROMPTS_DIR: str = "prompts"

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
