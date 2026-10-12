"""Environment-backed application configuration."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from migration_agent.domain.execution import ValidationMode
from migration_agent.domain.inspection_access import InspectionCapability
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.workflow_access import WorkflowCapability


class Settings(BaseSettings):
    """Configuration that is safe to load for local, offline commands."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

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
    final_target_root: Path | None = Field(default=None, validation_alias="AGENT_FINAL_TARGET_ROOT")
    validation_catalog: Literal["node-v1", "node-vitest-v1", "node-angular-v21"] = "node-v1"

    mcp_trusted_local_reads: bool = Field(
        default=True,
        validation_alias="AGENT_MCP_TRUSTED_LOCAL_READS",
        description="Whether the trusted local stdio launcher grants Mode B inspection.",
    )
    mcp_read_capabilities: frozenset[InspectionCapability] = Field(
        default=frozenset(InspectionCapability),
        validation_alias="AGENT_MCP_READ_CAPABILITIES",
        description="Inspection-only grants controlled by the local server launcher.",
    )
    mcp_workflow_capabilities: frozenset[WorkflowCapability] = Field(
        default=frozenset(WorkflowCapability),
        validation_alias="AGENT_MCP_WORKFLOW_CAPABILITIES",
        description="Workflow grants resolved by the trusted local launcher; never tool arguments.",
    )
    trust_root: Path | None = Field(default=None, validation_alias="AGENT_TRUST_ROOT")
    local_config_root: Path | None = Field(default=None, validation_alias="AGENT_LOCAL_CONFIG_ROOT")
    validation_image: str | None = Field(default=None, validation_alias="AGENT_VALIDATION_IMAGE")
    validation_mode: ValidationMode | None = Field(
        default=None, validation_alias="AGENT_VALIDATION_MODE"
    )
    native_toolchain_root: Path | None = Field(
        default=None, validation_alias="AGENT_NATIVE_TOOLCHAIN_ROOT"
    )
    native_dependencies_root: Path | None = Field(
        default=None, validation_alias="AGENT_NATIVE_DEPENDENCIES_ROOT"
    )

    @property
    def effective_validation_mode(self) -> ValidationMode:
        return self.validation_mode or (
            ValidationMode.CONTAINER if self.validation_image else ValidationMode.RESTRICTED
        )

    native_browser_path: Path | None = Field(
        default=None, validation_alias="AGENT_NATIVE_BROWSER_PATH"
    )
    browser_validation_plan: Path | None = Field(
        default=None, validation_alias="AGENT_BROWSER_VALIDATION_PLAN"
    )
    browser_review_mode: Literal["host", "provider"] = Field(
        default="host", validation_alias="AGENT_BROWSER_REVIEW_MODE"
    )
    browser_provider_export: bool = Field(
        default=False,
        validation_alias="AGENT_BROWSER_PROVIDER_EXPORT",
        description="Trusted launcher opt-in to disclose bounded visual evidence and staged code.",
    )

    apply_minimum_assurance: AssuranceLevel = Field(
        default=AssuranceLevel.MODE_B, validation_alias="AGENT_APPLY_MINIMUM_ASSURANCE"
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
