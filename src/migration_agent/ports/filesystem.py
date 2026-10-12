"""Read-only filesystem inspection port."""

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain import RepositorySnapshot


class InspectionPolicy(BaseModel):
    """Explicit bounds for safe repository inspection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_text_file_bytes: int = Field(default=5_000_000, gt=0)
    max_text_files: int = Field(default=10_000, gt=0)
    max_total_text_bytes: int = Field(default=50_000_000, gt=0)
    ignored_directory_names: tuple[str, ...] = (
        ".git",
        ".mypy_cache",
        ".next",
        ".nuxt",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "build",
        "coverage",
        "dist",
        "env",
        "node_modules",
        "out",
        "tmp",
        "venv",
    )


class FilesystemInspectorPort(Protocol):
    """Boundary for deterministic, read-only repository inspection."""

    def inspect(self, root: Path, policy: InspectionPolicy) -> RepositorySnapshot:
        """Inspect eligible files beneath root without mutating the repository."""
