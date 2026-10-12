"""Unit tests for specialist subagent CLI integration."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migration_agent.cli import app

runner = CliRunner()
pytestmark = pytest.mark.usefixtures("cli_workflow_authorization")


def test_cli_plan_create_with_critic(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    result = runner.invoke(
        app,
        [
            "plan",
            "create",
            str(fixture_path),
            "--output",
            str(tmp_path),
            "--fake-runtime",
            "--critic",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["critic_enabled"] is True
    assert data["status"].lower() in ("needs_approval", "draft")
    assert "warnings" in data
    assert any("Plan critic evaluated" in w or "GENERAL" in w for w in data["warnings"])


def test_cli_eval_with_specialists() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    result = runner.invoke(
        app,
        [
            "eval",
            str(fixture_path),
            "--with-specialists",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "specialist_metrics" in data
    spec = data["specialist_metrics"]
    assert spec["turns_used"] >= 2
    assert spec["cost_usd"] > 0.0
    assert spec["plan_critique_score"] is not None
    assert spec["improvement_detected"] is True
