"""Unit tests for ControlApiService application logic and mutating idempotency."""

from pathlib import Path

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.application.control_service import ControlApiService
from migration_agent.domain import (
    ApprovePlanPayload,
    ChangeSet,
    ExecutionStep,
    FileChange,
    FileOperation,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    RunRecord,
    StepRisk,
)


def test_control_api_service_health() -> None:
    service = ControlApiService()
    health = service.get_health()
    assert health.status == "ok"
    assert len(health.checks) >= 2


def test_control_api_service_runs_and_diff(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints.db"
    store = SqliteCheckpointStore(db_path)

    # Create dummy target file
    src_file = tmp_path / "src" / "sample.txt"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_text("line 1\nline 2\n", encoding="utf-8")

    # Save a changeset
    cs = ChangeSet(
        changeset_id="cs-1",
        plan_id="plan-1",
        step_id="step-1",
        base_revision="rev-0",
        worktree_fingerprint="fp-0",
        changes=(
            FileChange(
                path="src/sample.txt",
                operation=FileOperation.MODIFY,
                content_bytes=b"line 1\nline 2 modified\nline 3\n",
            ),
        ),
    )
    store.save_changeset(cs)

    # Save a run
    store.save_run_record(
        RunRecord(
            run_id="run-101",
            plan_id="plan-1",
            source_root=str(tmp_path),
            status=ExecutionStep.COMPLETED,
            applied_changeset_id="cs-1",
        )
    )

    service = ControlApiService(checkpoint_port=store)
    runs = service.list_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].run_id == "run-101"

    detail = service.get_run("run-101", tmp_path)
    assert detail.run_id == "run-101"
    assert detail.status == "COMPLETED"

    diff = service.get_diff("run-101", tmp_path)
    assert diff.total_files == 1
    assert diff.total_additions > 0
    assert diff.is_clean is False
    assert "line 2 modified" in diff.files[0].patch


def test_control_api_mutating_idempotency(tmp_path: Path) -> None:
    db_path = tmp_path / "checkpoints.db"
    store = SqliteCheckpointStore(db_path)
    gov = GitGovernanceAdapter()

    plan = MigrationPlan(
        plan_id="plan-idem",
        run_id="run-idem",
        source_root=str(tmp_path),
        steps=[
            MigrationStep(
                step_id="step-1",
                title="Initialize",
                description="Setup config",
                risk=StepRisk.LOW,
            )
        ],
        status=PlanStatus.NEEDS_APPROVAL,
    )
    store.save_plan(plan)

    service = ControlApiService(checkpoint_port=store, governance_port=gov)
    payload = ApprovePlanPayload(actor="lead-dev", request_id="idemp-key-999")

    # First approval
    view1 = service.approve_plan("plan-idem", payload, tmp_path)
    assert view1.is_approved is True
    assert view1.approval_signature is not None
    assert view1.approval_signature["actor"] == "lead-dev"

    # Second approval with identical request_id returns cached view
    view2 = service.approve_plan("plan-idem", payload, tmp_path)
    assert view1 is view2  # Cached instance returned
