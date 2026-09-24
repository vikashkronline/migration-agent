"""Domain models for execution state tracking, resumability, and run lifecycles."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStep(StrEnum):
    """Execution stages of an operational migration run."""

    INITIALIZED = "INITIALIZED"
    STAGED = "STAGED"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class RunRecord(BaseModel):
    """Durable operational state of a migration run persisted across process crashes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    source_root: str = Field(min_length=1)
    staging_root: str | None = None
    status: ExecutionStep = ExecutionStep.INITIALIZED
    current_step_id: str | None = None
    applied_changeset_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunSummary(BaseModel):
    """Lightweight projection of a migration run for listing and inspection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    plan_id: str
    status: ExecutionStep
    source_root: str
    staging_root: str | None = None
    created_at: datetime
    updated_at: datetime
