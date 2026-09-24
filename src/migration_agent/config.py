"""Environment-backed application configuration."""

from pathlib import Path

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

    state_dir: Path | None = Field(
        default=None,
        validation_alias="AGENT_STATE_DIR",
        description="Directory for local SQLite operational checkpoints and audit logging.",
    )

    max_step_files: int = Field(
        default=10,
        validation_alias="AGENT_MAX_STEP_FILES",
        description="Maximum number of expected files allowed in a single migration step.",
    )

    staging_root: Path | None = Field(
        default=None,
        validation_alias="AGENT_STAGING_ROOT",
        description="Root directory for isolated staging workspaces.",
    )

    @property
    def effective_model(self) -> str | None:
        """Return the effective model from either canonical or legacy configuration."""
        return self.runtime_model or self.agent_model

    def resolve_state_dir(self, override: Path | None = None) -> Path:
        """Resolve effective state directory for SQLite checkpoints and audit logging."""
        if override is not None:
            return override
        if self.state_dir is not None:
            return self.state_dir
        return Path.home() / ".agent-platform" / "state"

    def resolve_staging_root(self, override: Path | None = None) -> Path:
        """Resolve effective staging root for isolated workspaces."""
        if override is not None:
            return override
        if self.staging_root is not None:
            return self.staging_root
        return Path.home() / ".agent-platform" / "staging"
