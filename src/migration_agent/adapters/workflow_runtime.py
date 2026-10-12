"""Composition of shared Phase 16 services and durable background operation dispatch."""

import getpass
import threading
import uuid
from pathlib import Path

from migration_agent.adapters.access_approval_authority import AccessApprovalAuthority
from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.apply_lock import ExclusiveApplyLock
from migration_agent.adapters.approval_proof import LocalApprovalProof
from migration_agent.adapters.browser_validation import BrowserValidationGate
from migration_agent.adapters.controlled_files import LocalControlledFiles
from migration_agent.adapters.fenced_validation import validation_commands
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.foundation_transformation import BoundFoundationTransformationAdapter
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.mcp.tools import _create_default_framework_registry
from migration_agent.adapters.project_evidence import LocalProjectEvidence
from migration_agent.adapters.recovery_probe import LocalRecoveryProbe
from migration_agent.adapters.validation_backend import ValidationBackend
from migration_agent.adapters.workflow_store import SqliteWorkflowStore
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.apply import ApplyService
from migration_agent.application.host_proposals import HostProposalService, opaque_id
from migration_agent.application.transformation import TransformationService
from migration_agent.application.workflow_recovery import reconcile_workflows
from migration_agent.config import Settings
from migration_agent.domain.browser_validation import BrowserReview
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import ChangeSet
from migration_agent.domain.host_workflow import (
    TERMINAL_OPERATIONS,
    Lifecycle,
    Operation,
    OperationStatus,
    RepairProposal,
    WorkflowRecord,
)
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.validation import ValidationProfile
from migration_agent.ports.access import AuthorizationPort


