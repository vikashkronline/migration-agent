"""Framework-neutral domain contracts introduced in Phase 0."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MigrationRequest(BaseModel):
    """A request to assess or migrate one source repository."""

    model_config = ConfigDict(frozen=True)

    source_path: Path
    source_framework: str = Field(min_length=1)
    target_framework: str = Field(min_length=1)
    dry_run: bool = True

    @field_validator("source_framework", "target_framework")
    @classmethod
    def normalize_framework_name(cls, value: str) -> str:
        """Reject blank names while keeping framework identity adapter-neutral."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("framework name must not be blank")
        return normalized
