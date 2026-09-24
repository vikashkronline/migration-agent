"""CLI integration unit tests for 'agent plan' and 'migration-agent plan' commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from migration_agent.cli import app

runner = CliRunner()


def test_cli_plan_lifecycle_with_fake_runtime(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "output"

    # 1. agent plan create
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
    create_data = json.loads(create_res.output)
    assert create_data["status"] == "NEEDS_APPROVAL"
    assert create_data["is_valid"] is True
    assert create_data["step_count"] >= 1
    plan_id = create_data["plan_id"]
    assert plan_id.startswith("plan-")

    # 2. agent plan show (JSON format)
    show_res = runner.invoke(
        app,
        [
            "plan",
            "show",
            plan_id,
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
        ],
    )
    assert show_res.exit_code == 0, show_res.output
    plan_json = json.loads(show_res.output)
    assert plan_json["plan_id"] == plan_id
    assert plan_json["status"] == "NEEDS_APPROVAL"

    # 3. agent plan show (Summary format)
    show_sum_res = runner.invoke(
        app,
        [
            "plan",
            "show",
            plan_id,
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
            "--format",
            "summary",
        ],
    )
    assert show_sum_res.exit_code == 0, show_sum_res.output
    assert f"Plan ID:        {plan_id}" in show_sum_res.output
    assert "Status:         NEEDS_APPROVAL" in show_sum_res.output

    # 4. agent plan approve
    approve_res = runner.invoke(
        app,
        [
            "plan",
            "approve",
            plan_id,
            "--actor",
            "tech-lead",
            "--assurance-level",
            "MODE_B",
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
        ],
    )
    assert approve_res.exit_code == 0, approve_res.output
    approve_data = json.loads(approve_res.output)
    assert approve_data["status"] == "APPROVED"
    assert approve_data["actor"] == "tech-lead"
    assert approve_data["assurance_level"] == "MODE_B"
    assert approve_data["plan_digest"].startswith("sha256:")

    # 5. Verify show shows approved status
    show_after_approve = runner.invoke(
        app,
        [
            "plan",
            "show",
            plan_id,
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
        ],
    )
    assert show_after_approve.exit_code == 0
    approved_json = json.loads(show_after_approve.output)
    assert approved_json["status"] == "APPROVED"
    assert approved_json["approval"]["actor"] == "tech-lead"


def test_cli_plan_reject(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "output"

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

    reject_res = runner.invoke(
        app,
        [
            "plan",
            "reject",
            plan_id,
            "--reason",
            "Missing integration test strategy",
            "--actor",
            "reviewer",
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
        ],
    )
    assert reject_res.exit_code == 0, reject_res.output
    reject_data = json.loads(reject_res.output)
    assert reject_data["status"] == "REJECTED"
    assert reject_data["rejection_reason"] == "Missing integration test strategy"


def test_cli_plan_mode_c_cannot_approve(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    output_dir = tmp_path / "output"

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
    plan_id = json.loads(create_res.output)["plan_id"]

    approve_res = runner.invoke(
        app,
        [
            "plan",
            "approve",
            plan_id,
            "--actor",
            "anonymous",
            "--assurance-level",
            "MODE_C",
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(output_dir),
        ],
    )
    assert approve_res.exit_code == 2
    assert "Mode C (unauthenticated) cannot approve" in approve_res.output


def test_cli_plan_show_nonexistent(tmp_path: Path) -> None:
    res = runner.invoke(
        app,
        [
            "plan",
            "show",
            "plan-ghost-999",
            "--state-dir",
            str(tmp_path),
        ],
    )
    assert res.exit_code == 2
    assert "Plan 'plan-ghost-999' not found." in res.output
