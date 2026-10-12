"""Shared staging, validation, exact human review, and non-bypassable source apply gates."""

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from pathlib import Path

from migration_agent.application.host_proposals import HostProposalService, opaque_id
from migration_agent.application.standards_review import StandardsReviewService
from migration_agent.application.transformation import TransformationService
from migration_agent.application.validator import RuleBasedPlanValidator
from migration_agent.domain.apply_approval import ApplyApprovalRecord, ReviewRequestPayload
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import (
    ApplyResult,
    ApplyStatus,
    ChangeSet,
    FileChange,
    FileOperation,
    compute_changeset_digest,
    compute_file_sha256,
)
from migration_agent.domain.host_workflow import (
    EvidenceCitation,
    EvidenceExcerpt,
    ImplementationContext,
    ImplementationProposal,
    Lifecycle,
    Operation,
    RepairFile,
    ValidationExecution,
    WorkflowRecord,
    WriterLease,
    normalized_path,
)
from migration_agent.domain.planning import AssuranceLevel, MigrationPlan, compute_plan_digest
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.rules import RuleRegistry, StandardsReviewReport
from migration_agent.domain.validation import ValidationCommand, ValidationProfile, ValidationStatus
from migration_agent.ports.apply_approval import (
    ApprovalProofPort,
    ApprovalStorePort,
    ControlledFilesPort,
    ExecutionGatePort,
    FencedLockPort,
    FencedValidationPort,
    HumanReviewPort,
)
from migration_agent.ports.browser_validation import BrowserValidationPort
from migration_agent.ports.rules import RuleEvaluatorPort


