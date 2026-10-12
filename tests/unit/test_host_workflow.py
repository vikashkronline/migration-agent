"""Offline Phase 16 proposal, ownership, lifecycle, and concurrency regressions."""

import hashlib
import inspect
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from access_fixture import WorkflowAuthorizationFixture

from migration_agent.adapters.apply_lock import ExclusiveApplyLock
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.mcp.tools import _create_default_framework_registry
from migration_agent.adapters.project_evidence import LocalProjectEvidence
from migration_agent.adapters.recovery_probe import LocalRecoveryProbe
from migration_agent.adapters.workflow_store import SqliteWorkflowStore
from migration_agent.application.host_proposals import HostProposalService
from migration_agent.application.workflow_recovery import reconcile_workflows
from migration_agent.domain.analysis import AnalysisFinding, EvidenceReference
from migration_agent.domain.changeset import (
    ChangeSet,
    FileChange,
    FileOperation,
    compute_changeset_digest,
    compute_file_sha256,
)
from migration_agent.domain.host_workflow import (
    AnalysisProposal,
    BackupEntry,
    EvidenceCitation,
    Lifecycle,
    Operation,
    OperationStatus,
    PlanProposal,
    validate_transition,
)
from migration_agent.domain.planning import MigrationStep


@pytest.fixture
def host(tmp_path: Path) -> HostProposalService:
    root = tmp_path / "repo"
    shutil.copytree(Path("tests/fixtures/ember-classic-mini"), root)
    for args in [
        ("init",),
        ("add", "."),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Fixture",
        ),
    ]:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    binding = ProjectBinding(root)
    store = SqliteWorkflowStore(tmp_path / "state")
    return HostProposalService(
        binding.project_id,
        root,
        LocalProjectEvidence(root, _create_default_framework_registry()),
        store,
        store,
        "fixture",
        WorkflowAuthorizationFixture(),
    )


def analysis(host: HostProposalService) -> AnalysisProposal:
    state = host.evidence.repository_state()
    path = "app/components/user-card.js"
    text = host.evidence.read_text(path)
    return AnalysisProposal(
        base_revision=state.revision,
        worktree_fingerprint=state.fingerprint,
        summary="Migrate the grounded component",
        findings=(
            AnalysisFinding(
                id="finding-1",
                title="Component",
                description="Ember component",
                category="component",
                severity="low",
                confidence=1,
                evidence_references=(EvidenceReference(path=path, description="Source"),),
            ),
        ),
        citations=(EvidenceCitation(path=path, sha256=hashlib.sha256(text.encode()).hexdigest()),),
    )


def plan_proposal(host: HostProposalService) -> PlanProposal:
    payload = analysis(host)
    operation = host.submit_analysis("analysis-request", payload)
    assert operation.status == OperationStatus.SUCCEEDED
    return PlanProposal(
        base_revision=payload.base_revision,
        worktree_fingerprint=payload.worktree_fingerprint,
        analysis_id=operation.analysis_id or "",
        citations=payload.citations,
        steps=(
            MigrationStep(
                step_id="component-1",
                title="user-card",
                description="Migrate user-card component",
                validation_strategy=["typecheck"],
                expected_files=[payload.citations[0].path],
                evidence=[EvidenceReference(path=payload.citations[0].path, description="Source")],
            ),
        ),
    )


def test_proposal_loop_is_read_only_and_request_idempotent(host: HostProposalService) -> None:
    proposal = plan_proposal(host)
    before = host.evidence.repository_state()
    first = host.submit_plan("plan-request", proposal)
    repeated = host.submit_plan("plan-request", proposal)
    assert first == repeated and first.status == OperationStatus.SUCCEEDED
    saved = host.checkpoints.get_plan(first.plan_id or "")
    assert saved and saved.approval is None and saved.source_root == str(host.root)
    assert host.evidence.repository_state() == before
    assert not (host.root / ".agent").exists()
    with pytest.raises(ValueError, match="REQUEST_CONFLICT"):
        host.submit_plan("plan-request", proposal.model_copy(update={"analysis_id": "different"}))
    record = host.store.get_workflow(host.project_id, saved.plan_id, "component-1")
    assert record.state == Lifecycle.PLAN_SAVED and record.transferable


