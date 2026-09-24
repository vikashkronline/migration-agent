"""Ports for Git-governed project manifests, safety policies, and plan exports."""

from datetime import UTC, datetime
from typing import Protocol

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
    default_mode: str = "MODE_B"
    protected_paths: list[str] = Field(default_factory=lambda: [".agent/**", ".git/**"])
    max_step_files: int = 10
    require_approval_for_apply: bool = True


class GovernancePort(Protocol):
    """Boundary for managing Git-native governance metadata in .agent/."""

    def ensure_governance_layout(self, project_root: str, project_id: str | None = None) -> None:
        """Ensure .agent/ manifest and policy files exist with default configuration."""

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