class ApplyService:
    def __init__(
        self,
        proposals: HostProposalService,
        transformation: TransformationService,
        approvals: ApprovalStorePort,
        files: ControlledFilesPort,
        lock: FencedLockPort,
        proof: ApprovalProofPort,
        required_assurance: AssuranceLevel = AssuranceLevel.MODE_B,
        review_options: tuple[str, ...] = (),
        execution_gate: ExecutionGatePort | None = None,
        browser_gate: BrowserValidationPort | None = None,
        foundation_contract: Callable[[], str] | None = None,
        foundation_paths: tuple[str, ...] = (),
    ) -> None:
        self.proposals = proposals
        self.transformation = transformation
        self.approvals = approvals
        self.files = files
        self.lock = lock
        self.proof = proof
        self.required_assurance = required_assurance
        if required_assurance == AssuranceLevel.MODE_C:
            raise ValueError("ASSURANCE_REQUIRED: apply cannot use Mode C.")
        self.review_options = review_options
        self.execution_gate = execution_gate
        self.browser_gate = browser_gate
        self.foundation_contract = foundation_contract
        self.foundation_paths = frozenset(foundation_paths)

    def ensure_plan(self, plan_id: str, lease: WriterLease) -> MigrationPlan:
        plan = self.proposals.checkpoints.get_plan(opaque_id(plan_id))
        if plan is None or Path(plan.source_root).resolve() != self.proposals.root:
            raise ValueError("PROJECT_MISMATCH: bound plan is unavailable.")
        policy = self.proposals.evidence.policy()
        validator = RuleBasedPlanValidator(policy.max_step_files)
        validation = validator.validate(plan, self.proposals.evidence.inventory())
        if not validation.is_valid or RedactionPolicy().contains_secret(plan.model_dump_json()):
            raise ValueError("PLAN_INVALID: regenerate a grounded valid migration plan.")
        state = self.proposals.evidence.repository_state()
        if not state.clean:
            raise ValueError("BASE_CHANGED: commit or discard source changes before staging.")
        for step in plan.steps:
            opaque_id(step.step_id)
            try:
                self.proposals.store.get_workflow(self.proposals.project_id, plan_id, step.step_id)
            except ValueError as error:
                if not str(error).startswith("WORKFLOW_NOT_FOUND"):
                    raise
                self.proposals.store.save_workflow(
                    WorkflowRecord(
                        project_id=self.proposals.project_id,
                        source_root=str(self.proposals.root),
                        plan_id=plan.plan_id,
                        run_id=plan.run_id,
                        step_id=step.step_id,
                        base_revision=state.revision,
                        root_commit=state.root_commit,
                        worktree_fingerprint=state.fingerprint,
                        policy_digest=self.proposals.evidence.policy_digest(),
                        plan_digest=compute_plan_digest(plan),
                    ),
                    lease,
                )
        return plan

    def _record(self, plan_id: str, step_id: str, lease: WriterLease) -> WorkflowRecord:
        record = self.proposals.store.get_workflow(
            self.proposals.project_id, opaque_id(plan_id), opaque_id(step_id)
        )
        if Path(record.source_root).resolve() != self.proposals.root:
            raise ValueError("PROJECT_MISMATCH: checkpoint is outside the bound source.")
        self.proposals.check_base(record, lease)
        if (
            record.architecture_digest
            and self.foundation_contract
            and record.architecture_digest != self.foundation_contract()
        ):
            raise ValueError(
                "ARCHITECTURE_CHANGED: regenerate a plan for the accepted foundation decisions."
            )
        plan = self.proposals.checkpoints.get_plan(record.plan_id)
        if plan is None or compute_plan_digest(plan) != record.plan_digest:
            self.proposals.store.save_workflow(
                record.model_copy(update={"state": Lifecycle.BASE_CHANGED}), lease
            )
            raise ValueError("BASE_CHANGED: plan identity changed; submit a fresh plan.")
        return record

    def _changeset(self, record: WorkflowRecord) -> ChangeSet:
        changeset = self.proposals.checkpoints.get_changeset(record.changeset_id or "")
        if (
            changeset is None
            or changeset.plan_id != record.plan_id
            or changeset.step_id != record.step_id
            or changeset.base_revision != record.base_revision
            or changeset.worktree_fingerprint != record.worktree_fingerprint
            or compute_changeset_digest(changeset) != record.changeset_digest
            or changeset.changeset_digest != record.changeset_digest
        ):
            raise ValueError("CHANGESET_INVALID: artifact identity or base binding changed.")
        if (
            changeset.destination != record.destination
            or changeset.architecture_digest != record.architecture_digest
        ):
            raise ValueError("DESTINATION_CHANGED: checkpoint and proposed target bindings differ.")
        self.files.verify_destination(changeset)
        self._verify_destination_head(changeset)
        policy = self.proposals.evidence.policy()
        paths: set[str] = set()
        plan = self.proposals.checkpoints.get_plan(record.plan_id)
        step = (
            next((item for item in plan.steps if item.step_id == record.step_id), None)
            if plan
            else None
        )
        if not changeset.changes or len(changeset.changes) > 100:
            raise ValueError("CHANGESET_INVALID: empty or oversized artifact.")
        total = 0
        for change in changeset.changes:
            normalized_path(change.path)
            if step and step.scope != "foundation" and change.path in self.foundation_paths:
                raise ValueError(
                    "FOUNDATION_SCOPE_REQUIRED: architecture-owned configuration need"
                    "s a reviewed foundation change."
                )
            if change.old_path is not None or change.path.casefold() in paths:
                raise ValueError("CHANGESET_INVALID: unsupported rename or duplicate path.")
            paths.add(change.path.casefold())
            if RedactionPolicy.is_sensitive_path(Path(change.path)) or any(
                fnmatchcase(change.path, pattern) for pattern in policy.protected_paths
            ):
                raise ValueError("PROTECTED_PATH: artifact violates project policy.")
            content = change.content_bytes or b""
            total += len(content)
            if (
                change.operation != FileOperation.DELETE
                and compute_file_sha256(content) != change.content_digest
            ):
                raise ValueError("CHANGESET_INVALID: file bytes differ from their bound digest.")
            if RedactionPolicy().contains_secret(content.decode("utf-8")) or total > 32768:
                raise ValueError("CHANGESET_INVALID: content protection or size budget failed.")
        return changeset

    def submit_implementation(self, request_id: str, proposal: ImplementationProposal) -> Operation:
        def execute(operation: Operation, lease: WriterLease) -> Operation:
            plan = self.ensure_plan(proposal.plan_id, lease)
            record = self._record(proposal.plan_id, proposal.step_id, lease)
            step = next(item for item in plan.steps if item.step_id == proposal.step_id)
            architecture = self._architecture(record, step.scope)
            if (
                step.scope != "implementation"
                or record.state != Lifecycle.PLAN_SAVED
                or not self.files.destination_root
                or proposal.architecture_digest != architecture
                or proposal.base_revision != record.base_revision
                or proposal.worktree_fingerprint != record.worktree_fingerprint
            ):
                raise ValueError(
                    "IMPLEMENTATION_CONTEXT_INVALID: select a fresh grounded implemen"
                    "tation step and its accepted target architecture."
                )
            texts = self.proposals._citations(proposal.citations)
            if not {reference.path for reference in step.evidence} <= texts.keys():
                raise ValueError(
                    "EVIDENCE_REQUIRED: cite every planned source reference at its current digest."
                )
            if len({file.path for file in proposal.files}) != len(proposal.files) or {
                file.path for file in proposal.files
            } != set(step.target_files):
                raise ValueError(
                    "IMPLEMENTATION_SCOPE_INVALID: generated paths must exactly match"
                    " the declared target scope."
                )
            for dependency in step.dependencies:
                if (
                    self.proposals.store.get_workflow(
                        record.project_id, record.plan_id, dependency
                    ).state
                    != Lifecycle.APPLY_COMPLETED
                ):
                    raise ValueError(
                        "DEPENDENCY_NOT_READY: publish prerequisites "
                        "before proposing this implementation."
                    )
            if any(file.operation == FileOperation.DELETE and file.text for file in proposal.files):
                raise ValueError(
                    "IMPLEMENTATION_SCOPE_INVALID: deletion cannot carry replacement text."
                )
            changeset = self.files.bind_destination(
                ChangeSet(
                    changeset_id="cs-" + operation.operation_id[3:],
                    plan_id=record.plan_id,
                    step_id=record.step_id,
                    base_revision=record.base_revision,
                    worktree_fingerprint=record.worktree_fingerprint,
                    architecture_digest=architecture,
                    changes=tuple(
                        FileChange(
                            path=file.path,
                            operation=file.operation,
                            content_bytes=file.text.encode("utf-8")
                            if file.operation != FileOperation.DELETE
                            else None,
                            content_digest=compute_file_sha256(file.text.encode("utf-8")),
                        )
                        for file in sorted(proposal.files, key=lambda file: file.path)
                    ),
                )
            )
            if changeset.destination != proposal.destination:
                raise ValueError(
                    "DESTINATION_CHANGED: generated files refer to another target snapshot."
                )
            changeset = changeset.model_copy(
                update={"changeset_digest": compute_changeset_digest(changeset)}
            )
            self.proposals.checkpoints.save_changeset(changeset)
            updated = record.model_copy(
                update={
                    "changeset_id": changeset.changeset_id,
                    "changeset_digest": changeset.changeset_digest,
                    "destination": changeset.destination,
                    "architecture_digest": architecture,
                }
            )
            self._changeset(updated)
            self.proposals.store.save_workflow(updated, lease)
            return operation.model_copy(
                update={
                    "plan_id": record.plan_id,
                    "step_id": record.step_id,
                    "changeset_id": changeset.changeset_id,
                }
            )

        return self.proposals._submit(request_id, "implementation", proposal, execute)

    def implementation_context(
        self, plan_id: str, step_id: str, lease: WriterLease
    ) -> ImplementationContext:
        self.proposals.authorization.require("changeset.stage")
        self.proposals.authorization.require("evidence.read")
        plan = self.ensure_plan(plan_id, lease)
        record = self._record(plan_id, step_id, lease)
        step = next(item for item in plan.steps if item.step_id == step_id)
        architecture = self._architecture(record, step.scope)
        if (
            step.scope != "implementation"
            or architecture is None
            or not self.files.destination_root
        ):
            raise ValueError(
                "IMPLEMENTATION_CONTEXT_REQUIRED: select a separate-target implem"
                "entation step with accepted architecture."
            )
        base = self.files.bind_destination(
            ChangeSet(
                changeset_id="context",
                plan_id=plan_id,
                step_id=step_id,
                base_revision=record.base_revision,
                worktree_fingerprint=record.worktree_fingerprint,
                changes=tuple(
                    FileChange(path=path, operation=FileOperation.CREATE)
                    for path in sorted(step.target_files)
                ),
            )
        )
        self._verify_destination_head(base)
        if base.destination is None:
            raise ValueError("DESTINATION_REQUIRED: select the separate target.")
        source = []
        citations = []
        total = sum(len(change.base_content_bytes or b"") for change in base.changes)
        for path in sorted({reference.path for reference in step.evidence}):
            text = self.proposals.evidence.read_text(path)
            total += len(text.encode("utf-8"))
            if total > 65536:
                raise ValueError(
                    "IMPLEMENTATION_CONTEXT_TOO_LARGE: narrow the grounded task scope."
                )
            digest = compute_file_sha256(text.encode("utf-8"))[7:]
            citations.append(EvidenceCitation(path=path, sha256=digest))
            source.append(
                EvidenceExcerpt(path=path, sha256=digest, line=1, text=text, has_more=False)
            )
        return ImplementationContext(
            plan_id=plan_id,
            step_id=step_id,
            base_revision=record.base_revision,
            worktree_fingerprint=record.worktree_fingerprint,
            destination=base.destination,
            architecture_digest=architecture,
            citations=tuple(citations),
            source=tuple(source),
            target_files=tuple(sorted(step.target_files)),
            target_base=tuple(
                RepairFile(
                    path=change.path, text=(change.base_content_bytes or b"").decode("utf-8")
                )
                for change in base.changes
            ),
            acceptance_criteria=tuple(step.acceptance_criteria),
        )

    def _verify_destination_head(self, changeset: ChangeSet) -> None:
        if changeset.destination is None:
            return
        head = self.proposals.store.destination_head(
            self.proposals.project_id, changeset.destination.root
        )
        if head is None:
            if changeset.destination.fingerprint != compute_file_sha256(b""):
                raise ValueError(
                    "DESTINATION_NOT_EMPTY: start with an empty separate target; exis"
                    "ting unregistered content cannot be adopted silently."
                )
        elif head != changeset.destination.fingerprint:
            raise ValueError(
                "DESTINATION_CHANGED: restore the last verified target checkpoint"
                " before starting another task."
            )

    def review_standards(
        self,
        plan_id: str,
        step_id: str,
        registry: RuleRegistry,
        evaluator: RuleEvaluatorPort,
    ) -> StandardsReviewReport:
        """Inspect existing staged evidence without changing state or approval authority."""
        record = self.proposals.store.get_workflow(
            self.proposals.project_id, opaque_id(plan_id), opaque_id(step_id)
        )
        if record.state not in {
            Lifecycle.STAGE_VERIFIED,
            Lifecycle.VALIDATION_FAILED,
            Lifecycle.VALIDATION_PASSED,
            Lifecycle.APPROVAL_PENDING,
            Lifecycle.APPROVAL_RECORDED,
        }:
            raise ValueError("STANDARDS_STATE_INVALID: select an idle staged artifact.")
        plan = self.proposals.checkpoints.get_plan(record.plan_id)
        if (
            Path(record.source_root).resolve() != self.proposals.root
            or plan is None
            or Path(plan.source_root).resolve() != self.proposals.root
            or compute_plan_digest(plan) != record.plan_digest
        ):
            raise ValueError("STANDARDS_ARTIFACT_INVALID: project or plan binding changed.")

        def verify_current() -> None:
            state = self.proposals.evidence.repository_state()
            current_plan = self.proposals.checkpoints.get_plan(record.plan_id)
            if (
                not state.clean
                or current_plan is None
                or compute_plan_digest(current_plan) != record.plan_digest
                or (state.revision, state.fingerprint, state.root_commit)
                != (record.base_revision, record.worktree_fingerprint, record.root_commit)
                or self.proposals.evidence.policy_digest() != record.policy_digest
                or self.proposals.store.get_workflow(record.project_id, plan_id, step_id) != record
            ):
                raise ValueError("STANDARDS_CONTEXT_CHANGED: regenerate against current evidence.")

        verify_current()
        changeset = self._changeset(record)
        if (
            self.files.verify_staging(record.staging_path or "", changeset)
            != record.staging_fingerprint
        ):
            raise ValueError("STAGING_CHANGED: standards report requires exact staged bytes.")
        execution = None
        if record.validation_digest is not None:
            execution = self.approvals.get_validation_execution(record.validation_digest)
        report = StandardsReviewService().review(record, changeset, registry, evaluator, execution)
        if execution is not None:
            if self.execution_gate is None:
                raise ValueError(
                    "STANDARDS_VALIDATION_INVALID: execution verification unavailable."
                )
            self.execution_gate.verify_execution(execution, record)
        if (
            self.files.verify_staging(record.staging_path or "", changeset)
            != record.staging_fingerprint
        ):
            raise ValueError("STAGING_CHANGED: staged bytes changed during standards review.")
        verify_current()
        self._changeset(record)
        return report

    def _architecture(self, record: WorkflowRecord, scope: str) -> str | None:
        architecture = self.foundation_contract() if self.foundation_contract else None
        if scope != "foundation" and architecture is not None:
            ready = False
            for previous in self.proposals.store.list_workflows(self.proposals.project_id):
                prior_plan = self.proposals.checkpoints.get_plan(previous.plan_id)
                if (
                    previous.state == Lifecycle.APPLY_COMPLETED
                    and previous.destination
                    and previous.destination.root == self.files.destination_root
                    and previous.architecture_digest == architecture
                    and previous.policy_digest == record.policy_digest
                    and prior_plan is not None
                    and any(
                        item.step_id == previous.step_id and item.scope == "foundation"
                        for item in prior_plan.steps
                    )
                ):
                    ready = True
                    break
            if not ready:
                raise ValueError(
                    "FOUNDATION_PUBLICATION_REQUIRED: stage, validate, review and publish "
                    "the accepted foundation to this target before functional tasks."
                )
        return architecture

    def stage(
        self,
        plan_id: str,
        step_id: str,
        lease: WriterLease,
        cancelled: Callable[[], bool] | None = None,
    ) -> WorkflowRecord:
        access = self.proposals.authorization.require("changeset.stage")
        plan = self.ensure_plan(plan_id, lease)
        record = self._record(plan_id, step_id, lease)
        step = next(step for step in plan.steps if step.step_id == step_id)
        architecture = self._architecture(record, step.scope)
        for dependency in step.dependencies:
            prior = self.proposals.store.get_workflow(
                self.proposals.project_id, plan_id, dependency
            )
            prerequisite = next(item for item in plan.steps if item.step_id == dependency)
            if (
                prerequisite.scope == "foundation"
                and step.scope != "foundation"
                and prior.state == Lifecycle.STAGE_VERIFIED
            ):
                raise ValueError(
                    "FOUNDATION_VALIDATION_REQUIRED: validate the staged foundation "
                    "before generating dependent functional tasks."
                )
            if self.files.destination_root and prior.state != Lifecycle.APPLY_COMPLETED:
                raise ValueError(
                    f"DEPENDENCY_NOT_READY: publish prerequisite {dependency} to the target first."
                )
            if prior.state not in {
                Lifecycle.STAGE_VERIFIED,
                Lifecycle.VALIDATION_PASSED,
                Lifecycle.APPROVAL_RECORDED,
                Lifecycle.APPLY_COMPLETED,
            }:
                raise ValueError("DEPENDENCY_NOT_READY: stage dependencies first.")
        if record.state == Lifecycle.PLAN_SAVED:
            if step.scope == "implementation":
                if not record.changeset_id:
                    raise ValueError(
                        "IMPLEMENTATION_PROPOSAL_REQUIRED: submit grounded generated file"
                        "s through the CLI/MCP implementation tool before staging."
                    )
                changeset = self._changeset(record)
            else:
                changeset, _ = self.transformation.preview(self.proposals.root, plan, step_id)
            changeset = self.files.bind_destination(changeset)
            changeset = changeset.model_copy(
                update={"base_revision": record.base_revision, "architecture_digest": architecture}
            )
            changeset = changeset.model_copy(
                update={"changeset_digest": compute_changeset_digest(changeset)}
            )
            self.proposals.checkpoints.save_changeset(changeset)
            record = record.model_copy(
                update={
                    "changeset_id": changeset.changeset_id,
                    "changeset_digest": changeset.changeset_digest,
                    "destination": changeset.destination,
                    "architecture_digest": architecture,
                }
            )
        elif record.state != Lifecycle.REPAIRING:
            raise ValueError(
                "STAGE_STATE_INVALID: stage requires a fresh plan or validated repair."
            )
        changeset = self._changeset(record)

        def fence() -> None:
            self.proposals.authorization.require("changeset.stage", access.access_digest)
            self.proposals.store.renew_lease(lease, 300)
            if cancelled and cancelled():
                raise ValueError("CANCEL_REQUESTED: staging stopped at a safe boundary.")

        path = self.files.materialize(changeset, f"stage-{uuid.uuid4().hex}", fence)
        self.proposals.check_base(record, lease)
        return self.proposals.store.save_workflow(
            record.model_copy(
                update={
                    "state": Lifecycle.STAGE_VERIFIED,
                    "staging_path": str(path),
                    "staging_fingerprint": self.files.verify_staging(str(path), changeset),
                    "validation_results": (),
                    "validation_digest": None,
                    "browser_evidence": None,
                    "approval_nonce": None,
                }
            ),
            lease,
        )

    def validate(
        self,
        plan_id: str,
        step_id: str,
        commands: tuple[ValidationCommand, ...],
        runner: FencedValidationPort,
        lease: WriterLease,
        cancelled: Callable[[], bool] | None = None,
    ) -> WorkflowRecord:
        access = self.proposals.authorization.require("validation.run")
        record = self._record(plan_id, step_id, lease)
        plan = self.ensure_plan(plan_id, lease)
        step = next((s for s in plan.steps if s.step_id == step_id), None)
        if step:
            for dependency in step.dependencies:
                prior = self.proposals.store.get_workflow(
                    self.proposals.project_id, plan_id, dependency
                )
                if prior.state != Lifecycle.APPLY_COMPLETED:
                    raise ValueError(
                        f"DEPENDENCY_NOT_READY: prerequisite step '{dependency}' must be applied "
                        f"(current state: {prior.state.value}) before validation."
                    )
        if (
            record.state
            not in {
                Lifecycle.STAGE_VERIFIED,
                Lifecycle.VALIDATION_FAILED,
                Lifecycle.VALIDATION_PASSED,
                Lifecycle.APPROVAL_PENDING,
                Lifecycle.APPROVAL_RECORDED,
            }
            or not commands
        ):
            raise ValueError("VALIDATION_STATE_INVALID: a staged artifact and checks are required.")
        changeset = self._changeset(record)
        before = self.files.verify_staging(record.staging_path or "", changeset)
        if before != record.staging_fingerprint:
            raise ValueError("STAGING_CHANGED: regenerate the staged workspace.")
        record = self.proposals.store.save_workflow(
            record.model_copy(
                update={
                    "state": Lifecycle.VALIDATION_RUNNING,
                    "validation_digest": None,
                    "validation_results": (),
                    "browser_evidence": None,
                    "approval_nonce": None,
                }
            ),
            lease,
        )
        results = []
        provenance = None
        browser_evidence = None

        def fence() -> None:
            self.proposals.authorization.require("validation.run", access.access_digest)
            self.proposals.store.renew_lease(lease, 300)
            if cancelled and cancelled():
                raise ValueError("CANCEL_REQUESTED: validation stopped at a safe boundary.")

        try:
            if self.execution_gate is not None and runner is self.execution_gate:
                provenance = self.execution_gate.prepare(record, commands, lease)
            for command in commands:
                fence()
                results.append(runner.run(command, Path(record.staging_path or ""), fence))
            if (
                provenance is not None
                and self.browser_gate is not None
                and self.browser_gate.required_profiles <= {result.profile for result in results}
                and all(
                    result.status == ValidationStatus.PASSED and result.exit_code == 0
                    for result in results
                )
            ):
                browser_evidence = self.browser_gate.run(record, provenance, lease, fence)
            after = self.files.verify_staging(record.staging_path or "", changeset)
            if after != before:
                raise ValueError("STAGING_CHANGED: validation modified the staged inputs.")
            self.proposals.check_base(record, lease)
            if provenance is not None and self.execution_gate is not None:
                provenance = self.execution_gate.completed(provenance, record, fence)
        except (ValueError, OSError) as error:
            latest = self.proposals.store.get_workflow(self.proposals.project_id, plan_id, step_id)
            if latest.state == Lifecycle.VALIDATION_RUNNING:
                self.proposals.store.save_workflow(
                    latest.model_copy(
                        update={
                            "state": Lifecycle.VALIDATION_FAILED,
                            "validation_results": tuple(results),
                            "recovery_note": RedactionPolicy().redact_text(str(error))[:1024],
                        }
                    ),
                    lease,
                )
            raise
        execution = ValidationExecution(
            schema_version=3
            if provenance is not None and self.browser_gate is not None
            else 2
            if provenance is not None
            else 1,
            provenance=provenance,
            browser_evidence=browser_evidence,
            project_id=record.project_id,
            plan_id=plan_id,
            step_id=step_id,
            changeset_id=changeset.changeset_id,
            changeset_digest=changeset.changeset_digest,
            staging_fingerprint=before,
            results=tuple(results),
        )
        digest = self.approvals.save_validation_execution(execution, lease)
        passed = all(
            result.status == ValidationStatus.PASSED and result.exit_code == 0 for result in results
        )
        if self.browser_gate is not None and provenance is not None:
            passed = passed and browser_evidence is not None and browser_evidence.passed
        return self.proposals.store.save_workflow(
            record.model_copy(
                update={
                    "state": Lifecycle.VALIDATION_PASSED if passed else Lifecycle.VALIDATION_FAILED,
                    "validation_results": tuple(results),
                    "validation_digest": digest,
                    "browser_evidence": browser_evidence,
                }
            ),
            lease,
        )

    def _validated(self, record: WorkflowRecord, lease: WriterLease | None = None) -> ChangeSet:
        changeset = self._changeset(record)
        execution = self.approvals.get_validation_execution(record.validation_digest or "")
        plan = self.proposals.checkpoints.get_plan(record.plan_id)
        if plan is None:
            raise ValueError("PLAN_INVALID: validation strategy unavailable.")
        step = next(step for step in plan.steps if step.step_id == record.step_id)
        required = set()
        for strategy in step.validation_strategy:
            text = strategy.casefold()
            matches = {
                profile
                for pattern, profile in (
                    (r"\blint\b", ValidationProfile.LINT),
                    (r"\b(typecheck|tsc)\b", ValidationProfile.TYPECHECK),
                    (r"\b(test|pytest)\b", ValidationProfile.TEST),
                    (r"\bbuild\b", ValidationProfile.BUILD),
                )
                if re.search(pattern, text)
            }
            if not matches:
                raise ValueError("VALIDATION_STRATEGY_UNSUPPORTED: choose a supported profile.")
            required.update(matches)
        if not required or not required.issubset({result.profile for result in execution.results}):
            raise ValueError("VALIDATION_REQUIRED: all planned validation profiles must pass.")
        if self.execution_gate is None or execution.schema_version not in {2, 3}:
            raise ValueError(
                "VALIDATION_BACKEND_UNSUPPORTED: legacy or report-only evidence "
                "requires revalidation."
            )
        access = self.proposals.authorization.require("evidence.read")

        def fence() -> None:
            self.proposals.authorization.require("evidence.read", access.access_digest)
            if lease:
                self.proposals.store.renew_lease(lease, 300)

        self.execution_gate.verify_execution(execution, record, fence)
        if self.browser_gate is not None:
            if (
                execution.schema_version != 3
                or execution.browser_evidence is None
                or execution.browser_evidence != record.browser_evidence
                or execution.provenance is None
                or execution.browser_evidence.capture.consent_id != execution.provenance.consent_id
                or execution.browser_evidence.capture.tool_digest
                != compute_canonical_digest(
                    [tool.model_dump(mode="json") for tool in execution.provenance.toolchain]
                )
            ):
                raise ValueError(
                    "BROWSER_VALIDATION_REQUIRED: revalidate with mandatory browser evidence."
                )
            self.browser_gate.verify(execution.browser_evidence, record)
        if (
            execution.project_id,
            execution.plan_id,
            execution.step_id,
            execution.changeset_id,
            execution.changeset_digest,
            execution.staging_fingerprint,
        ) != (
            record.project_id,
            record.plan_id,
            record.step_id,
            record.changeset_id,
            record.changeset_digest,
            record.staging_fingerprint,
        ):
            raise ValueError("VALIDATION_INVALID: provenance does not bind this staged ChangeSet.")
        if (
            compute_canonical_digest(execution.model_dump(mode="json")) != record.validation_digest
            or not execution.results
            or execution.results != record.validation_results
            or not all(
                result.status == ValidationStatus.PASSED and result.exit_code == 0
                for result in execution.results
            )
            or self.files.verify_staging(record.staging_path or "", changeset)
            != record.staging_fingerprint
        ):
            raise ValueError("VALIDATION_INVALID: PASSED immutable execution evidence is required.")
        return changeset

    def request_review(
        self, plan_id: str, step_id: str, changeset_id: str, lease: WriterLease
    ) -> ReviewRequestPayload:
        access = self.proposals.authorization.require("approval.request")
        record = self._record(plan_id, step_id, lease)
        if record.state not in {
            Lifecycle.VALIDATION_PASSED,
            Lifecycle.APPROVAL_PENDING,
            Lifecycle.APPROVAL_RECORDED,
        }:
            raise ValueError("VALIDATION_REQUIRED: complete validation before human review.")
        changeset = self._validated(record, lease)
        if changeset_id != record.changeset_id:
            raise ValueError("CHANGESET_MISMATCH: review must select the current exact artifact.")
        if record.state != Lifecycle.APPROVAL_PENDING:
            record = self.proposals.store.save_workflow(
                record.model_copy(
                    update={"state": Lifecycle.APPROVAL_PENDING, "approval_nonce": None}
                ),
                lease,
            )
        required = (
            AssuranceLevel.MODE_A
            if self.proposals.evidence.policy().default_mode == "MODE_A"
            else self.required_assurance
        )
        if "approval.sign" in access.capabilities and "changeset.apply" not in access.capabilities:
            required = AssuranceLevel.MODE_A
        return ReviewRequestPayload(
            project_id=record.project_id,
            run_id=record.run_id,
            plan_id=plan_id,
            step_id=step_id,
            changeset_id=changeset_id,
            changeset_digest=changeset.changeset_digest,
            policy_digest=record.policy_digest,
            base_revision=record.base_revision,
            worktree_fingerprint=record.worktree_fingerprint,
            validation_digest=record.validation_digest or "",
            required_assurance=required,
            signer_key_fingerprint=access.key_fingerprint
            if "approval.sign" in access.capabilities
            else None,
            destination=changeset.destination,
            diff=self.files.review_diff(changeset),
            review_command=(
                "agent",
                "approve",
                step_id,
                "--project-root",
                str(self.proposals.root),
                "--plan",
                plan_id,
                *self.review_options,
            ),
        )

    def approve(self, plan_id: str, step_id: str, reviewer: HumanReviewPort) -> ApplyApprovalRecord:
        access = self.proposals.authorization.require("approval.sign")
        lease = self.proposals.store.acquire_lease(
            self.proposals.project_id, f"review-{uuid.uuid4().hex}", ttl=900
        )
        try:
            record = self._record(plan_id, step_id, lease)
            review = self.request_review(plan_id, step_id, record.changeset_id or "", lease)
            decision = reviewer.confirm(review)
            self.proposals.authorization.require_signature(
                "approval.sign", decision.key_fingerprint
            )
            if not decision.confirmed or decision.assurance == AssuranceLevel.MODE_C:
                raise ValueError("APPROVAL_DECLINED: trusted human confirmation was not provided.")
            if (
                review.required_assurance == AssuranceLevel.MODE_A
                and decision.assurance != AssuranceLevel.MODE_A
            ):
                raise ValueError(
                    "ASSURANCE_REQUIRED: policy requires a cryptographic human signature."
                )
            record = self._record(plan_id, step_id, lease)
            self._validated(record, lease)
            now = datetime.now(UTC)
            approval = ApplyApprovalRecord(
                project_id=record.project_id,
                run_id=record.run_id,
                plan_id=plan_id,
                step_id=step_id,
                changeset_id=record.changeset_id or "",
                changeset_digest=record.changeset_digest or "",
                policy_digest=record.policy_digest,
                base_revision=record.base_revision,
                worktree_fingerprint=record.worktree_fingerprint,
                validation_digest=record.validation_digest or "",
                destination=record.destination,
                actor=decision.actor,
                principal_id=access.principal_id,
                access_digest=access.access_digest,
                assurance_level=decision.assurance,
                key_fingerprint=decision.key_fingerprint,
                nonce=uuid.uuid4().hex,
                created_at=now,
                expires_at=now + timedelta(minutes=15),
            )
            approval = approval.model_copy(update={"signature": self.proof.sign(approval)})
            self.proposals.authorization.require("approval.sign", access.access_digest)
            if not self.proof.verify(approval, record.root_commit):
                raise ValueError(
                    "APPROVAL_INVALID: signature does not match out-of-band authority."
                )
            self.approvals.save_apply_approval(approval, lease)
            self.proposals.store.save_workflow(
                record.model_copy(
                    update={"state": Lifecycle.APPROVAL_RECORDED, "approval_nonce": approval.nonce}
                ),
                lease,
            )
            return approval
        finally:
            self.proposals.store.release_lease(lease)

    def apply(self, plan_id: str, step_id: str, changeset_id: str) -> ApplyResult:
        with (
            self.proposals.authorization.fence("changeset.apply"),
            self.lock.acquire(self.files.lock_identity(self.proposals.project_id)),
        ):
            access = self.proposals.authorization.require("changeset.apply")
            lease = self.proposals.store.acquire_lease(
                self.proposals.project_id, f"apply-{uuid.uuid4().hex}", ttl=300
            )

            def fence() -> None:
                self.proposals.authorization.require("changeset.apply", access.access_digest)
                self.lock.verify()
                self.proposals.store.renew_lease(lease, 300)

            try:
                record = self._record(plan_id, step_id, lease)
                if (
                    record.state != Lifecycle.APPROVAL_RECORDED
                    or record.changeset_id != changeset_id
                ):
                    raise ValueError("APPROVAL_REQUIRED: exact human-approved artifact required.")
                changeset = self._validated(record, lease)
                approval = self.approvals.get_apply_approval(record.approval_nonce or "")
                expected = (
                    record.project_id,
                    record.run_id,
                    record.plan_id,
                    record.step_id,
                    record.changeset_id,
                    record.changeset_digest,
                    record.policy_digest,
                    record.base_revision,
                    record.worktree_fingerprint,
                    record.validation_digest,
                )
                actual = (
                    approval.project_id,
                    approval.run_id,
                    approval.plan_id,
                    approval.step_id,
                    approval.changeset_id,
                    approval.changeset_digest,
                    approval.policy_digest,
                    approval.base_revision,
                    approval.worktree_fingerprint,
                    approval.validation_digest,
                )
                now = datetime.now(UTC)
                if (
                    actual != expected
                    or approval.destination != record.destination
                    or approval.access_digest != access.access_digest
                    or approval.created_at.tzinfo is None
                    or approval.expires_at.tzinfo is None
                    or approval.created_at > now
                    or not approval.created_at < approval.expires_at
                    or (approval.expires_at - approval.created_at).total_seconds() > 900
                    or approval.expires_at <= now
                    or not self.proof.verify(approval, record.root_commit)
                ):
                    raise ValueError("APPROVAL_INVALID: approval binding, expiry, or proof failed.")
                required = (
                    self.proposals.evidence.policy().default_mode == "MODE_A"
                    or self.required_assurance == AssuranceLevel.MODE_A
                )
                if required and approval.assurance_level != AssuranceLevel.MODE_A:
                    raise ValueError(
                        "ASSURANCE_REQUIRED: apply requires a trusted Mode A signature."
                    )
                fence()
                backup, entries = self.files.prepare_backup(changeset, fence)
                self.proposals.check_base(record, lease)
                self.approvals.consume_apply_approval(approval.nonce, lease)
                record = self.proposals.store.save_workflow(
                    record.model_copy(
                        update={
                            "state": Lifecycle.APPLY_INTENT,
                            "backup_path": str(backup),
                            "backups": entries,
                            "generation": lease.generation,
                        }
                    ),
                    lease,
                )
                result = self.files.apply_files(record, changeset, fence)
                state = (
                    Lifecycle.APPLY_COMPLETED
                    if result.status == ApplyStatus.APPLIED
                    else Lifecycle.RECOVERY_REQUIRED
                )
                self.proposals.store.save_workflow(
                    record.model_copy(
                        update={
                            "state": state,
                            "approval_nonce": None,
                            "recovery_note": "; ".join(result.diagnostics),
                        }
                    ),
                    lease,
                )
                return result
            finally:
                self.proposals.store.release_lease(lease)
