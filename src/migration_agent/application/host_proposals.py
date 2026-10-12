"""Shared deterministic host proposal validation without a provider runtime."""

import hashlib
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path

from pydantic import BaseModel

from migration_agent.application.authorization import UnboundAuthorization
from migration_agent.application.validator import RuleBasedPlanValidator
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import compute_changeset_digest, compute_file_sha256
from migration_agent.domain.host_workflow import (
    AnalysisProposal,
    EvidenceCitation,
    EvidenceExcerpt,
    Lifecycle,
    Operation,
    OperationStatus,
    PlanProposal,
    RepairProposal,
    RepositoryState,
    WorkflowRecord,
    WriterLease,
    normalized_path,
)
from migration_agent.domain.planning import MigrationPlan, PlanStatus, compute_plan_digest
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.run_state import RunRecord
from migration_agent.ports.access import AuthorizationPort
from migration_agent.ports.checkpoints import CheckpointPort
from migration_agent.ports.host_workflow import ProjectEvidencePort, WorkflowStorePort


def opaque_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) or ".." in value:
        raise ValueError("INVALID_ID: bounded opaque identifier required.")
    return value


class HostProposalService:
    def __init__(
        self,
        project_id: str,
        root: Path,
        evidence: ProjectEvidencePort,
        store: WorkflowStorePort,
        checkpoints: CheckpointPort,
        actor: str,
        authorization: AuthorizationPort | None = None,
    ) -> None:
        self.project_id = project_id
        self.root = root.resolve()
        self.evidence = evidence
        self.store = store
        self.checkpoints = checkpoints
        self.actor = actor
        self.authorization = authorization or UnboundAuthorization()

    def read_evidence(
        self, citations: tuple[EvidenceCitation, ...], lines: int = 100
    ) -> tuple[EvidenceExcerpt, ...]:
        self.authorization.require("evidence.read")
        if not 1 <= len(citations) <= 10 or not 1 <= lines <= 200:
            raise ValueError("EVIDENCE_LIMIT: select 1-10 references and 1-200 lines.")
        results = []
        total = 0
        for citation in citations:
            text = self._check_citation(citation)
            split = text.splitlines()
            excerpt = "\n".join(split[citation.line - 1 : citation.line - 1 + lines])
            total += len(excerpt.encode("utf-8"))
            if total > 32768:
                raise ValueError("EVIDENCE_LIMIT: excerpts exceed 32 KiB.")
            results.append(
                EvidenceExcerpt(
                    path=citation.path,
                    sha256=citation.sha256,
                    line=citation.line,
                    text=excerpt,
                    has_more=citation.line - 1 + lines < len(split),
                )
            )
        return tuple(results)

    def _check_citation(self, citation: EvidenceCitation) -> str:
        text = self.evidence.read_text(citation.path)
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != citation.sha256:
            raise ValueError("EVIDENCE_CHANGED: cited content digest no longer matches.")
        lines = text.splitlines()
        if citation.line > len(lines):
            raise ValueError("EVIDENCE_LINE_INVALID: cited line does not exist.")
        if citation.symbol and not re.search(
            rf"(?<![\w$]){re.escape(citation.symbol)}(?![\w$])", lines[citation.line - 1]
        ):
            raise ValueError("EVIDENCE_SYMBOL_INVALID: symbol is absent from the cited line.")
        return text

    def _base(self, revision: str, fingerprint: str) -> RepositoryState:
        state = self.evidence.repository_state()
        if not state.clean or state.revision != revision or state.fingerprint != fingerprint:
            raise ValueError("BASE_CHANGED: re-inspect and submit a fresh proposal.")
        return state

    def _citations(self, citations: tuple[EvidenceCitation, ...]) -> dict[str, str]:
        return {citation.path: self._check_citation(citation) for citation in citations}

    def _check_evidence(
        self, path: str, line: int | None, sample: str | None, texts: dict[str, str]
    ) -> None:
        if path not in texts:
            raise ValueError("EVIDENCE_REQUIRED: every reference needs a current citation.")
        text = texts[path]
        if line is not None:
            split = text.splitlines()
            if line > len(split):
                raise ValueError("EVIDENCE_LINE_INVALID: reference line is absent.")
            text = split[line - 1]
        if sample and sample not in text:
            raise ValueError("EVIDENCE_SAMPLE_INVALID: sample is not grounded in source.")

    def _submit(
        self,
        request_id: str,
        kind: str,
        payload: BaseModel,
        execute: Callable[[Operation, WriterLease], Operation],
    ) -> Operation:
        capability = {
            "analysis": "analysis.submit",
            "plan": "plan.submit",
            "repair": "repair.submit",
            "implementation": "changeset.stage",
        }[kind]
        access = self.authorization.require(capability)
        opaque_id(request_id)
        serialized = payload.model_dump_json()
        if len(serialized.encode("utf-8")) > 65536 or RedactionPolicy().contains_secret(serialized):
            raise ValueError("PROPOSAL_REJECTED: input exceeds limits or contains credentials.")
        op, claimed = self.store.claim_request(
            Operation(
                operation_id=f"op-{uuid.uuid4().hex}",
                project_id=self.project_id,
                request_id=request_id,
                kind=kind,
                actor=self.actor,
                access_digest=access.access_digest,
                principal_id=access.principal_id,
                capability=capability,
                payload_digest=compute_canonical_digest(payload.model_dump(mode="json")),
            )
        )
        if not claimed:
            return op
        lease: WriterLease | None = None
        try:
            lease = self.store.acquire_lease(self.project_id, op.operation_id, ttl=300)
            running = op.model_copy(update={"status": OperationStatus.RUNNING})
            self.authorization.require(capability, access.access_digest)
            self.store.save_operation(running, lease)
            result = execute(running, lease).model_copy(
                update={
                    "status": OperationStatus.SUCCEEDED,
                    "message": "Validated and saved",
                    "updated_at": datetime.now(UTC),
                }
            )
            self.store.save_operation(result, lease)
            return result
        except ValueError as error:
            failed = op.model_copy(
                update={
                    "status": OperationStatus.FAILED,
                    "message": RedactionPolicy().redact_text(str(error))[:512],
                }
            )
            current = self.store.get_operation(self.project_id, op.operation_id)
            if current.status == OperationStatus.CANCEL_REQUESTED:
                failed = failed.model_copy(update={"status": OperationStatus.CANCELLED})
            self.store.save_operation(failed)
            return failed
        finally:
            if lease:
                self.store.release_lease(lease)

    def submit_analysis(self, request_id: str, proposal: AnalysisProposal) -> Operation:
        def execute(op: Operation, lease: WriterLease) -> Operation:
            self._base(proposal.base_revision, proposal.worktree_fingerprint)
            texts = self._citations(proposal.citations)
            finding_ids: set[str] = set()
            for finding in proposal.findings:
                opaque_id(finding.id)
                if finding.id in finding_ids or not finding.evidence_references:
                    raise ValueError("FINDING_INVALID: unique findings require source evidence.")
                finding_ids.add(finding.id)
                for reference in finding.evidence_references:
                    self._check_evidence(
                        reference.path, reference.line_number, reference.sample, texts
                    )
            analysis_id = f"analysis-{op.operation_id[3:]}"
            self.store.save_analysis(self.project_id, analysis_id, proposal, lease)
            return op.model_copy(update={"analysis_id": analysis_id})

        return self._submit(request_id, "analysis", proposal, execute)

    def submit_plan(self, request_id: str, proposal: PlanProposal) -> Operation:
        def execute(op: Operation, lease: WriterLease) -> Operation:
            state = self._base(proposal.base_revision, proposal.worktree_fingerprint)
            analysis = self.store.get_analysis(self.project_id, opaque_id(proposal.analysis_id))
            if (analysis.base_revision, analysis.worktree_fingerprint) != (
                state.revision,
                state.fingerprint,
            ):
                raise ValueError("BASE_CHANGED: analysis is stale; re-inspect and re-analyze.")
            texts = self._citations(proposal.citations)
            policy = self.evidence.policy()
            for step in proposal.steps:
                opaque_id(step.step_id)
                if not step.evidence or not step.expected_files or step.unresolved_questions:
                    raise ValueError(
                        "PLAN_UNCERTAIN: grounded scope and resolved questions required."
                    )
                if step.scope not in {"component", "service", "foundation", "implementation"}:
                    raise ValueError(
                        "SCOPE_UNSUPPORTED: no deterministic transform for this scope."
                    )
                if step.scope == "implementation":
                    if not step.target_files or not step.acceptance_criteria:
                        raise ValueError(
                            "IMPLEMENTATION_SCOPE_REQUIRED: declare target files and business"
                            " acceptance criteria."
                        )
                    if len(set(step.target_files)) != len(step.target_files):
                        raise ValueError("IMPLEMENTATION_SCOPE_INVALID: duplicate target paths.")
                    for path in step.target_files:
                        normalized_path(path)
                        if any(fnmatchcase(path, pattern) for pattern in policy.protected_paths):
                            raise ValueError(
                                "PROTECTED_PATH: implementation targets protected governance."
                            )
                for reference in step.evidence:
                    self._check_evidence(
                        reference.path, reference.line_number, reference.sample, texts
                    )
                for path in step.expected_files:
                    normalized_path(path)
                    if any(fnmatchcase(path, pattern) for pattern in policy.protected_paths):
                        raise ValueError("PROTECTED_PATH: proposed scope violates project policy.")
                if step.scope != "foundation" and not any(
                    path in texts for path in step.expected_files
                ):
                    raise ValueError("SCOPE_UNGROUNDED: expected files must identify cited source.")
            plan = MigrationPlan(
                plan_id=f"plan-{op.operation_id[3:]}",
                source_root=str(self.root),
                run_id=f"run-{op.operation_id[3:]}",
                status=PlanStatus.DRAFT,
                steps=list(proposal.steps),
                policy_digest=self.evidence.policy_digest(),
            )
            validator = RuleBasedPlanValidator(max_step_files=policy.max_step_files)
            checked = validator.validate(plan, self.evidence.inventory())
            if not checked.is_valid:
                raise ValueError("PLAN_INVALID: " + "; ".join(checked.errors)[:400])
            plan = plan.model_copy(update={"steps": validator.topological_sort(plan.steps)})
            self.store.verify_lease(lease)
            self.checkpoints.save_plan(plan)
            self.checkpoints.save_run_record(
                RunRecord(run_id=plan.run_id, plan_id=plan.plan_id, source_root=str(self.root))
            )
            for step in plan.steps:
                self.store.save_workflow(
                    WorkflowRecord(
                        project_id=self.project_id,
                        source_root=str(self.root),
                        run_id=plan.run_id,
                        plan_id=plan.plan_id,
                        step_id=step.step_id,
                        base_revision=state.revision,
                        root_commit=state.root_commit,
                        worktree_fingerprint=state.fingerprint,
                        policy_digest=plan.policy_digest,
                        plan_digest=compute_plan_digest(plan),
                    ),
                    lease,
                )
            return op.model_copy(update={"plan_id": plan.plan_id})

        return self._submit(request_id, "plan", proposal, execute)

    def check_base(self, record: WorkflowRecord, lease: WriterLease) -> None:
        try:
            self._base(record.base_revision, record.worktree_fingerprint)
            if self.evidence.policy_digest() != record.policy_digest:
                raise ValueError("BASE_CHANGED: active policy changed; submit a fresh plan.")
        except ValueError:
            if record.state not in {
                Lifecycle.BASE_CHANGED,
                Lifecycle.APPLY_INTENT,
                Lifecycle.APPLY_COMPLETED,
                Lifecycle.RECOVERY_REQUIRED,
            }:
                self.store.save_workflow(
                    record.model_copy(update={"state": Lifecycle.BASE_CHANGED}), lease
                )
            raise

    def submit_repair(self, request_id: str, proposal: RepairProposal) -> Operation:
        def execute(op: Operation, lease: WriterLease) -> Operation:
            record = self.store.get_workflow(
                self.project_id, opaque_id(proposal.plan_id), opaque_id(proposal.step_id)
            )
            self.check_base(record, lease)
            if (
                record.state != Lifecycle.VALIDATION_FAILED
                or record.changeset_id != proposal.changeset_id
            ):
                raise ValueError(
                    "REPAIR_STATE_INVALID: repair requires the failed current ChangeSet."
                )
            from migration_agent.domain.host_workflow import workflow_diagnostic_digest

            diagnostic_digest = workflow_diagnostic_digest(record)
            if proposal.diagnostic_digest != diagnostic_digest:
                raise ValueError("DIAGNOSTIC_MISMATCH: repair must cite the recorded failure.")
            prior = self.checkpoints.get_changeset(proposal.changeset_id)
            browser_repair = record.browser_evidence is not None
            if (
                record.browser_evidence is not None
                and record.browser_repair_count >= record.browser_evidence.max_repairs
            ):
                raise ValueError(
                    "BROWSER_REPAIR_BUDGET_EXHAUSTED: resolve findings or renew "
                    "the approved scope/budget."
                )
            if prior is None or compute_changeset_digest(prior) != record.changeset_digest:
                raise ValueError("CHANGESET_INVALID: current artifact is unavailable or altered.")
            by_path = {file.path: file for file in proposal.files}
            allowed = {change.path for change in prior.changes}
            if len(by_path) != len(proposal.files) or not set(by_path) <= allowed:
                raise ValueError("REPAIR_SCOPE_INVALID: repair exceeds the prior ChangeSet scope.")
            if sum(len(file.text.encode("utf-8")) for file in proposal.files) > 32768:
                raise ValueError("REPAIR_TOO_LARGE: generated bytes exceed budget.")
            changes = tuple(
                change.model_copy(
                    update={
                        "content_bytes": by_path[change.path].text.encode("utf-8"),
                        "content_digest": compute_file_sha256(
                            by_path[change.path].text.encode("utf-8")
                        ),
                    }
                )
                if change.path in by_path
                else change
                for change in prior.changes
            )
            repaired = prior.model_copy(
                update={"changeset_id": f"cs-{op.operation_id[3:]}", "changes": changes}
            )
            repaired = repaired.model_copy(
                update={"changeset_digest": compute_changeset_digest(repaired)}
            )
            self.store.verify_lease(lease)
            self.checkpoints.save_changeset(repaired)
            self.store.save_workflow(
                record.model_copy(
                    update={
                        "state": Lifecycle.REPAIRING,
                        "changeset_id": repaired.changeset_id,
                        "changeset_digest": repaired.changeset_digest,
                        "validation_results": (),
                        "validation_digest": None,
                        "browser_evidence": None,
                        "browser_repair_count": record.browser_repair_count + int(browser_repair),
                        "approval_nonce": None,
                        "staging_fingerprint": None,
                    }
                ),
                lease,
            )
            return op.model_copy(
                update={
                    "plan_id": record.plan_id,
                    "step_id": record.step_id,
                    "changeset_id": repaired.changeset_id,
                }
            )

        return self._submit(request_id, "repair", proposal, execute)
