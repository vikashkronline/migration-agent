"""Unit tests for CLI run lifecycle commands (list, show, resume) and offline evaluation."""

import json
from pathlib import Path

from typer.testing import CliRunner

from migration_agent.adapters import SqliteCheckpointStore
from migration_agent.cli import app
from migration_agent.domain import (
    ApprovalSignature,
    AssuranceLevel,
    ExecutionStep,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    RunRecord,
    compute_plan_digest,
)

runner = CliRunner()


def _create_and_approve_plan(
    fixture_dir: Path, state_dir: Path, output_dir: Path, run_id: str = "run-cli-lifecycle-1"
) -> str:
    plan_step = MigrationStep(
        step_id="step-user-card",
        title="Migrate user card component",
        description="Extract and render user-card",
        expected_files=[
            "src/app/components/user-card/user-card.component.ts",
            "src/app/components/user-card/user-card.component.html",
            "src/app/components/user-card/user-card.component.scss",
            "src/app/components/user-card/user-card.component.spec.ts",
        ],
    )
    plan = MigrationPlan(
        plan_id="plan-cli-lifecycle-1",
        source_root=str(fixture_dir),
        run_id=run_id,
        steps=[plan_step],
        status=PlanStatus.APPROVED,
        policy_digest="policy-cli-digest-1",
    )
    digest = compute_plan_digest(plan)
    sig = ApprovalSignature(
        actor="reviewer",
        plan_digest=digest,
        policy_digest="policy-cli-digest-1",
        signature=f"APPROVED:{digest}:reviewer",
        assurance_level=AssuranceLevel.MODE_B,
    )
    approved_plan = plan.model_copy(update={"approval": sig})

    store = SqliteCheckpointStore(state_dir)
    store.save_plan(approved_plan)
    store.save_approval(approved_plan.plan_id, sig)
    return approved_plan.plan_id


def test_cli_run_list_and_show(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"

    # Initially empty
    list_res = runner.invoke(app, ["run", "list", "--state-dir", str(state_dir)])
    assert list_res.exit_code == 0, list_res.output
    runs = json.loads(list_res.output)
    assert runs == []

    # Insert a run record directly
    store = SqliteCheckpointStore(state_dir)
    store.save_run_record(
        RunRecord(
            run_id="run-test-list",
            plan_id="plan-test-list",
            source_root=str(tmp_path),
            status=ExecutionStep.STAGED,
        )
    )

    list_res2 = runner.invoke(app, ["run", "list", "--state-dir", str(state_dir)])
    assert list_res2.exit_code == 0
    runs2 = json.loads(list_res2.output)
    assert len(runs2) == 1
    assert runs2[0]["run_id"] == "run-test-list"
    assert runs2[0]["status"] == "STAGED"

    # Show existing run
    show_res = runner.invoke(app, ["run", "show", "run-test-list", "--state-dir", str(state_dir)])
    assert show_res.exit_code == 0
    show_data = json.loads(show_res.output)
    assert show_data["run_id"] == "run-test-list"
    assert show_data["status"] == "STAGED"

    # Show non-existent run
    show_res_missing = runner.invoke(
        app, ["run", "show", "run-missing", "--state-dir", str(state_dir)]
    )
    assert show_res_missing.exit_code == 2


def test_cli_run_resume(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "gov"
    report_output_dir = tmp_path / "reports"
    staging_root = tmp_path / "staging"

    run_id = "run-cli-resume-1"
    plan_id = _create_and_approve_plan(fixture_dir, state_dir, output_dir, run_id=run_id)

    # First, stage the run so it's in STAGED state
    stage_res = runner.invoke(
        app,
        [
            "stage",
            str(fixture_dir),
            "--plan",
            plan_id,
            "--state-dir",
            str(state_dir),
            "--staging-root",
            str(staging_root),
        ],
    )
    assert stage_res.exit_code == 0, stage_res.output

    # Checkpoint store now has plan and changeset, create run record at STAGED status
    store = SqliteCheckpointStore(state_dir)
    stage_data = json.loads(stage_res.output)
    store.save_run_record(
        RunRecord(
            run_id=run_id,
            plan_id=plan_id,
            source_root=str(fixture_dir),
            staging_root=stage_data["staging_path"],
            applied_changeset_id=stage_data["changeset_id"],
            status=ExecutionStep.STAGED,
        )
    )

    # Resume the staged run
    resume_res = runner.invoke(
        app,
        [
            "run",
            "resume",
            run_id,
            "--state-dir",
            str(state_dir),
            "--output",
            str(report_output_dir),
            "--fake-runner",
        ],
    )
    assert resume_res.exit_code == 0, resume_res.output
    summary = json.loads(resume_res.output)
    assert summary["status"] == "SUCCESS"
    assert summary["run_id"] == run_id

    # Verify run record in SQLite was updated to COMPLETED
    updated_rec = store.get_run_record(run_id)
    assert updated_rec is not None
    assert updated_rec.status == ExecutionStep.COMPLETED


def test_cli_eval(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"

    res = runner.invoke(
        app,
        [
            "eval",
            str(fixture_dir),
            "--min-precision",
            "0.8",
            "--min-recall",
            "0.8",
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["status"] == "ok"
    assert data["metrics"]["precision"] >= 0.8
    assert data["metrics"]["recall"] >= 0.8
    assert "user-card" in data["detected_components"]
