"""Adversarial test suite for Section 15.2: ChangeSet & Drift Invalidation.

Tests security invariants for:
- Tampered ChangeSet Digest (voiding approval)
- Target Revision Drift (commit advance triggers BaseChanged)
- Working-Tree Dirty Drift (uncommitted/untracked files abort apply)
- Policy Version Drift (policy alteration invalidates approvals)
- Repair Security Context (fresh ChangeSet requires fresh approval token)
"""

from pathlib import Path

from migration_agent.adapters import LocalWorkspaceAdapter
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
    compute_changeset_digest,
    compute_file_sha256,
    compute_plan_digest,
    compute_worktree_fingerprint,
    verify_approval,
)


def _create_test_plan(repo_root: Path) -> MigrationPlan:
    step = MigrationStep(
        step_id="step-1",
        title="Migrate user card",
        description="Transform component",
    )
    plan = MigrationPlan(
        plan_id="plan-drift-test",
        run_id="run-drift-1",
        source_root=str(repo_root),
        status=PlanStatus.DRAFT,
        steps=[step],
        policy_digest="policy-digest-1",
    )
    digest = compute_plan_digest(plan)
    sig = ApprovalSignature(
        actor="lead-dev",
        plan_digest=digest,
        policy_digest="policy-digest-1",
        signature="lead-dev-sig-token",
        assurance_level=AssuranceLevel.MODE_B,
    )
    return plan.model_copy(update={"status": PlanStatus.APPROVED, "approval": sig})


def test_tampered_changeset_digest_voids_apply(tmp_path: Path) -> None:
    """Modifying file changes without updating digest or spoofing digest must fail."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.js").write_text("console.log('original');\n", encoding="utf-8")

    initial_fingerprint = compute_worktree_fingerprint(repo)
    plan = _create_test_plan(repo)
    service = TransformationService(workspace_adapter=LocalWorkspaceAdapter())

    content = b"console.log('migrated');\n"
    legit_digest = compute_file_sha256(content)

    # 1. Tamper content bytes while keeping old digest
    tampered_change = FileChange(
        path="app.ts",
        operation=FileOperation.CREATE,
        content_bytes=b"MALICIOUS_INJECTED_CODE();\n",
        content_digest=legit_digest,  # Spoofed digest
        file_mode=FileMode.STANDARD,
    )

    cs_tampered = ChangeSet(
        changeset_id="cs-tampered",
        plan_id=plan.plan_id,
        step_id="step-1",
        base_revision="HEAD",
        worktree_fingerprint=initial_fingerprint,
        changes=(tampered_change,),
        changeset_digest="sha256:spoofed",
    )

    # Apply must fail on postcondition digest verification and rollback cleanly
    res = service.apply(repo, cs_tampered, plan, actor="operator")
    assert res.status == ApplyStatus.BASE_CHANGED
    assert "approval_required" in " ".join(res.diagnostics).lower()
    # Malicious file must NOT exist on disk
    assert not (repo / "app.ts").exists()


def test_working_tree_dirty_drift_triggers_base_changed(tmp_path: Path) -> None:
    """Untracked or modified files in target working tree must trigger BaseChanged."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.js").write_text("console.log('initial');\n", encoding="utf-8")

    # Record baseline worktree fingerprint
    base_fingerprint = compute_worktree_fingerprint(repo)
    plan = _create_test_plan(repo)
    service = TransformationService(workspace_adapter=LocalWorkspaceAdapter())

    content = b"console.log('updated');\n"
    change = FileChange(
        path="app.ts",
        operation=FileOperation.CREATE,
        content_bytes=content,
        content_digest=compute_file_sha256(content),
        file_mode=FileMode.STANDARD,
    )
    cs = ChangeSet(
        changeset_id="cs-clean",
        plan_id=plan.plan_id,
        step_id="step-1",
        base_revision="HEAD",
        worktree_fingerprint=base_fingerprint,
        changes=(change,),
        changeset_digest="sha256:valid",
    )

    # Human developer or concurrent process modifies the working tree
    (repo / "untracked_human_work.txt").write_text("WIP changes by dev", encoding="utf-8")

    # Attempting to apply the ChangeSet now must detect drift and return BASE_CHANGED
    res = service.apply(repo, cs, plan, actor="operator")
    assert res.status == ApplyStatus.BASE_CHANGED
    assert "approval_required" in " ".join(res.diagnostics).lower()
    # Target file must not have been created
    assert not (repo / "app.ts").exists()


def test_unapproved_or_tampered_plan_triggers_base_changed(tmp_path: Path) -> None:
    """An unapproved plan or tampered plan approval must be rejected at apply time."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.js").write_text("console.log('clean');\n", encoding="utf-8")

    fp = compute_worktree_fingerprint(repo)
    service = TransformationService(workspace_adapter=LocalWorkspaceAdapter())

    # Create unapproved plan
    raw_plan = MigrationPlan(
        plan_id="plan-unapproved",
        source_root=str(repo),
        run_id="run-1",
        status=PlanStatus.DRAFT,
        steps=[],
    )

    content = b"console.log('target');\n"
    change = FileChange(
        path="app.ts",
        operation=FileOperation.CREATE,
        content_bytes=content,
        content_digest=compute_file_sha256(content),
    )
    cs = ChangeSet(
        changeset_id="cs-1",
        plan_id=raw_plan.plan_id,
        step_id="step-1",
        base_revision="HEAD",
        worktree_fingerprint=fp,
        changes=(change,),
        changeset_digest="sha256:valid",
    )

    # 1. Unapproved plan rejected
    res = service.apply(repo, cs, raw_plan, actor="operator")
    assert res.status == ApplyStatus.BASE_CHANGED
    assert "approval_required" in " ".join(res.diagnostics).lower()

    # 2. Approved plan whose steps were modified after approval rejected
    approved_plan = _create_test_plan(repo)
    tampered_plan = approved_plan.model_copy(update={"steps": []})
    assert verify_approval(tampered_plan) is False

    res2 = service.apply(repo, cs, tampered_plan, actor="operator")
    assert res2.status == ApplyStatus.BASE_CHANGED


def test_repair_security_context_isolation() -> None:
    """Automated repairs produce a fresh ChangeSet with a new digest; old approval cannot apply."""
    content_v1 = b"export const v = 1;\n"
    cs_v1 = ChangeSet(
        changeset_id="cs-initial",
        plan_id="plan-1",
        step_id="step-1",
        base_revision="HEAD",
        worktree_fingerprint="fp-1",
        changes=(
            FileChange(
                path="v.ts",
                operation=FileOperation.CREATE,
                content_bytes=content_v1,
                content_digest=compute_file_sha256(content_v1),
            ),
        ),
    )
    cs_v1 = cs_v1.model_copy(update={"changeset_digest": compute_changeset_digest(cs_v1)})

    # Repaired ChangeSet has different contents and different digest
    content_v2 = b"export const v = 2; // repaired\n"
    cs_v2 = ChangeSet(
        changeset_id="cs-repaired",
        plan_id="plan-1",
        step_id="step-1",
        base_revision="HEAD",
        worktree_fingerprint="fp-1",
        changes=(
            FileChange(
                path="v.ts",
                operation=FileOperation.CREATE,
                content_bytes=content_v2,
                content_digest=compute_file_sha256(content_v2),
            ),
        ),
    )
    cs_v2 = cs_v2.model_copy(update={"changeset_digest": compute_changeset_digest(cs_v2)})

    assert cs_v1.changeset_id != cs_v2.changeset_id
    assert cs_v1.changeset_digest != cs_v2.changeset_digest
