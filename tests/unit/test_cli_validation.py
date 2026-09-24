"""CLI integration tests for 'agent validate' and 'agent run'."""

import json
from pathlib import Path

from typer.testing import CliRunner

from migration_agent.cli import app

runner = CliRunner()


def _create_and_approve_plan(
    fixture_dir: Path,
    state_dir: Path,
    output_dir: Path,
) -> str:
    """Helper to generate and approve a plan using the CLI."""
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


def test_cli_validate_success(tmp_path: Path) -> None:
    workspace = tmp_path / "staging"
    workspace.mkdir()

    res = runner.invoke(
        app,
        [
            "validate",
            str(workspace),
            "--fake-runner",
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["status"] == "ok"
    assert len(data["validation_results"]) > 0
    assert all(r["status"] == "PASSED" for r in data["validation_results"])


def test_cli_validate_profile_filter(tmp_path: Path) -> None:
    workspace = tmp_path / "staging"
    workspace.mkdir()

    res = runner.invoke(
        app,
        [
            "validate",
            str(workspace),
            "--profile",
            "LINT",
            "--fake-runner",
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["status"] == "ok"
    assert len(data["validation_results"]) == 1
    assert data["validation_results"][0]["profile"] == "LINT"


def test_cli_validate_invalid_profile(tmp_path: Path) -> None:
    workspace = tmp_path / "staging"
    workspace.mkdir()

    res = runner.invoke(
        app,
        [
            "validate",
            str(workspace),
            "--profile",
            "INVALID_PROFILE",
            "--fake-runner",
        ],
    )
    assert res.exit_code == 2
    assert "Invalid profile" in res.output


def test_cli_validate_failure(tmp_path: Path) -> None:
    workspace = tmp_path / "staging"
    workspace.mkdir()

    res = runner.invoke(
        app,
        [
            "validate",
            str(workspace),
            "--fake-runner",
            "--fail-validation",
        ],
    )
    assert res.exit_code == 2
    data = json.loads(res.output)
    assert data["status"] == "failed"
    assert any(r["status"] == "FAILED" for r in data["validation_results"])


def test_cli_run_end_to_end_success(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "gov"
    report_output_dir = tmp_path / "reports"

    plan_id = _create_and_approve_plan(fixture_dir, state_dir, output_dir)

    res = runner.invoke(
        app,
        [
            "run",
            str(fixture_dir),
            "--plan",
            plan_id,
            "--output",
            str(report_output_dir),
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
            "--fake-runner",
        ],
    )
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["status"] == "SUCCESS"
    assert Path(data["json_report_path"]).is_file()
    assert Path(data["md_report_path"]).is_file()


def test_cli_run_unapproved_plan_rejected(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "gov"

    # Create plan but DO NOT approve it
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
    assert create_res.exit_code == 0
    plan_id = json.loads(create_res.output)["plan_id"]

    res = runner.invoke(
        app,
        [
            "run",
            str(fixture_dir),
            "--plan",
            plan_id,
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
            "--fake-runner",
        ],
    )
    assert res.exit_code == 2
    assert "Cannot run unapproved or modified plan" in res.output


def test_cli_run_with_auto_repair(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "gov"

    plan_id = _create_and_approve_plan(fixture_dir, state_dir, output_dir)

    res = runner.invoke(
        app,
        [
            "run",
            str(fixture_dir),
            "--plan",
            plan_id,
            "--auto-repair",
            "--max-repairs",
            "2",
            "--output",
            str(tmp_path / "reports"),
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
            "--fake-runner",
            "--fail-validation",
        ],
    )
    # Because validation was simulated to always fail, the repair loop will attempt repairs and fail
    assert res.exit_code == 2
    data = json.loads(res.output)
    assert data["status"] == "FAILED"
    assert data["repair_attempts_count"] > 0
