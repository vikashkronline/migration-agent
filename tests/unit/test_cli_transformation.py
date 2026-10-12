"""CLI integration tests for 'agent preview', 'agent stage', and 'agent apply'."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migration_agent.cli import app

runner = CliRunner()
pytestmark = pytest.mark.usefixtures("cli_workflow_authorization")


def _create_and_approve_plan(
    fixture_dir: Path,
    state_dir: Path,
    output_dir: Path,
) -> str:
    """Generate plan sign-off, which does not authorize source apply."""
    if fixture_dir.is_relative_to(state_dir.parent) and not (fixture_dir / ".git").exists():
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
            subprocess.run(["git", *args], cwd=fixture_dir, check=True, capture_output=True)
    create_res = runner.invoke(
        app,
        [
            "plan",
            "create",
            str(fixture_dir),
            "--output",
            str(output_dir),
            "--state-dir",
            str(state_dir),
            "--fake-runtime",
        ],
    )
    assert create_res.exit_code == 0, create_res.output
    plan_id = json.loads(create_res.output)["plan_id"]

    approve_res = runner.invoke(
        app,
        [
            "plan",
            "approve",
            plan_id,
            "--actor",
            "test-operator",
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
        ],
    )
    assert approve_res.exit_code == 0, approve_res.output
    return plan_id


def test_cli_preview_lifecycle(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    plan_output = tmp_path / "plan_gov"
    preview_output = tmp_path / "preview_out"

    plan_id = _create_and_approve_plan(fixture_dir, state_dir, plan_output)

    res = runner.invoke(
        app,
        [
            "preview",
            str(fixture_dir),
            "--plan",
            plan_id,
            "--output",
            str(preview_output),
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(plan_output),
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["status"] == "ok"
    assert data["plan_id"] == plan_id
    assert data["file_count"] == 4
    assert (preview_output / "changeset.json").exists()
    assert (preview_output / "preview.diff").exists()


def test_cli_preview_nonexistent_plan(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    res = runner.invoke(
        app,
        [
            "preview",
            str(fixture_dir),
            "--plan",
            "plan-nonexistent",
            "--state-dir",
            str(tmp_path / "state"),
        ],
    )
    assert res.exit_code == 2


def test_cli_stage_lifecycle(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "repo"
    shutil.copytree(Path(__file__).parents[1] / "fixtures" / "ember-classic-mini", fixture_dir)
    state_dir = tmp_path / "state"
    plan_output = tmp_path / "plan_gov"
    staging_root = tmp_path / "staging_root"

    plan_id = _create_and_approve_plan(fixture_dir, state_dir, plan_output)

    res = runner.invoke(
        app,
        [
            "stage",
            str(fixture_dir),
            "--plan",
            plan_id,
            "--staging-root",
            str(staging_root),
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(plan_output),
        ],
    )
    assert res.exit_code == 2, res.output
    assert "STEP_REQUIRED" in res.output
    assert not staging_root.exists()


def test_cli_stage_unapproved_plan_rejected(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    plan_output = tmp_path / "plan_gov"

    # Create plan but DO NOT approve it
    create_res = runner.invoke(
        app,
        [
            "plan",
            "create",
            str(fixture_dir),
            "--output",
            str(plan_output),
            "--state-dir",
            str(state_dir),
            "--fake-runtime",
        ],
    )
    assert create_res.exit_code == 0
    plan_id = json.loads(create_res.output)["plan_id"]

    res = runner.invoke(
        app,
        [
            "stage",
            str(fixture_dir),
            "--plan",
            plan_id,
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(plan_output),
        ],
    )
    assert res.exit_code == 2
    assert "STEP_REQUIRED" in res.output


def test_cli_apply_lifecycle(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    target_repo = tmp_path / "target_repo"
    shutil.copytree(fixture_dir, target_repo)

    state_dir = tmp_path / "state"
    plan_output = tmp_path / "plan_gov"
    backup_root = tmp_path / "backups"

    plan_id = _create_and_approve_plan(target_repo, state_dir, plan_output)

    apply_res = runner.invoke(
        app,
        [
            "apply",
            str(target_repo),
            "--plan",
            plan_id,
            "--actor",
            "test-operator",
            "--backup-root",
            str(backup_root),
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(plan_output),
        ],
    )
    assert apply_res.exit_code == 2, apply_res.output
    assert "CHANGESET_REQUIRED" in apply_res.output
    assert (
        target_repo / "src" / "app" / "components" / "user-card" / "user-card.component.ts"
    ).exists() is False
    assert not backup_root.exists()


def test_cli_apply_drift_aborts(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    target_repo = tmp_path / "target_repo"
    shutil.copytree(fixture_dir, target_repo)

    state_dir = tmp_path / "state"
    plan_output = tmp_path / "plan_gov"

    plan_id = _create_and_approve_plan(target_repo, state_dir, plan_output)

    # First preview to create and store the ChangeSet
    prev_res = runner.invoke(
        app,
        [
            "preview",
            str(target_repo),
            "--plan",
            plan_id,
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(plan_output),
        ],
    )
    assert prev_res.exit_code == 0
    cs_id = json.loads(prev_res.output)["changeset_id"]

    # Now induce drift in the target repository
    (target_repo / "untracked.txt").write_text("drift", encoding="utf-8")

    # Apply with that changeset must detect drift and fail
    apply_res = runner.invoke(
        app,
        [
            "apply",
            str(target_repo),
            "--plan",
            plan_id,
            "--changeset",
            cs_id,
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(plan_output),
        ],
    )
    assert apply_res.exit_code == 2
    assert "WORKFLOW_NOT_FOUND" in apply_res.output
