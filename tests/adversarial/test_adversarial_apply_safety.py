"""Adversarial test suite for Section 15.3: Apply Safety, Staging & Crash Recovery.

Tests security invariants for:
- Conflicting Human Modifications & Path Escapes
- Dry-Run Failure Aborts
- Mid-Apply Failure & Verified Rollback
- Non-Universal Rollback & RecoveryRequired Transition (Invariant 28)
- Checkpoint Store Crash State Recording
"""

from pathlib import Path

from migration_agent.adapters import LocalWorkspaceAdapter
from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.application.transformation import TransformationService
from migration_agent.domain import (
    ApplyStatus,
    ApprovalSignature,
    AssuranceLevel,
    ChangeSet,
    FileChange,
    FileMode,
    FileOperation,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    compute_file_sha256,
    compute_plan_digest,
    compute_worktree_fingerprint,
)


def _make_approved_plan(repo: Path) -> MigrationPlan:
    step = MigrationStep(
        step_id="step-1",
        title="Safe Migration Step",
        description="Apply safe changes",
    )
    plan = MigrationPlan(
        plan_id="plan-safety-test",
        source_root=str(repo),
        run_id="run-safety-1",
        status=PlanStatus.DRAFT,
        steps=[step],
        policy_digest="policy-digest-1",
    )
    digest = compute_plan_digest(plan)
    sig = ApprovalSignature(
        actor="lead-dev",
        plan_digest=digest,
        policy_digest="policy-digest-1",
        signature="lead-sig-1234",
        assurance_level=AssuranceLevel.MODE_B,
    )
    return plan.model_copy(update={"status": PlanStatus.APPROVED, "approval": sig})


def test_path_escape_rejected_at_preflight(tmp_path: Path) -> None:
    """ChangeSet attempting to write outside repository root must be aborted in preflight."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "component.js").write_text("console.log('original');\n", encoding="utf-8")
    fp = compute_worktree_fingerprint(repo)

    plan = _make_approved_plan(repo)
    service = TransformationService(workspace_adapter=LocalWorkspaceAdapter())

    content = b"malicious content"
    malicious_change = FileChange(
        path="../../escaped_file.txt",
        operation=FileOperation.CREATE,
        content_bytes=content,
        content_digest=compute_file_sha256(content),
    )
    cs = ChangeSet(
        changeset_id="cs-escape",
        plan_id=plan.plan_id,
        step_id="step-1",
        base_revision="HEAD",
        worktree_fingerprint=fp,
        changes=(malicious_change,),
        changeset_digest="sha256:escape",
    )

    res = service.apply(repo, cs, plan, actor="operator")
    assert res.status == ApplyStatus.BASE_CHANGED
    assert "escapes repository root" in " ".join(res.diagnostics).lower()

    # Verify no file was written outside repo root
    assert not (tmp_path / "escaped_file.txt").exists()


def test_controlled_apply_failure_triggers_clean_verified_rollback(tmp_path: Path) -> None:
    """Filesystem write error mid-apply must trigger clean rollback and restore prior state."""
    repo = tmp_path / "repo"
    repo.mkdir()
    original_text = "export const original = true;\n"
    (repo / "component.js").write_text(original_text, encoding="utf-8")
    fp = compute_worktree_fingerprint(repo)

    plan = _make_approved_plan(repo)
    service = TransformationService(workspace_adapter=LocalWorkspaceAdapter())

    content = b"export const migrated = true;\n"
    change = FileChange(
        path="component.js",
        operation=FileOperation.MODIFY,
        content_bytes=content,
        content_digest=compute_file_sha256(content),
        file_mode=FileMode.STANDARD,
    )
    cs = ChangeSet(
        changeset_id="cs-rollback-test",
        plan_id=plan.plan_id,
        step_id="step-1",
        base_revision="HEAD",
        worktree_fingerprint=fp,
        changes=(change,),
        changeset_digest="sha256:rollback",
    )

    # Simulate filesystem write failure during apply
    res = service.apply(repo, cs, plan, actor="operator", simulate_apply_failure=True)
    assert res.status == ApplyStatus.ROLLED_BACK
    assert "rollback cleanly executed and verified" in " ".join(res.diagnostics).lower()

    # Original file contents must be completely restored
    assert (repo / "component.js").read_text(encoding="utf-8") == original_text


def test_rollback_failure_transitions_to_recovery_required(tmp_path: Path) -> None:
    """When apply AND rollback fail, transitions explicitly to RecoveryRequired (Invariant 28)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    original_text = "export const config = 'v1';\n"
    (repo / "component.js").write_text(original_text, encoding="utf-8")
    fp = compute_worktree_fingerprint(repo)

    state_dir = tmp_path / "state"
    store = SqliteCheckpointStore(state_dir=state_dir)
    plan = _make_approved_plan(repo)
    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        checkpoint_store=store,
    )

    content = b"export const config = 'v2';\n"
    change = FileChange(
        path="component.js",
        operation=FileOperation.MODIFY,
        content_bytes=content,
        content_digest=compute_file_sha256(content),
    )
    cs = ChangeSet(
        changeset_id="cs-recovery-required",
        plan_id=plan.plan_id,
        step_id="step-1",
        base_revision="HEAD",
        worktree_fingerprint=fp,
        changes=(change,),
        changeset_digest="sha256:rec-req",
    )

    # Simulate both apply failure AND rollback failure
    res = service.apply(
        repo,
        cs,
        plan,
        actor="operator",
        simulate_apply_failure=True,
        simulate_rollback_failure=True,
    )

    # Invariant 28: Explicit transition to RECOVERY_REQUIRED
    assert res.status == ApplyStatus.RECOVERY_REQUIRED
    assert "CRITICAL" in " ".join(res.diagnostics)
    assert "manual operator recovery required" in " ".join(res.diagnostics).lower()
    assert res.recovery_details is not None
    assert "apply_error" in res.recovery_details
    assert "rollback_error" in res.recovery_details
    assert "backup_dir" in res.recovery_details

    # Checkpoint store must have recorded the APPLY_RECOVERY_REQUIRED operational state
    checkpoints = store.list_checkpoints(plan.run_id)
    assert any(c.checkpoint_type == "APPLY_RECOVERY_REQUIRED" for c in checkpoints)