def test_proposal_rejects_cycle_and_unknown_symbol(host: HostProposalService) -> None:
    payload = analysis(host)
    bad = payload.model_copy(
        update={"citations": (payload.citations[0].model_copy(update={"symbol": "absent_symbol"}),)}
    )
    assert host.submit_analysis("invalid-symbol", bad).status == OperationStatus.FAILED
    proposal = plan_proposal(host)
    step = proposal.steps[0].model_copy(update={"dependencies": ["component-1"]})
    operation = host.submit_plan("cycle", proposal.model_copy(update={"steps": (step,)}))
    assert operation.status == OperationStatus.FAILED and "PLAN_INVALID" in operation.message


def test_evidence_checks_digest_and_line_budget(host: HostProposalService) -> None:
    citation = analysis(host).citations[0]
    excerpt = host.read_evidence((citation,), 1)[0]
    assert excerpt.has_more and excerpt.text
    with pytest.raises(ValueError, match="EVIDENCE_CHANGED"):
        host.read_evidence((citation.model_copy(update={"sha256": "0" * 64}),))
    with pytest.raises(ValueError, match="EVIDENCE_LIMIT"):
        host.read_evidence((citation,), 201)


def test_leases_fence_expired_writers_and_cas(host: HostProposalService) -> None:
    proposal = plan_proposal(host)
    operation = host.submit_plan("plan", proposal)
    first = host.store.acquire_lease(host.project_id, "writer-A")
    with pytest.raises(ValueError, match="WRITER_BUSY"):
        host.store.acquire_lease(host.project_id, "writer-B")
    record = host.store.get_workflow(host.project_id, operation.plan_id or "", "component-1")
    assert isinstance(host.store, SqliteWorkflowStore)
    with host.store._get_connection() as conn:
        conn.execute("UPDATE writer_leases SET expires_at=0 WHERE project_id=?", (host.project_id,))
    second = host.store.acquire_lease(host.project_id, "writer-B")
    assert second.generation == first.generation + 1
    with pytest.raises(ValueError, match="LEASE_LOST"):
        host.store.save_workflow(record, first)
    updated = host.store.save_workflow(
        record.model_copy(update={"state": Lifecycle.STAGE_VERIFIED}), second
    )
    with pytest.raises(ValueError, match="STALE_CHECKPOINT"):
        host.store.save_workflow(record, second)
    with pytest.raises(ValueError, match="INVALID_TRANSITION"):
        host.store.save_workflow(
            updated.model_copy(update={"state": Lifecycle.APPLY_COMPLETED}), second
        )
    host.store.release_lease(second)


def test_drift_invalidates_all_downstream_artifacts(host: HostProposalService) -> None:
    operation = host.submit_plan("plan", plan_proposal(host))
    record = host.store.get_workflow(host.project_id, operation.plan_id or "", "component-1")
    lease = host.store.acquire_lease(host.project_id, "fixture-writer")
    record = host.store.save_workflow(
        record.model_copy(
            update={
                "state": Lifecycle.STAGE_VERIFIED,
                "changeset_id": "cs-old",
                "approval_nonce": "old",
                "validation_digest": "old",
            }
        ),
        lease,
    )
    (host.root / "drift.txt").write_text("drift")
    with pytest.raises(ValueError, match="BASE_CHANGED"):
        host.check_base(record, lease)
    invalidated = host.store.get_workflow(host.project_id, record.plan_id, record.step_id)
    assert invalidated.state == Lifecycle.BASE_CHANGED
    assert invalidated.changeset_id is None and invalidated.approval_nonce is None
    with pytest.raises(ValueError, match="INVALID_TRANSITION"):
        host.store.save_workflow(
            invalidated.model_copy(update={"state": Lifecycle.STAGE_VERIFIED}), lease
        )
    host.store.release_lease(lease)


