"""Environment-backed application configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration that is safe to load for local, offline commands."""

    model_config = SettingsConfigDict(extra="ignore")

    runtime_provider: str = Field(
        default="gemini",
        validation_alias="AGENT_RUNTIME_PROVIDER",
        description="Default runtime provider ('gemini' or 'openai').",
    )

    runtime_model: str | None = Field(
        default=None,
        validation_alias="AGENT_RUNTIME_MODEL",
        description="Model identifier for the configured runtime provider.",
    )

    agent_model: str | None = Field(
        default=None,
        validation_alias="MIGRATION_AGENT_MODEL",
        description="Legacy model identifier for backward compatibility.",
    )

    @property
    def effective_model(self) -> str | None:
        """Return the effective model from either canonical or legacy configuration."""
        return self.runtime_model or self.agent_model
