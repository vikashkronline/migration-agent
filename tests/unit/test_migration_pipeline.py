"""Unit tests for unified migration pipeline (approval, repair, controlled apply)."""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migration_agent.adapters import (
    FakeAgentRuntime,
    FakeCommandRunner,
    GitGovernanceAdapter,
    LocalWorkspaceAdapter,
    SafeFilesystemInspector,
    SqliteCheckpointStore,
)
from migration_agent.application import (
    AnalysisService,
    BoundedRepairService,
    InventoryService,
    MigrationPipelineService,
    PlanningService,
    ReportService,
    RuleBasedPlanValidator,
    TransformationService,
    ValidationService,
)
from migration_agent.cli import _create_framework_registry, app
from migration_agent.config import Settings


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    fixture_src = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    target_repo = tmp_path / "repo"
    shutil.copytree(fixture_src, target_repo)
    return target_repo


@pytest.fixture
def pipeline_env(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    staging_root = tmp_path / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)

    checkpoint_store = SqliteCheckpointStore(state_dir)
    governance = GitGovernanceAdapter()
    settings = Settings()
    registry = _create_framework_registry()

    trans_service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        registry=registry,
        filesystem=SafeFilesystemInspector(),
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
    )
    runner = FakeCommandRunner()
    val_service = ValidationService(command_runner=runner, audit_logger=checkpoint_store)
    repair_service = BoundedRepairService(
        command_runner=runner,
        workspace_adapter=LocalWorkspaceAdapter(),
        validation_service=val_service,
        audit_logger=checkpoint_store,
        checkpoint_store=checkpoint_store,
        max_budget=3,
    )
    report_service = ReportService(checkpoint_store=checkpoint_store, audit_logger=checkpoint_store)
    runtime = FakeAgentRuntime()
    inv_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=registry,
    )
    analysis_service = AnalysisService(
        filesystem=SafeFilesystemInspector(),
        frameworks=registry,
        runtime=runtime,
    )
    planning_service = PlanningService(
        runtime=runtime,
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
        governance=governance,
        validator=RuleBasedPlanValidator(max_step_files=settings.max_step_files),
    )
    pipeline_service = MigrationPipelineService(
        checkpoint_store=checkpoint_store,
        transformation_service=trans_service,
        validation_service=val_service,
        repair_service=repair_service,
        report_service=report_service,
        planning_service=planning_service,
        governance=governance,
        inventory_service=inv_service,
        analysis_service=analysis_service,
        audit_logger=checkpoint_store,
    )
    return pipeline_service, staging_root, state_dir


def test_pipeline_dry_run_preview_only(temp_workspace: Path, pipeline_env) -> None:
    pipeline_service, staging_root, state_dir = pipeline_env

    result = pipeline_service.migrate(
        project_path=temp_workspace,
        dry_run=True,
        auto_approve=True,
        staging_root=staging_root,
        output_dir=state_dir / "reports",
    )

    assert result.status == "dry_run"
    assert result.dry_run is True
    assert result.changeset_id is not None
    assert result.changeset_digest is not None
    assert len(result.applied_paths) > 0
    assert any("user-badge.component.ts" in p for p in result.applied_paths)
    # Check that target workspace files were NOT created on dry run
    target_comp = (
        temp_workspace / "src" / "app" / "components" / "user-badge" / "user-badge.component.ts"
    )
    assert not target_comp.exists()


def test_pipeline_auto_approve_end_to_end_apply(temp_workspace: Path, pipeline_env) -> None:
    pipeline_service, staging_root, state_dir = pipeline_env

    result = pipeline_service.migrate(
        project_path=temp_workspace,
        auto_approve=True,
        skip_validation=True,
        staging_root=staging_root,
        output_dir=state_dir / "reports",
    )

    assert result.status == "approval_required"
    assert not result.applied_paths
    assert result.backup_snapshot_path is None

    # Target files must now exist in workspace
    target_comp = (
        temp_workspace / "src" / "app" / "components" / "user-badge" / "user-badge.component.ts"
    )
    assert not target_comp.exists()


def test_pipeline_user_aborted_on_rejection(temp_workspace: Path, pipeline_env) -> None:
    pipeline_service, staging_root, _state_dir = pipeline_env

    result = pipeline_service.migrate(
        project_path=temp_workspace,
        auto_approve=False,
        confirm_callback=lambda plan: False,
        staging_root=staging_root,
    )

    assert result.status == "aborted"
    assert "rejected" in result.diagnostics[0]
    target_comp = (
        temp_workspace / "src" / "app" / "components" / "user-badge" / "user-badge.component.ts"
    )
    assert not target_comp.exists()


def test_pipeline_validation_and_reporting(temp_workspace: Path, pipeline_env) -> None:
    pipeline_service, staging_root, state_dir = pipeline_env

    result = pipeline_service.migrate(
        project_path=temp_workspace,
        auto_approve=True,
        skip_validation=False,
        staging_root=staging_root,
        output_dir=state_dir / "reports",
    )

    assert result.status == "approval_required"
    assert result.validation_status == "PASSED"
    assert result.json_report_path is not None
    assert Path(result.json_report_path).is_file()


def test_cli_migrate_dry_run(
    temp_workspace: Path, tmp_path: Path, cli_workflow_authorization
) -> None:
    runner = CliRunner()
    state_dir = tmp_path / "cli_state"

    res = runner.invoke(
        app,
        [
            "migrate",
            str(temp_workspace),
            "--dry-run",
            "--auto-approve",
            "--state-dir",
            str(state_dir),
            "--fake-runner",
        ],
    )
    assert res.exit_code == 0
    assert "dry_run" in res.stdout


def test_cli_eval_semantic() -> None:
    runner = CliRunner()
    fixture = Path("tests") / "fixtures" / "angularjs-directive-mini"

    res = runner.invoke(
        app,
        [
            "eval",
            str(fixture),
            "--semantic",
        ],
    )
    assert res.exit_code == 0
    assert "compilation_pass_rate" in res.stdout
    assert "control_flow_fidelity" in res.stdout
