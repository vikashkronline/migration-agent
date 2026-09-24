"""Application-owned ports for isolated staging workspace management."""

from pathlib import Path
from typing import Protocol

from migration_agent.domain import ChangeSet


class WorkspacePort(Protocol):
    """Boundary for isolated staging workspace creation, isolation, and materialization."""

    def create_staging(
        self,
        run_id: str,
        source_root: Path,
        staging_root: Path,
    ) -> Path:
        """Create an isolated staging replica of the source repository."""

    def apply_changeset(
        self,
        workspace_path: Path,
        changeset: ChangeSet,
    ) -> None:
        """Materialize proposed ChangeSet mutations directly within the staging workspace."""

    def cleanup_staging(
        self,
        workspace_path: Path,
    ) -> None:
        """Safely destroy an isolated staging workspace."""
