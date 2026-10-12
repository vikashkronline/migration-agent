"""Setup diagnostics expose blockers without certifying migration readiness."""

import json
from pathlib import Path

from typer.testing import CliRunner

from migration_agent.application.doctor import collect_diagnostics, validation_setup_diagnostics
from migration_agent.cli import app
from migration_agent.config import Settings
from migration_agent.domain.execution import ValidationMode


def test_doctor_reports_canonical_model_configuration() -> None:
    report = collect_diagnostics(settings=Settings(runtime_model="configured", agent_model=None))
    check = next(c for c in report["checks"] if c["name"] == "model_configuration")
    assert check["details"]["configured"] is True


def test_restricted_reports_execution_and_browser_prerequisites() -> None:
    report = validation_setup_diagnostics(
        Settings(
            validation_mode=ValidationMode.RESTRICTED,
            browser_validation_plan=None,
        )
    )
    assert report.missing_prerequisites == (
        "execution_backend_selection",
        "browser_validation_plan",
    )
    assert report.repository_code_executed is False


def test_native_missing_paths_are_visible(tmp_path: Path) -> None:
    report = validation_setup_diagnostics(
        Settings(
            validation_mode=ValidationMode.NATIVE,
            native_toolchain_root=tmp_path / "missing-tools",
            native_dependencies_root=tmp_path / "missing-dependencies",
            browser_validation_plan=tmp_path / "missing-plan.json",
        )
    )
    assert "external_native_toolchain" in report.missing_prerequisites
    assert "external_offline_dependencies" in report.missing_prerequisites
    assert "per_step_human_execution_consent" in report.missing_prerequisites
    assert "browser_validation_plan" in report.missing_prerequisites


def test_cli_validation_status_contains_setup(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import Mock

    import migration_agent.adapters.workflow_cli as module

    runtime = Mock()
    runtime.settings = Settings(
        validation_mode=ValidationMode.RESTRICTED, browser_validation_plan=None
    )
    runtime.store.list_workflows.return_value = []
    monkeypatch.setattr(module, "WorkflowRuntime", Mock(return_value=runtime))
    result = CliRunner().invoke(
        app,
        [
            "validation",
            "status",
            "--project-root",
            str(tmp_path),
            "--state-dir",
            str(tmp_path / "state"),
            "--staging-root",
            str(tmp_path / "staging"),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["setup"]["missing_prerequisites"] == [
        "execution_backend_selection",
        "browser_validation_plan",
    ]
    assert data["consents"] == []
    runtime.close.assert_called_once()
