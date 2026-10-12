"""Ports for Git-governed project manifests, safety policies, and plan exports."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain import MigrationPlan


class ProjectManifest(BaseModel):
    """Schema-versioned platform project manifest stored in .agent/manifest.json."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    platform_version: str = "0.1.0"
    project_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectPolicy(BaseModel):
    """Safety and execution policy stored in .agent/policy.json."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    default_mode: Literal["MODE_A", "MODE_B", "MODE_C"] = "MODE_B"
    protected_paths: list[str] = Field(default_factory=lambda: [".agent/**", ".git/**"])
    max_step_files: int = 10
    require_approval_for_apply: bool = True
    execution_mode: Literal["trusted", "container", "denied"] = "trusted"
    native_network: Literal["host", "none"] = "host"
    native_filesystem_isolation: bool = False
    native_hard_resource_limits: bool = False


class MigrationSession(BaseModel):
    """External session roots; declarations confer no execution or apply authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    source_root: Path
    project_root: Path
    staging_root: Path
    state_dir: Path


class GovernancePort(Protocol):
    """Boundary for managing Git-native governance metadata in .agent/."""

    def ensure_governance_layout(self, project_root: str, project_id: str | None = None) -> None:
        """Ensure .agent/ manifest, policies, access roles, and knowledge folders exist."""

    def get_manifest(self, project_root: str) -> ProjectManifest | None:
        """Load the platform project manifest from .agent/manifest.json."""

    def save_migration_session(self, session: MigrationSession) -> None:
        """Persist external roots idempotently, refusing an existing different binding."""

    def get_policy(self, project_root: str) -> ProjectPolicy:
        """Load the active safety policy for the project."""

    def get_policy_digest(self, project_root: str) -> str:
        """Compute the RFC 8785 canonical digest of the active project policy."""

    def export_plan(self, project_root: str, plan: MigrationPlan) -> str:
        """Export the migration plan to .agent/plans/<plan_id>.json.

        Returns:
            The absolute path of the exported plan file.
        """

    def load_plan(self, project_root: str, plan_id: str) -> MigrationPlan | None:
        """Load an exported migration plan by ID from .agent/plans/."""
