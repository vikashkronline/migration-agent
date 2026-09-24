"""Unit tests for ResumableExecutionService recovery and budget tracking."""

from pathlib import Path
from unittest.mock import MagicMock

from migration_agent.adapters import (
    AngularAdapter,
    AngularStandaloneComponentRenderer,
    EmberClassicComponentExtractor,
    FakeCommandRunner,
    LocalWorkspaceAdapter,
    SqliteCheckpointStore,
)
from migration_agent.application import (
    BoundedRepairService,
    ReportService,
    ResumableExecutionService,
    TransformationService,
    ValidationService,
)
from migration_agent.domain import (
    ApprovalSignature,
    AssuranceLevel,
    ExecutionStep,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    RunRecord,
    RunStatus,
    ValidationProfile,
    ValidationStatus,
    compute_plan_digest,
)
from migration_agent.ports import OperationalCheckpoint


def _build_test_plan(fixture_path: Path, run_id: str = "run-resumable-1") -> MigrationPlan:
    step = MigrationStep(
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
        plan_id="plan-resumable-1",
        source_root=str(fixture_path),
        run_id=run_id,
        steps=[step],
        status=PlanStatus.APPROVED,
        policy_digest="policy-digest-123",
    )
    digest = compute_plan_digest(plan)
    sig = ApprovalSignature(
        actor="reviewer",
        plan_digest=digest,
        policy_digest="policy-digest-123",
        signature=f"APPROVED:{digest}:reviewer",
        assurance_level=AssuranceLevel.MODE_B,
    )
    return plan.model_copy(update={"approval": sig})


def test_resumable_execution_end_to_end_lifecycle(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    staging_root = tmp_path / "staging"
    reports_dir = tmp_path / "reports"

    checkpoint_store = SqliteCheckpointStore(state_dir)
    plan = _build_test_plan(fixture_dir, run_id="run-e2e-1")
    checkpoint_store.save_plan(plan)

    runner = FakeCommandRunner(default_status=ValidationStatus.PASSED, default_exit_code=0)
    trans_service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
    )
    val_service = ValidationService(command_runner=runner, audit_logger=checkpoint_store)
    repair_service = BoundedRepairService(
        command_runner=runner,
        workspace_adapter=LocalWorkspaceAdapter(),
        validation_service=val_service,
        audit_logger=checkpoint_store,
        checkpoint_store=checkpoint_store,
    )
    report_service = ReportService(checkpoint_store=checkpoint_store, audit_logger=checkpoint_store)

    exec_service = ResumableExecutionService(
        checkpoint_store=checkpoint_store,
        transformation_service=trans_service,
        validation_service=val_service,
        repair_service=repair_service,
        report_service=report_service,
        audit_logger=checkpoint_store,
    )

    commands = AngularAdapter().get_validation_commands(ValidationProfile.LINT)

    run_record, report = exec_service.start_run(
        source_root=fixture_dir,
        plan=plan,
        staging_root=staging_root,
        commands=commands,
        output_dir=reports_dir,
    )

    assert run_record.status == ExecutionStep.COMPLETED
    assert report.status == RunStatus.SUCCESS
    assert checkpoint_store.get_run_record(run_record.run_id) is not None


def test_resume_skips_staging_when_already_staged(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    staging_root = tmp_path / "staging"
    reports_dir = tmp_path / "reports"

    checkpoint_store = SqliteCheckpointStore(state_dir)
    plan = _build_test_plan(fixture_dir, run_id="run-staged-skip-1")
    checkpoint_store.save_plan(plan)

    # Mock transformation service to assert stage() is not called during resume
    real_trans_service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
    )
    staging_dir, changeset = real_trans_service.stage(
        staging_root=staging_root,
        run_id=plan.run_id,
        source_root=fixture_dir,
        plan=plan,
    )

    # Persist state simulating a crash right after staging
    run_record = RunRecord(
        run_id=plan.run_id,
        plan_id=plan.plan_id,
        source_root=str(fixture_dir),
        staging_root=str(staging_dir),
        applied_changeset_id=changeset.changeset_id,
        status=ExecutionStep.STAGED,
    )
    checkpoint_store.save_run_record(run_record)

    mock_trans_service = MagicMock(spec=TransformationService)

    runner = FakeCommandRunner(default_status=ValidationStatus.PASSED, default_exit_code=0)
    val_service = ValidationService(command_runner=runner, audit_logger=checkpoint_store)
    repair_service = BoundedRepairService(
        command_runner=runner,
        workspace_adapter=LocalWorkspaceAdapter(),
        validation_service=val_service,
        audit_logger=checkpoint_store,
        checkpoint_store=checkpoint_store,
    )
    report_service = ReportService(checkpoint_store=checkpoint_store, audit_logger=checkpoint_store)

    exec_service = ResumableExecutionService(
        checkpoint_store=checkpoint_store,
        transformation_service=mock_trans_service,
        validation_service=val_service,
        repair_service=repair_service,
        report_service=report_service,
        audit_logger=checkpoint_store,
    )

    commands = AngularAdapter().get_validation_commands(ValidationProfile.LINT)

    resumed_record, report = exec_service.resume_run(
        run_id=plan.run_id,
        commands=commands,
        output_dir=reports_dir,
    )

    # Invariant verified: stage was NOT called again!
    mock_trans_service.stage.assert_not_called()
    assert resumed_record.status == ExecutionStep.COMPLETED
    assert report.status == RunStatus.SUCCESS


