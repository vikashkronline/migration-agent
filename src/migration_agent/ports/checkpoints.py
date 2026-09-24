"""Ports for operational checkpoints, state persistence, and audit logging."""

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain import (
    ApprovalSignature,
    ChangeSet,
    ExecutionStep,
    MigrationPlan,
    MigrationRunReport,
    RunRecord,
)


class OperationalCheckpoint(BaseModel):
    """Operational checkpoint record tracking execution state and recovery."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    checkpoint_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    checkpoint_type: str = Field(min_length=1)
    step_id: str | None = None
    state_data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditEvent(BaseModel):
    """Append-only audit event capturing important actions, decisions, and approvals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


class CheckpointPort(Protocol):
    """Boundary for canonical SQLite operational state and checkpoint persistence."""

    def save_plan(self, plan: MigrationPlan) -> None:
        """Persist or update a migration plan in the operational database."""

    def get_plan(self, plan_id: str) -> MigrationPlan | None:
        """Retrieve a migration plan by its unique ID."""

    def list_plans(self) -> list[MigrationPlan]:
        """List all migration plans recorded in the database."""

    def save_approval(self, plan_id: str, approval: ApprovalSignature) -> None:
        """Record an approval signature bound to a plan."""

    def save_checkpoint(self, checkpoint: OperationalCheckpoint) -> None:
        """Record an operational checkpoint."""

    def list_checkpoints(self, run_id: str) -> list[OperationalCheckpoint]:
        """List all checkpoints associated with a given run ID."""

    def save_changeset(self, changeset: ChangeSet) -> None:
        """Persist a ChangeSet in the operational database."""

    def get_changeset(self, changeset_id: str) -> ChangeSet | None:
        """Retrieve a ChangeSet by its unique ID."""

    def save_run_report(self, report: MigrationRunReport) -> None:
        """Persist a migration run report in the operational database."""

    def get_run_report(self, run_id: str) -> MigrationRunReport | None:
        """Retrieve a migration run report by its run ID."""

    def save_run_record(self, run: RunRecord) -> None:
        """Persist or update a migration run state record."""

    def get_run_record(self, run_id: str) -> RunRecord | None:
        """Retrieve a migration run record by its unique run ID."""

    def list_run_records(self) -> list[RunRecord]:
        """List all recorded migration runs."""

    def update_run_status(
        self,
        run_id: str,
        status: ExecutionStep,
        current_step_id: str | None = None,
        applied_changeset_id: str | None = None,
    ) -> None:
        """Update the operational status and progress of a run."""


class AuditLogPort(Protocol):
    """Boundary for recording append-only audit events."""

    def record_event(self, event: AuditEvent) -> None:
        """Record an audit event to the append-only audit log."""

    def get_events(self, run_id: str) -> list[AuditEvent]:
        """Retrieve all audit events associated with a run in chronological order."""

    def verify_audit_log(self, run_id: str) -> bool:
        """Verify the integrity and chronological sequence of audit events for a run."""