def test_lock_excludes_another_process(tmp_path: Path) -> None:
    lock = ExclusiveApplyLock(tmp_path / "locks")
    script = (
        "from pathlib import Path\n"
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('apply_lock', sys.argv[2])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "ExclusiveApplyLock = module.ExclusiveApplyLock\ntry:\n"
        " with ExclusiveApplyLock(Path(sys.argv[1])).acquire('project'):\n"
        "  sys.exit(2)\nexcept ValueError as error:\n"
        " sys.exit(0 if str(error).startswith('WRITER_BUSY') else 3)"
    )
    with lock.acquire("project"):
        lock.verify()
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path / "locks"),
                inspect.getfile(ExclusiveApplyLock),
            ],
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0
    with ExclusiveApplyLock(tmp_path / "locks").acquire("project"):
        pass


def test_operations_are_scoped_and_cancellation_is_durable(host: HostProposalService) -> None:
    op, claimed = host.store.claim_request(
        Operation(
            operation_id="op-queued",
            project_id=host.project_id,
            request_id="queued",
            kind="stage",
            payload_digest="digest",
            actor="fixture",
        )
    )
    assert claimed
    with pytest.raises(ValueError, match="OPERATION_NOT_FOUND"):
        host.store.get_operation("foreign", op.operation_id)
    cancelled = host.store.cancel_operation(host.project_id, op.operation_id)
    assert cancelled.status == OperationStatus.CANCELLED
    assert host.store.claim_request(op) == (cancelled, False)


@pytest.mark.parametrize(
    "disk,expected",
    [
        ("target", Lifecycle.APPLY_COMPLETED),
        ("base", Lifecycle.RECOVERY_REQUIRED),
        ("partial", Lifecycle.RECOVERY_REQUIRED),
    ],
)
def test_interrupted_apply_reconciles_without_writing(
    host: HostProposalService, disk: str, expected: Lifecycle
) -> None:
    operation = host.submit_plan("plan", plan_proposal(host))
    record = host.store.get_workflow(host.project_id, operation.plan_id or "", "component-1")
    change = FileChange(
        path="new.txt",
        operation=FileOperation.CREATE,
        content_bytes=b"target",
        content_digest=compute_file_sha256(b"target"),
    )
    changeset = ChangeSet(
        changeset_id="cs-reconcile",
        plan_id=record.plan_id,
        step_id=record.step_id,
        base_revision=record.base_revision,
        worktree_fingerprint=record.worktree_fingerprint,
        changes=(change,),
    )
    changeset = changeset.model_copy(
        update={"changeset_digest": compute_changeset_digest(changeset)}
    )
    host.checkpoints.save_changeset(changeset)
    lease = host.store.acquire_lease(host.project_id, "interrupted")
    for state in [
        Lifecycle.STAGE_VERIFIED,
        Lifecycle.VALIDATION_RUNNING,
        Lifecycle.VALIDATION_PASSED,
        Lifecycle.APPROVAL_PENDING,
        Lifecycle.APPROVAL_RECORDED,
        Lifecycle.APPLY_INTENT,
    ]:
        record = host.store.save_workflow(
            record.model_copy(
                update={
                    "state": state,
                    "changeset_id": changeset.changeset_id,
                    "changeset_digest": changeset.changeset_digest,
                    "backups": (BackupEntry(path="new.txt", existed=False),),
                }
            ),
            lease,
        )
    host.store.release_lease(lease)
    if disk != "base":
        (host.root / "new.txt").write_text("target" if disk == "target" else "partial")
    before = (host.root / "new.txt").read_bytes() if disk != "base" else None
    reconcile_workflows(
        host.project_id, host.store, host.checkpoints, LocalRecoveryProbe(host.root)
    )
    assert (
        host.store.get_workflow(host.project_id, record.plan_id, record.step_id).state == expected
    )
    assert ((host.root / "new.txt").read_bytes() if disk != "base" else None) == before


def test_exactly_twelve_states_and_no_direct_drift_resume() -> None:
    assert len(Lifecycle) == 12
    with pytest.raises(ValueError, match="INVALID_TRANSITION"):
        validate_transition(Lifecycle.BASE_CHANGED, Lifecycle.PLAN_SAVED)