class WorkflowRuntime:
    def __init__(
        self,
        binding: ProjectBinding,
        settings: Settings,
        state_dir: Path | None = None,
        authorization: AuthorizationPort | None = None,
    ) -> None:
        self.binding = binding
        self.settings = settings
        self.configuration_snapshot = None
        self.authorization = authorization or ProjectAuthorization(
            binding.project_root,
            settings.model_copy(update={"state_dir": settings.resolve_state_dir(state_dir)}),
        )
        if isinstance(self.authorization, ProjectAuthorization):
            from migration_agent.adapters.configuration_runtime import ConfigurationFacade

            if self.authorization.require("project.read").access_digest:
                configured = ConfigurationFacade(self.authorization, self.authorization.settings)
                settings = configured.runtime_settings()
                self.settings = settings
                from migration_agent.application.configuration import resolve_configuration

                self.configuration_snapshot = resolve_configuration(
                    configured.repository.project(),
                    configured.repository.local(),
                    configured.repository.launcher(),
                )
        self.state = binding.validate_storage_roots(
            settings.resolve_state_dir(state_dir), settings.resolve_staging_root()
        )
        self.staging = settings.resolve_staging_root().expanduser().resolve()
        self.trust = (settings.trust_root or Path.home() / ".agent-platform" / "trust").resolve()
        binding.validate_storage_roots(self.trust)
        self.store = SqliteWorkflowStore(self.state)
        registry = _create_default_framework_registry()
        self.proposals = HostProposalService(
            binding.project_id,
            binding.project_root,
            LocalProjectEvidence(binding.project_root, registry),
            self.store,
            self.store,
            getpass.getuser(),
            self.authorization,
        )
        if isinstance(self.authorization, ProjectAuthorization):
            self.proposals.evidence = LocalProjectEvidence(
                binding.project_root, registry, self.authorization
            )
        governed = (
            self.authorization.service().store.binding
            if isinstance(self.authorization, ProjectAuthorization)
            and self.authorization.require("project.read").access_digest
            else None
        )
        destination = settings.final_target_root
        self.architecture_snapshot = None
        if destination is not None:
            from migration_agent.adapters.filesystem import read_repository_text
            from migration_agent.adapters.stack_catalog import (
                get_default_target_preset,
                get_target_preset,
            )
            from migration_agent.domain.stack import ArchitectureManifest

            preset = get_default_target_preset()
            if (
                governed is not None
                and (Path(governed.governance_root) / ".agent/architecture.json").exists()
            ):
                manifest = ArchitectureManifest.model_validate_json(
                    read_repository_text(Path(governed.governance_root), ".agent/architecture.json")
                )
                approved = get_target_preset(manifest.preset_id)
                if approved is None:
                    raise ValueError(
                        "FOUNDATION_PRESET_UNSUPPORTED: select an installed signed preset."
                    )
                preset = approved
                self.architecture_snapshot = manifest.draft_digest

            settings = settings.model_copy(update={"validation_catalog": preset.validation_catalog})
            self.settings = settings
        if destination is not None:
            binding.validate_storage_roots(self.trust, destination)
            if governed is not None:
                governance_root = Path(governed.governance_root).resolve()
                resolved_target = destination.resolve()
                if governance_root.is_relative_to(
                    resolved_target
                ) or resolved_target.is_relative_to(governance_root):
                    raise ValueError("UNSAFE_ROOT_OVERLAP: governance and target must be separate.")
        self.files = LocalControlledFiles(
            binding.project_root,
            self.staging,
            self.state,
            destination,
            require_destination=governed is not None
            and Path(governed.governance_root).resolve() != binding.project_root,
        )
        lock_root = Path.home() / ".agent-platform" / "locks"
        binding.validate_storage_roots(lock_root)
        self.lock = ExclusiveApplyLock(lock_root)
        self.runner = ValidationBackend(
            settings, self.proposals, self.store, self.staging, self.state, self.trust
        )
        self.browser_gate = BrowserValidationGate(settings, self.runner, self.store, self.state)
        authority = (
            AccessApprovalAuthority(self.authorization, binding.project_id)
            if isinstance(self.authorization, ProjectAuthorization)
            else None
        )
        proof = LocalApprovalProof(self.trust, self.state, authority)
        if authority:
            self.runner.proof = proof
        self.apply_service = ApplyService(
            self.proposals,
            TransformationService(
                workspace_adapter=LocalWorkspaceAdapter(),
                registry=registry,
                filesystem=SafeFilesystemInspector(),
                max_preview_files=100,
                max_preview_bytes=32768,
                foundation_adapter=BoundFoundationTransformationAdapter(self.authorization)
                if isinstance(self.authorization, ProjectAuthorization)
                else None,
            ),
            self.store,
            self.files,
            self.lock,
            proof,
            settings.apply_minimum_assurance,
            (
                "--state-dir",
                str(self.state),
                "--staging-root",
                str(self.staging),
                "--trust-root",
                str(self.trust),
            ),
            execution_gate=self.runner,
            browser_gate=self.browser_gate,
            foundation_contract=BoundFoundationTransformationAdapter(
                self.authorization
            ).contract_digest
            if isinstance(self.authorization, ProjectAuthorization) and destination is not None
            else None,
            foundation_paths=BoundFoundationTransformationAdapter.configuration_paths
            if destination is not None
            else (),
        )
        self._threads: list[threading.Thread] = []
        self._closing = threading.Event()
        try:
            with self.lock.acquire(self.files.lock_identity(binding.project_id)):
                reconcile_workflows(
                    binding.project_id,
                    self.store,
                    self.store,
                    LocalRecoveryProbe(binding.project_root, destination),
                )
        except ValueError as error:
            if not str(error).startswith("WRITER_BUSY"):
                raise
        self.store.purge_operations()

    def dispatch(
        self,
        kind: str,
        plan_id: str,
        step_id: str,
        request_id: str,
        changeset_id: str | None = None,
        profile: str = "ALL",
        background: bool = True,
    ) -> Operation:
        self.require_current_configuration()
        for value in (plan_id, step_id, request_id):
            opaque_id(value)
        if changeset_id:
            opaque_id(changeset_id)
        if kind not in {"stage", "validate", "apply", "review"}:
            raise ValueError("OPERATION_KIND_INVALID: unsupported operation.")
        if profile not in {"ALL", *(item.value for item in ValidationProfile)}:
            raise ValueError("PROFILE_INVALID: choose an existing validation profile.")
        return self._dispatch_current(
            kind, plan_id, step_id, request_id, changeset_id, profile, background
        )

    def require_current_configuration(self) -> None:
        if not self.configuration_is_current():
            raise ValueError(
                "CONFIGURATION_CHANGED: restart this CLI/MCP session before start"
                "ing another operation."
            )

    def _dispatch_current(
        self,
        kind: str,
        plan_id: str,
        step_id: str,
        request_id: str,
        changeset_id: str | None,
        profile: str,
        background: bool,
    ) -> Operation:
        operation, claimed = self.store.claim_request(
            # Authorize before querying a replay receipt.
            Operation(
                operation_id=f"op-{uuid.uuid4().hex}",
                project_id=self.binding.project_id,
                request_id=request_id,
                actor=self.proposals.actor,
                principal_id=self.authorization.require(
                    {
                        "stage": "changeset.stage",
                        "validate": "validation.run",
                        "apply": "changeset.apply",
                        "review": "approval.request",
                    }[kind]
                ).principal_id,
                access_digest=self.authorization.require(
                    {
                        "stage": "changeset.stage",
                        "validate": "validation.run",
                        "apply": "changeset.apply",
                        "review": "approval.request",
                    }[kind]
                ).access_digest,
                capability={
                    "stage": "changeset.stage",
                    "validate": "validation.run",
                    "apply": "changeset.apply",
                    "review": "approval.request",
                }[kind],
                kind=kind,
                configuration_snapshot=self.configuration_snapshot,
                plan_id=plan_id,
                step_id=step_id,
                changeset_id=changeset_id,
                payload_digest=compute_canonical_digest(
                    {
                        "plan": plan_id,
                        "step": step_id,
                        "changeset": changeset_id,
                        "profile": profile,
                        "configuration": self.configuration_snapshot,
                    }
                ),
            )
        )
        if claimed:
            if background:
                self._threads = [thread for thread in self._threads if thread.is_alive()]
                if len(self._threads) >= 2:
                    failed = operation.model_copy(
                        update={
                            "status": OperationStatus.FAILED,
                            "message": "WRITER_BUSY: bounded worker capacity reached.",
                        }
                    )
                    self.store.save_operation(failed)
                    return failed
                thread = threading.Thread(
                    target=self._execute, args=(operation, profile), daemon=True
                )
                self._threads.append(thread)
                thread.start()
            else:
                self._execute(operation, profile)
                return self.store.get_operation(self.binding.project_id, operation.operation_id)
        return operation

    def configuration_is_current(self) -> bool:
        if self.configuration_snapshot is None or not isinstance(
            self.authorization, ProjectAuthorization
        ):
            return True
        from migration_agent.adapters.configuration_runtime import ConfigurationFacade
        from migration_agent.application.configuration import resolve_configuration

        facade = ConfigurationFacade(self.authorization, self.authorization.settings)
        from migration_agent.adapters.filesystem import read_repository_text
        from migration_agent.domain.stack import ArchitectureManifest

        architecture_file = facade.repository.governance / ".agent/architecture.json"
        active = (
            ArchitectureManifest.model_validate_json(
                read_repository_text(facade.repository.governance, ".agent/architecture.json")
            ).draft_digest
            if architecture_file.exists()
            else None
        )
        if active != self.architecture_snapshot:
            return False
        return self.configuration_snapshot == resolve_configuration(
            facade.repository.project(), facade.repository.local(), facade.repository.launcher()
        )

    def verify_source(self) -> None:
        if not self.proposals.evidence.repository_state().clean:
            raise ValueError("BASE_CHANGED: inspect and commit or restore the source first.")

    def prepare(self, plan_id: str, step_id: str, skip_validation: bool) -> WorkflowRecord:
        try:
            record = self.store.get_workflow(self.binding.project_id, plan_id, step_id)
        except ValueError as error:
            if not str(error).startswith("WORKFLOW_NOT_FOUND"):
                raise
            record = None
        if record is None or record.state in {Lifecycle.PLAN_SAVED, Lifecycle.REPAIRING}:
            staged = self.dispatch("stage", plan_id, step_id, uuid.uuid4().hex, background=False)
            if staged.status != OperationStatus.SUCCEEDED:
                raise ValueError(staged.message)
        if not skip_validation:
            self.dispatch("validate", plan_id, step_id, uuid.uuid4().hex, background=False)
        return self.store.get_workflow(self.binding.project_id, plan_id, step_id)

    def current_changeset(self, changeset_id: str) -> ChangeSet:
        self.authorization.require("changeset.read")
        changeset = self.store.get_changeset(opaque_id(changeset_id))
        if changeset is None:
            raise ValueError("CHANGESET_INVALID: current artifact is unavailable.")
        return changeset

    def submit_browser_review(
        self, plan_id: str, step_id: str, request_id: str, review: BrowserReview
    ) -> Operation:
        access = self.authorization.require("validation.run")
        operation, claimed = self.store.claim_request(
            Operation(
                operation_id=f"op-{uuid.uuid4().hex}",
                project_id=self.binding.project_id,
                request_id=opaque_id(request_id),
                kind="browser_review",
                principal_id=access.principal_id,
                access_digest=access.access_digest,
                capability="validation.run",
                actor=self.proposals.actor,
                plan_id=opaque_id(plan_id),
                step_id=opaque_id(step_id),
                payload_digest=compute_canonical_digest(
                    {"plan": plan_id, "step": step_id, "review": review.model_dump(mode="json")}
                ),
            )
        )
        if not claimed:
            return operation
        lease = None
        try:
            lease = self.store.acquire_lease(
                self.binding.project_id, operation.operation_id, ttl=300
            )
            record = self.apply_service._record(plan_id, step_id, lease)
            if record.state != Lifecycle.VALIDATION_FAILED or not record.validation_digest:
                raise ValueError(
                    "BROWSER_REVIEW_STATE_INVALID: select current failed/pending "
                    "browser validation."
                )
            execution = self.store.get_validation_execution(record.validation_digest)
            self.runner.verify_execution(execution, record)
            evidence = self.browser_gate.submit(record, review, lease)
            updated = execution.model_copy(update={"browser_evidence": evidence})
            digest = self.store.save_validation_execution(updated, lease)
            self.store.save_workflow(
                record.model_copy(
                    update={
                        "browser_evidence": evidence,
                        "validation_digest": digest,
                        "approval_nonce": None,
                    }
                ),
                lease,
            )
            operation = operation.model_copy(
                update={
                    "status": OperationStatus.SUCCEEDED,
                    "message": "Browser review recorded; repair or rerun validation "
                    "before source approval.",
                }
            )
        except (ValueError, OSError) as error:
            operation = operation.model_copy(
                update={
                    "status": OperationStatus.FAILED,
                    "message": RedactionPolicy().redact_text(str(error))[:512],
                }
            )
        try:
            self.store.save_operation(operation, lease)
        finally:
            if lease:
                self.store.release_lease(lease)
        return operation

    def submit_repair(self, proposal: RepairProposal) -> WorkflowRecord:
        operation = self.proposals.submit_repair(uuid.uuid4().hex, proposal)
        if operation.status != OperationStatus.SUCCEEDED:
            raise ValueError(operation.message)
        return self.store.get_workflow(self.binding.project_id, proposal.plan_id, proposal.step_id)

    def _execute(self, operation: Operation, profile: str) -> None:
        lease = None
        try:
            if not operation.capability:
                raise ValueError("ACCESS_CONTEXT_REQUIRED: resubmit the legacy operation.")
            decision = self.authorization.require(operation.capability, operation.access_digest)
            if operation.configuration_snapshot != self.configuration_snapshot:
                raise ValueError(
                    "CONFIGURATION_CONTEXT_CHANGED: resubmit under the current runtime snapshot."
                )
            if decision.principal_id != operation.principal_id:
                raise ValueError("ACTOR_MISMATCH: operation belongs to another principal.")
            current = self.store.get_operation(operation.project_id, operation.operation_id)
            if current.status in TERMINAL_OPERATIONS:
                return
            current = current.model_copy(
                update={"status": OperationStatus.RUNNING, "message": "Running"}
            )
            self.store.save_operation(current)
            plan_id, step_id = current.plan_id or "", current.step_id or ""
            if current.kind == "apply":
                result = self.apply_service.apply(plan_id, step_id, current.changeset_id or "")
                status = (
                    OperationStatus.SUCCEEDED
                    if result.status.value == "APPLIED"
                    else OperationStatus.RECOVERY_REQUIRED
                )
                done = current.model_copy(update={"status": status, "message": result.status.value})
            else:
                lease = self.store.acquire_lease(
                    operation.project_id, operation.operation_id, ttl=300
                )

                def cancelled() -> bool:
                    self.authorization.require(operation.capability or "", operation.access_digest)
                    return (
                        self._closing.is_set()
                        or self.store.get_operation(
                            operation.project_id, operation.operation_id
                        ).status
                        == OperationStatus.CANCEL_REQUESTED
                    )

                if current.kind == "stage":
                    record = self.apply_service.stage(plan_id, step_id, lease, cancelled)
                elif current.kind == "validate":
                    commands = tuple(
                        command
                        for selected, items in validation_commands(
                            self.settings.validation_catalog
                        ).items()
                        if profile in {"ALL", selected.value}
                        for command in items
                    )

                    record = self.apply_service.validate(
                        plan_id, step_id, commands, self.runner, lease, cancelled
                    )
                else:
                    self.apply_service.request_review(
                        plan_id, step_id, current.changeset_id or "", lease
                    )
                    record = self.store.get_workflow(operation.project_id, plan_id, step_id)
                status = (
                    OperationStatus.FAILED
                    if record.state == Lifecycle.VALIDATION_FAILED
                    else OperationStatus.SUCCEEDED
                )
                done = current.model_copy(
                    update={
                        "status": status,
                        "changeset_id": record.changeset_id,
                        "message": record.state.value,
                        "completed_units": len(record.validation_results),
                        "total_units": len(record.validation_results),
                        "output_tail": RedactionPolicy().redact_text(
                            "\n".join(
                                result.sanitized_output for result in record.validation_results
                            )
                            + (
                                "\n"
                                + "\n".join(record.browser_evidence.issues)
                                + "\nBrowser: "
                                + record.browser_evidence.status
                                + "; capture: "
                                + record.browser_evidence.capture.capture_id
                                + "; E2E: "
                                + record.browser_evidence.e2e_status
                                if record.browser_evidence
                                else ""
                            )
                        )[-4096:],
                    }
                )
            self.store.save_operation(done, lease)
        except Exception as error:
            current = self.store.get_operation(operation.project_id, operation.operation_id)
            if current.status not in TERMINAL_OPERATIONS:
                status = (
                    OperationStatus.CANCELLED
                    if current.status == OperationStatus.CANCEL_REQUESTED
                    else OperationStatus.FAILED
                )
                self.store.save_operation(
                    current.model_copy(
                        update={
                            "status": status,
                            "message": RedactionPolicy().redact_text(str(error))[:512],
                        }
                    )
                )
        finally:
            if lease:
                self.store.release_lease(lease)

    def close(self) -> None:
        self._closing.set()
        for thread in self._threads:
            thread.join(timeout=5)
