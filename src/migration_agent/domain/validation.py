"""Domain models for validation profiles, command specifications, repair loops, and run reports."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ValidationProfile(StrEnum):
    """Supported validation profile dimensions."""

    LINT = "LINT"
    TYPECHECK = "TYPECHECK"
    TEST = "TEST"
    BUILD = "BUILD"


class ValidationStatus(StrEnum):
    """Outcomes of executing a validation command."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    DISALLOWED = "DISALLOWED"


class ValidationCommand(BaseModel):
    """Allowlisted command execution template for validation checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    executable: str = Field(min_length=1)
    args: tuple[str, ...] = Field(default_factory=tuple)
    profile: ValidationProfile
    timeout_seconds: int = Field(default=60, ge=1)
    max_output_bytes: int = Field(default=65536, ge=1)

    @property
    def rendered_command(self) -> str:
        """Return the space-separated rendered command string."""
        return " ".join([self.executable, *self.args])


class ValidationResult(BaseModel):
    """Immutable result of executing a validation check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str = Field(min_length=1)
    profile: ValidationProfile
    status: ValidationStatus
    exit_code: int | None = None
    duration_ms: int = Field(default=0, ge=0)
    sanitized_output: str = Field(default="")
    output_digest: str = Field(default="")
    diagnostics: tuple[str, ...] = Field(default_factory=tuple)


class RepairAttempt(BaseModel):
    """Record of an automated self-repair attempt within a bounded repair loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_index: int = Field(ge=1)
    cited_diagnostic: str = Field(min_length=1)
    previous_changeset_digest: str = Field(min_length=1)
    new_changeset_digest: str = Field(min_length=1)
    status: ValidationStatus
    summary: str = Field(default="")


class RunStatus(StrEnum):
    """Terminal status of an end-to-end migration run."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class MigrationRunReport(BaseModel):
    """Comprehensive, reproducible audit summary of a complete migration run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    source_root: str = Field(min_length=1)
    staging_root: str | None = None
    status: RunStatus
    validation_results: tuple[ValidationResult, ...] = Field(default_factory=tuple)
    repair_attempts: tuple[RepairAttempt, ...] = Field(default_factory=tuple)
    applied_changeset_id: str | None = None
    applied_changeset_digest: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: str = Field(default="")
