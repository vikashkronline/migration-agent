"""Unit tests for TransformationService, ChangeSet preview, staging, and ADR-8 controlled apply."""

import shutil
from pathlib import Path

import pytest

from migration_agent.adapters import (
    AngularStandaloneComponentRenderer,
    EmberClassicComponentExtractor,
    LocalWorkspaceAdapter,
    SqliteCheckpointStore,
)
from migration_agent.application import TransformationService
from migration_agent.domain import (
    ApplyStatus,
    ApprovalSignature,
    AssuranceLevel,
    EvidenceReference,
    EvidenceStatus,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    StepRisk,
    compute_plan_digest,
)


def _approved_plan(repo_root: Path) -> MigrationPlan:
    step = MigrationStep(
        step_id="step-001",
        title="Migrate user card",
        description="Transform user-card to Angular",
        dependencies=[],
        scope="component",
        risk=StepRisk.LOW,
        confidence=1.0,
        evidence=[
            EvidenceReference(
                path="app/components/user-card.js",
                description="Ember component",
                line_number=1,
                sample="Component.extend({",
                status=EvidenceStatus.VALID,
            )
        ],
        expected_files=["src/app/components/user-card/user-card.component.ts"],
        validation_strategy=["ng test"],
        rollback_note="revert",
        acceptance_criteria=["compiles"],
        unresolved_questions=[],
    )

    preliminary_plan = MigrationPlan(
        plan_id="plan-test-001",
        source_root=str(repo_root),
        run_id="run-test-001",
        status=PlanStatus.NEEDS_APPROVAL,
        steps=[step],
        policy_digest="sha256:default-policy",
    )

    plan_digest = compute_plan_digest(preliminary_plan)
    approval = ApprovalSignature(
        actor="operator",
        plan_digest=plan_digest,
        policy_digest="sha256:default-policy",
        assurance_level=AssuranceLevel.MODE_B,
        signature=f"sig:{plan_digest[:16]}",
    )

    return preliminary_plan.model_copy(
        update={
            "status": PlanStatus.APPROVED,
            "approval": approval,
        }
    )


def _setup_fixture_repo(tmp_path: Path) -> Path:
    fixture_src = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    repo_dst = tmp_path / "repo"
    shutil.copytree(fixture_src, repo_dst)
    return repo_dst


def test_preview_generates_changeset_and_diff(tmp_path: Path) -> None:
    repo = _setup_fixture_repo(tmp_path)
    plan = _approved_plan(repo)

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
    )

    changeset, diff_text = service.preview(repo, plan)

    assert changeset.plan_id == plan.plan_id
    assert len(changeset.changes) == 4
    assert any(c.path.endswith("user-card.component.ts") for c in changeset.changes)
    assert any(c.path.endswith("user-card.component.html") for c in changeset.changes)
    assert any(c.path.endswith("user-card.component.scss") for c in changeset.changes)
    assert any(c.path.endswith("user-card.component.spec.ts") for c in changeset.changes)
    assert "UserCardComponent" in diff_text
    assert changeset.changeset_digest.startswith("sha256:")


def test_stage_rejects_unapproved_plan(tmp_path: Path) -> None:
    repo = _setup_fixture_repo(tmp_path)
    plan = _approved_plan(repo).model_copy(update={"status": PlanStatus.DRAFT, "approval": None})

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
    )

    with pytest.raises(ValueError, match="Cannot stage unapproved"):
        service.stage(tmp_path / "staging", "run-1", repo, plan)


def test_stage_materializes_changes_in_isolated_staging(tmp_path: Path) -> None:
    repo = _setup_fixture_repo(tmp_path)
    plan = _approved_plan(repo)
    staging_root = tmp_path / "staging"
    state_dir = tmp_path / "state"
    checkpoint_store = SqliteCheckpointStore(state_dir)

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
    )

    stg_dir, cs = service.stage(staging_root, "run-stage-001", repo, plan)

    target_ts = "src/app/components/user-card/user-card.component.ts"
    assert stg_dir.exists()
    assert (stg_dir / target_ts).exists()
    assert cs.plan_id == plan.plan_id

    # Verify audit event and checkpoint were recorded
    events = checkpoint_store.audit_log_path.read_text(encoding="utf-8")
    assert "CHANGESET_STAGED" in events


def test_apply_success_with_backup_and_postconditions(tmp_path: Path) -> None:
    repo = _setup_fixture_repo(tmp_path)
    plan = _approved_plan(repo)
    state_dir = tmp_path / "state"
    checkpoint_store = SqliteCheckpointStore(state_dir)

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
    )

    changeset, _ = service.preview(repo, plan)
    result = service.apply(
        source_root=repo,
        changeset=changeset,
        plan=plan,
        actor="operator",
        backup_root=tmp_path / "backups",
    )

    target_ts = "src/app/components/user-card/user-card.component.ts"
    assert result.status == ApplyStatus.APPLIED
    assert len(result.applied_paths) == 4
    assert (repo / target_ts).exists()


def test_apply_drift_aborts_with_base_changed(tmp_path: Path) -> None:
    repo = _setup_fixture_repo(tmp_path)
    plan = _approved_plan(repo)

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
    )

    changeset, _ = service.preview(repo, plan)

    # Induce drift in target working tree
    drift_file = repo / "drift.txt"
    drift_file.write_text("untracked modification", encoding="utf-8")

    result = service.apply(
        source_root=repo,
        changeset=changeset,
        plan=plan,
        actor="operator",
    )

    target_ts = "src/app/components/user-card/user-card.component.ts"
    assert result.status == ApplyStatus.BASE_CHANGED
    assert "drifted" in result.diagnostics[0]
    # Generated files must NOT exist
    assert not (repo / target_ts).exists()


def test_apply_verified_rollback_on_failure(tmp_path: Path) -> None:
    repo = _setup_fixture_repo(tmp_path)
    plan = _approved_plan(repo)

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
    )

    changeset, _ = service.preview(repo, plan)

    result = service.apply(
        source_root=repo,
        changeset=changeset,
        plan=plan,
        actor="operator",
        simulate_apply_failure=True,
    )

    target_ts = "src/app/components/user-card/user-card.component.ts"
    assert result.status == ApplyStatus.ROLLED_BACK
    assert "Rollback cleanly executed and verified" in result.diagnostics[0]
    # No partial files left behind
    assert not (repo / target_ts).exists()


def test_apply_double_fault_transitions_to_recovery_required(tmp_path: Path) -> None:
    repo = _setup_fixture_repo(tmp_path)
    plan = _approved_plan(repo)

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
    )

    changeset, _ = service.preview(repo, plan)

    result = service.apply(
        source_root=repo,
        changeset=changeset,
        plan=plan,
        actor="operator",
        simulate_apply_failure=True,
        simulate_rollback_failure=True,
    )

    assert result.status == ApplyStatus.RECOVERY_REQUIRED
    assert "RECOVERY_REQUIRED" in result.status.value
    assert result.recovery_details is not None
    assert "Simulated failure restoring backup files" in result.recovery_details["rollback_error"]