def test_resume_retains_and_decrements_repair_budget(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"
    staging_root = tmp_path / "staging"
    reports_dir = tmp_path / "reports"

    checkpoint_store = SqliteCheckpointStore(state_dir)
    plan = _build_test_plan(fixture_dir, run_id="run-repair-budget-1")
    checkpoint_store.save_plan(plan)

    trans_service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
    )
    staging_dir, changeset = trans_service.stage(
        staging_root=staging_root,
        run_id=plan.run_id,
        source_root=fixture_dir,
        plan=plan,
    )

    # Record 1 prior repair attempt checkpoint
    checkpoint_store.save_checkpoint(
        OperationalCheckpoint(
            checkpoint_id="chk-rep-1",
            run_id=plan.run_id,
            checkpoint_type="REPAIR_ATTEMPT",
            step_id="step-user-card",
            state_data={"attempt_index": 1},
        )
    )

    run_record = RunRecord(
        run_id=plan.run_id,
        plan_id=plan.plan_id,
        source_root=str(fixture_dir),
        staging_root=str(staging_dir),
        applied_changeset_id=changeset.changeset_id,
        status=ExecutionStep.REPAIRING,
    )
    checkpoint_store.save_run_record(run_record)

    runner = FakeCommandRunner(
        default_status=ValidationStatus.FAILED,
        default_exit_code=1,
        default_output="Syntax error",
        diagnostics=("Syntax error",),
    )
    val_service = ValidationService(command_runner=runner, audit_logger=checkpoint_store)
    repair_service = BoundedRepairService(
        command_runner=runner,
        workspace_adapter=LocalWorkspaceAdapter(),
        validation_service=val_service,
        audit_logger=checkpoint_store,
        checkpoint_store=checkpoint_store,
        max_budget=2,
    )
    report_service = ReportService(checkpoint_store=checkpoint_store, audit_logger=checkpoint_store)

    exec_service = ResumableExecutionService(
        checkpoint_store=checkpoint_store,
        transformation_service=trans_service,
        validation_service=val_service,
        repair_service=repair_service,
        report_service=report_service,
        audit_logger=checkpoint_store,
    )

    commands = AngularAdapter().get_validation_commands(ValidationProfile.LINT)

    # Resume with max_repairs=2. Since 1 attempt was already recorded, budget remaining is 1.
    resumed_record, report = exec_service.resume_run(
        run_id=plan.run_id,
        commands=commands,
        max_repairs=2,
        auto_repair=True,
        output_dir=reports_dir,
    )

    assert resumed_record.status == ExecutionStep.FAILED
    assert report.status == RunStatus.FAILED
    # Only 1 additional attempt executed
    assert len(report.repair_attempts) == 1


def test_resume_completed_run_returns_existing_report(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    state_dir = tmp_path / "state"

    checkpoint_store = SqliteCheckpointStore(state_dir)
    plan = _build_test_plan(fixture_dir, run_id="run-already-completed")
    checkpoint_store.save_plan(plan)

    run_record = RunRecord(
        run_id=plan.run_id,
        plan_id=plan.plan_id,
        source_root=str(fixture_dir),
        status=ExecutionStep.COMPLETED,
    )
    checkpoint_store.save_run_record(run_record)

    exec_service = ResumableExecutionService(
        checkpoint_store=checkpoint_store,
        transformation_service=MagicMock(),
        validation_service=MagicMock(),
        repair_service=MagicMock(),
        report_service=ReportService(checkpoint_store=checkpoint_store),
    )

    resumed_record, report = exec_service.resume_run(
        run_id=plan.run_id,
        commands=[],
    )

    assert resumed_record.status == ExecutionStep.COMPLETED
    assert report.status == RunStatus.SUCCESS
