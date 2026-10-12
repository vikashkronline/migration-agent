"""Typed host proposals, durable operations, and the Phase 16 execution lifecycle."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)

from migration_agent.domain.analysis import AnalysisFinding
from migration_agent.domain.browser_validation import BrowserEvidence
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import DestinationBinding, FileOperation
from migration_agent.domain.configuration import ConfigurationSnapshot
from migration_agent.domain.execution import ExecutionProvenance
from migration_agent.domain.planning import MigrationStep
from migration_agent.domain.validation import ValidationResult


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Lifecycle(StrEnum):
    PLAN_SAVED = "PLAN_SAVED"
    STAGE_VERIFIED = "STAGE_VERIFIED"
    VALIDATION_RUNNING = "VALIDATION_RUNNING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    REPAIRING = "REPAIRING"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVAL_RECORDED = "APPROVAL_RECORDED"
    APPLY_INTENT = "APPLY_INTENT"
    APPLY_COMPLETED = "APPLY_COMPLETED"
    BASE_CHANGED = "BASE_CHANGED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


TRANSITIONS: dict[Lifecycle, frozenset[Lifecycle]] = {
    Lifecycle.PLAN_SAVED: frozenset({Lifecycle.STAGE_VERIFIED}),
    Lifecycle.STAGE_VERIFIED: frozenset({Lifecycle.VALIDATION_RUNNING}),
    Lifecycle.VALIDATION_RUNNING: frozenset(
        {Lifecycle.VALIDATION_FAILED, Lifecycle.VALIDATION_PASSED}
    ),
    Lifecycle.VALIDATION_FAILED: frozenset({Lifecycle.REPAIRING, Lifecycle.VALIDATION_RUNNING}),
    Lifecycle.REPAIRING: frozenset({Lifecycle.STAGE_VERIFIED}),
    Lifecycle.VALIDATION_PASSED: frozenset(
        {Lifecycle.APPROVAL_PENDING, Lifecycle.VALIDATION_RUNNING}
    ),
    Lifecycle.APPROVAL_PENDING: frozenset(
        {Lifecycle.APPROVAL_RECORDED, Lifecycle.VALIDATION_RUNNING}
    ),
    Lifecycle.APPROVAL_RECORDED: frozenset(
        {Lifecycle.APPLY_INTENT, Lifecycle.APPROVAL_PENDING, Lifecycle.VALIDATION_RUNNING}
    ),
    Lifecycle.APPLY_INTENT: frozenset({Lifecycle.APPLY_COMPLETED, Lifecycle.RECOVERY_REQUIRED}),
    Lifecycle.APPLY_COMPLETED: frozenset(),
    Lifecycle.BASE_CHANGED: frozenset(),
    Lifecycle.RECOVERY_REQUIRED: frozenset({Lifecycle.BASE_CHANGED, Lifecycle.APPLY_COMPLETED}),
}

QUIESCENT = frozenset(
    {
        Lifecycle.PLAN_SAVED,
        Lifecycle.STAGE_VERIFIED,
        Lifecycle.VALIDATION_PASSED,
        Lifecycle.APPROVAL_RECORDED,
        Lifecycle.APPLY_COMPLETED,
    }
)


def validate_transition(previous: Lifecycle, following: Lifecycle) -> None:
    if following == Lifecycle.BASE_CHANGED and previous not in {
        Lifecycle.APPLY_INTENT,
        Lifecycle.APPLY_COMPLETED,
        Lifecycle.RECOVERY_REQUIRED,
        Lifecycle.BASE_CHANGED,
    }:
        return
    if following not in TRANSITIONS[previous]:
        raise ValueError("INVALID_TRANSITION: lifecycle transition is not permitted.")


def normalized_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value != path.as_posix()
        or path.is_absolute()
        or ".." in path.parts
        or ":" in value
        or "\\" in value
        or "\x00" in value
        or any(part.startswith(".") for part in path.parts)
    ):
        raise ValueError("INVALID_PATH: expected a non-hidden repository-relative POSIX path.")
    if path.parts[0].casefold() in {"node_modules", "dist", "build", "venv", "env"}:
        raise ValueError("INVALID_PATH: ignored path is outside allowed scope.")
    return value


class RepositoryState(WorkflowModel):
    revision: str
    root_commit: str
    fingerprint: str
    clean: bool
    dirty_paths: tuple[str, ...] = ()


class EvidenceCitation(WorkflowModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    line: int = Field(default=1, ge=1)
    symbol: str | None = Field(default=None, min_length=1, max_length=128)

    _path = field_validator("path")(normalized_path)


class EvidenceExcerpt(WorkflowModel):
    path: str
    sha256: str
    line: int
    text: str
    has_more: bool


class AnalysisProposal(WorkflowModel):
    base_revision: str
    worktree_fingerprint: str
    summary: str = Field(min_length=1, max_length=8192)
    findings: tuple[AnalysisFinding, ...] = Field(min_length=1, max_length=100)
    citations: tuple[EvidenceCitation, ...] = Field(min_length=1, max_length=100)


class PlanProposal(WorkflowModel):
    base_revision: str
    worktree_fingerprint: str
    analysis_id: str
    steps: tuple[MigrationStep, ...] = Field(min_length=1, max_length=100)
    citations: tuple[EvidenceCitation, ...] = Field(min_length=1, max_length=100)


class RepairFile(WorkflowModel):
    path: str
    text: str = Field(max_length=32768)

    _path = field_validator("path")(normalized_path)


class RepairProposal(WorkflowModel):
    plan_id: str
    step_id: str
    changeset_id: str
    diagnostic_digest: str
    files: tuple[RepairFile, ...] = Field(min_length=1, max_length=100)


class ImplementationFile(RepairFile):
    operation: FileOperation = FileOperation.CREATE


class ImplementationProposal(WorkflowModel):
    plan_id: str
    step_id: str
    base_revision: str
    worktree_fingerprint: str
    destination: DestinationBinding
    architecture_digest: str
    citations: tuple[EvidenceCitation, ...] = Field(min_length=1, max_length=100)
    files: tuple[ImplementationFile, ...] = Field(min_length=1, max_length=100)


class ImplementationContext(WorkflowModel):
    plan_id: str
    step_id: str
    base_revision: str
    worktree_fingerprint: str
    destination: DestinationBinding
    architecture_digest: str
    citations: tuple[EvidenceCitation, ...]
    source: tuple[EvidenceExcerpt, ...]
    target_files: tuple[str, ...]
    target_base: tuple[RepairFile, ...]
    acceptance_criteria: tuple[str, ...]


class OperationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


TERMINAL_OPERATIONS = frozenset(
    {
        OperationStatus.SUCCEEDED,
        OperationStatus.FAILED,
        OperationStatus.CANCELLED,
        OperationStatus.RECOVERY_REQUIRED,
    }
)


class Operation(WorkflowModel):
    schema_version: Literal[1] = 1
    operation_id: str
    project_id: str
    request_id: str
    kind: str
    payload_digest: str
    status: OperationStatus = OperationStatus.QUEUED
    actor: str
    principal_id: str | None = None
    access_digest: str | None = None
    capability: str | None = None
    configuration_snapshot: ConfigurationSnapshot | None = None
    plan_id: str | None = None
    step_id: str | None = None
    changeset_id: str | None = None
    analysis_id: str | None = None
    message: str = "Queued"
    completed_units: int = 0
    total_units: int = 0
    output_tail: str = ""
    poll_interval_seconds: int = 2
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WriterLease(WorkflowModel):
    project_id: str
    owner: str
    generation: int = Field(ge=1)
    expires_at: float


class BackupEntry(WorkflowModel):
    path: str
    existed: bool
    digest: str | None = None
    mode: int = 0o644


class WorkflowRecord(WorkflowModel):
    schema_version: Literal[1] = 1
    project_id: str
    source_root: str
    run_id: str
    plan_id: str
    step_id: str
    state: Lifecycle = Lifecycle.PLAN_SAVED
    version: int = 0
    base_revision: str
    root_commit: str
    worktree_fingerprint: str
    policy_digest: str
    plan_digest: str = ""
    changeset_id: str | None = None
    changeset_digest: str | None = None
    staging_path: str | None = None
    staging_fingerprint: str | None = None
    validation_results: tuple[ValidationResult, ...] = ()
    validation_digest: str | None = None
    browser_evidence: BrowserEvidence | None = None
    browser_repair_count: int = Field(default=0, ge=0)
    approval_nonce: str | None = None
    backup_path: str | None = None
    backups: tuple[BackupEntry, ...] = ()
    generation: int | None = None
    recovery_note: str = ""
    destination: DestinationBinding | None = None
    architecture_digest: str | None = None

    @property
    def transferable(self) -> bool:
        return self.state in QUIESCENT


class StepStatus(WorkflowModel):
    step_id: str
    state: Lifecycle
    transferable: bool
    changeset_id: str | None
    changeset_digest: str | None
    validation_digest: str | None
    validation_backend: str = "unsupported"
    native_consent_id: str | None = None
    browser_status: str = "NOT_RUN"
    browser_capture_id: str | None = None
    e2e_status: str = "NOT_RUN"
    diagnostic_digest: str
    diagnostics: tuple[str, ...] = ()


class OperationView(WorkflowModel):
    operation: Operation
    repository: RepositoryState
    steps: tuple[StepStatus, ...] = ()


class ValidationExecution(WorkflowModel):
    schema_version: Literal[1, 2, 3] = 1
    provenance: ExecutionProvenance | None = None
    browser_evidence: BrowserEvidence | None = None
    project_id: str
    plan_id: str
    step_id: str
    changeset_id: str
    changeset_digest: str
    staging_fingerprint: str
    results: tuple[ValidationResult, ...]
    completed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_serializer(mode="wrap")
    def compatible_serialization(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = cast(dict[str, Any], handler(self))
        if self.schema_version < 3 and self.browser_evidence is None:
            data.pop("browser_evidence", None)
        return data


def workflow_diagnostic_digest(record: WorkflowRecord) -> str:
    commands = [result.model_dump(mode="json") for result in record.validation_results]
    return compute_canonical_digest(
        commands
        if record.browser_evidence is None
        else {"commands": commands, "browser": record.browser_evidence.model_dump(mode="json")}
    )
