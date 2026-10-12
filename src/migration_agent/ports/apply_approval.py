"""Human review, signature, storage, and safe file mutation application boundaries."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from migration_agent.domain.apply_approval import (
    ApplyApprovalRecord,
    HumanDecision,
    ReviewRequestPayload,
)
from migration_agent.domain.changeset import ApplyResult, ChangeSet
from migration_agent.domain.execution import ExecutionProvenance
from migration_agent.domain.host_workflow import (
    BackupEntry,
    RepairProposal,
    ValidationExecution,
    WorkflowRecord,
    WriterLease,
)
from migration_agent.domain.validation import ValidationCommand, ValidationResult


class ApprovalStorePort(Protocol):
    def save_apply_approval(self, record: ApplyApprovalRecord, lease: WriterLease) -> None: ...
    def get_apply_approval(self, nonce: str) -> ApplyApprovalRecord: ...
    def consume_apply_approval(self, nonce: str, lease: WriterLease) -> None: ...
    def save_validation_execution(
        self, execution: ValidationExecution, lease: WriterLease
    ) -> str: ...
    def get_validation_execution(self, digest: str) -> ValidationExecution: ...


class ApprovalProofPort(Protocol):
    def sign(self, record: ApplyApprovalRecord) -> str: ...
    def verify(self, record: ApplyApprovalRecord, root_commit: str) -> bool: ...


class HumanReviewPort(Protocol):
    def confirm(self, review: ReviewRequestPayload) -> HumanDecision: ...


class FencedLockPort(Protocol):
    def acquire(self, project_id: str) -> AbstractContextManager[None]: ...
    def verify(self) -> None: ...


class ControlledFilesPort(Protocol):
    @property
    def destination_root(self) -> str | None: ...
    def bind_destination(self, changeset: ChangeSet) -> ChangeSet: ...
    def verify_destination(self, changeset: ChangeSet) -> None: ...
    def lock_identity(self, project_id: str) -> str: ...
    def materialize(
        self, changeset: ChangeSet, workspace_id: str, fence: Callable[[], None]
    ) -> Path: ...
    def verify_staging(self, path: str, changeset: ChangeSet) -> str: ...
    def prepare_backup(
        self, changeset: ChangeSet, fence: Callable[[], None]
    ) -> tuple[Path, tuple[BackupEntry, ...]]: ...
    def apply_files(
        self, record: WorkflowRecord, changeset: ChangeSet, fence: Callable[[], None]
    ) -> ApplyResult: ...
    def review_diff(self, changeset: ChangeSet) -> str: ...


class FencedValidationPort(Protocol):
    def run(
        self, command: ValidationCommand, working_dir: Path, fence: Callable[[], None]
    ) -> ValidationResult: ...


class ExecutionGatePort(FencedValidationPort, Protocol):
    def prepare(
        self, record: WorkflowRecord, commands: tuple[ValidationCommand, ...], lease: WriterLease
    ) -> ExecutionProvenance: ...
    def completed(
        self,
        provenance: ExecutionProvenance,
        record: WorkflowRecord,
        fence: Callable[[], None] | None = None,
    ) -> ExecutionProvenance: ...
    def verify_execution(
        self,
        execution: ValidationExecution,
        record: WorkflowRecord,
        fence: Callable[[], None] | None = None,
    ) -> None: ...


class SourceApplyPort(Protocol):
    def apply(self, plan_id: str, step_id: str, changeset_id: str) -> ApplyResult: ...


class StagedWorkflowPort(Protocol):
    def verify_source(self) -> None: ...
    def prepare(self, plan_id: str, step_id: str, skip_validation: bool) -> WorkflowRecord: ...
    def current_changeset(self, changeset_id: str) -> ChangeSet: ...
    def submit_repair(self, proposal: RepairProposal) -> WorkflowRecord: ...
