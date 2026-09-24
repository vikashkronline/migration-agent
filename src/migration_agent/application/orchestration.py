"""Application service orchestrating resumable execution, state transitions, and recovery."""

import uuid
from pathlib import Path

from migration_agent.application.transformation import TransformationService
from migration_agent.application.validation import (
    BoundedRepairService,
    ReportService,
    ValidationService,
)
from migration_agent.domain import (
    ChangeSet,
    ExecutionStep,
    MigrationPlan,
    MigrationRunReport,
    RepairAttempt,
    RunRecord,
    RunStatus,
    ValidationCommand,
    ValidationStatus,
)
from migration_agent.ports import (
    AuditEvent,
    AuditLogPort,
    CheckpointPort,
)


class ResumableExecutionService:
    """Manages the full lifecycle of a migration run with crash recovery and resumption."""

    def __init__(
        self,
        checkpoint_store: CheckpointPort,
        transformation_service: TransformationService,
        validation_service: ValidationService,
        repair_service: BoundedRepairService,
        report_service: ReportService,
        audit_logger: AuditLogPort | None = None,
    ) -> None:
        self.checkpoint_store = checkpoint_store
        self.transformation_service = transformation_service
        self.validation_service = validation_service
        self.repair_service = repair_service
        self.report_service = report_service
        self.audit_logger = audit_logger

    def start_run(
        self,
        source_root: Path | str,
        plan: MigrationPlan,
        *,
        staging_root: Path | str,
        commands: tuple[ValidationCommand, ...] | list[ValidationCommand],
        auto_repair: bool = False,
        max_repairs: int = 3,
        output_dir: Path | str | None = None,
        actor: str = "operator",
    ) -> tuple[RunRecord, MigrationRunReport]:
        """Initiate a new migration run, persisting state at each milestone."""
        run_id = plan.run_id or f"run-{uuid.uuid4().hex[:8]}"
        src_path = Path(source_root).resolve()

        run_record = RunRecord(
            run_id=run_id,
            plan_id=plan.plan_id,
            source_root=str(src_path),
            status=ExecutionStep.INITIALIZED,
        )
        self.checkpoint_store.save_run_record(run_record)

        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type="RUN_STARTED",
                    actor=actor,
                    payload={"plan_id": plan.plan_id, "source_root": str(src_path)},
                )
            )

        return self._execute_from_state(
            run_record=run_record,
            plan=plan,
            staging_root=staging_root,
            commands=commands,
            auto_repair=auto_repair,
            max_repairs=max_repairs,
            output_dir=output_dir,
            actor=actor,
            skip_staging_if_present=False,
        )

    def resume_run(
        self,
        run_id: str,
        *,
        staging_root: Path | str | None = None,
        commands: tuple[ValidationCommand, ...] | list[ValidationCommand],
        auto_repair: bool = True,
        max_repairs: int = 3,
        output_dir: Path | str | None = None,
        actor: str = "operator",
    ) -> tuple[RunRecord, MigrationRunReport]:
        """Resume an interrupted run from its latest operational checkpoint."""
        run_record = self.checkpoint_store.get_run_record(run_id)
        if run_record is None:
            raise ValueError(f"Run '{run_id}' not found in state store.")

        plan = self.checkpoint_store.get_plan(run_record.plan_id)
        if plan is None:
            raise ValueError(
                f"Plan '{run_record.plan_id}' associated with run '{run_id}' not found."
            )

        if run_record.status == ExecutionStep.COMPLETED:
            existing_report = self.checkpoint_store.get_run_report(run_id)
            if existing_report is not None:
                return run_record, existing_report
            # If report is missing, synthesize completed report
            dummy_report = self.report_service.compile_report(
                run_id=run_id,
                plan_id=plan.plan_id,
                source_root=run_record.source_root,
                staging_root=run_record.staging_root or "",
                validation_results=[],
                repair_attempts=[],
                terminal_status=RunStatus.SUCCESS,
            )
            return run_record, dummy_report

        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type="RUN_RESUMED",
                    actor=actor,
                    payload={"resumed_from": run_record.status.value},
                )
            )

        effective_staging_root = staging_root or (
            Path(run_record.staging_root).parent if run_record.staging_root else Path.cwd()
        )

        return self._execute_from_state(
            run_record=run_record,
            plan=plan,
            staging_root=effective_staging_root,
            commands=commands,
            auto_repair=auto_repair,
            max_repairs=max_repairs,
            output_dir=output_dir,
            actor=actor,
            skip_staging_if_present=True,
        )

    def _execute_from_state(
        self,
        run_record: RunRecord,
        plan: MigrationPlan,
        staging_root: Path | str,
        commands: tuple[ValidationCommand, ...] | list[ValidationCommand],
        auto_repair: bool,
        max_repairs: int,
        output_dir: Path | str | None,
        actor: str,
        skip_staging_if_present: bool,
    ) -> tuple[RunRecord, MigrationRunReport]:
        """Internal state machine executing remaining stages to completion."""
        run_id = run_record.run_id
        src_path = Path(run_record.source_root)
        step_id = plan.steps[0].step_id if plan.steps else "step-001"

        staging_dir: Path
        current_changeset: ChangeSet | None = None

        # Stage 1: Staging workspace
        can_skip_staging = (
            skip_staging_if_present
            and run_record.staging_root is not None
            and Path(run_record.staging_root).is_dir()
            and run_record.status
            in (
                ExecutionStep.STAGED,
                ExecutionStep.VALIDATING,
                ExecutionStep.REPAIRING,
                ExecutionStep.FAILED,
            )
        )

        if can_skip_staging:
            assert run_record.staging_root is not None
            staging_dir = Path(run_record.staging_root)
            if run_record.applied_changeset_id:
                current_changeset = self.checkpoint_store.get_changeset(
                    run_record.applied_changeset_id
                )
        else:
            staging_dir_res, staged_changeset = self.transformation_service.stage(
                staging_root=staging_root,
                run_id=run_id,
                source_root=src_path,
                plan=plan,
            )
            staging_dir = staging_dir_res
            current_changeset = staged_changeset
            run_record = run_record.model_copy(
                update={
                    "status": ExecutionStep.STAGED,
                    "staging_root": str(staging_dir),
                    "current_step_id": step_id,
                    "applied_changeset_id": staged_changeset.changeset_id,
                }
            )
            self.checkpoint_store.save_run_record(run_record)

        # Stage 2: Validation
        self.checkpoint_store.update_run_status(run_id, ExecutionStep.VALIDATING)
        val_results = self.validation_service.validate(staging_dir, commands, run_id=run_id)

        all_passed = all(r.status == ValidationStatus.PASSED for r in val_results)
        repair_attempts: list[RepairAttempt] = []

        # Stage 3: Bounded repair loop if validation failed
        if not all_passed and auto_repair and current_changeset is not None:
            self.checkpoint_store.update_run_status(run_id, ExecutionStep.REPAIRING)

            # Determine remaining repair budget across resumptions
            prior_checkpoints = self.checkpoint_store.list_checkpoints(run_id)
            prior_repair_count = sum(
                1 for c in prior_checkpoints if c.checkpoint_type == "REPAIR_ATTEMPT"
            )
            remaining_budget = max(0, max_repairs - prior_repair_count)

            if remaining_budget > 0:
                success, current_changeset, repair_attempts, val_results = (
                    self.repair_service.run_repair_loop(
                        staging_dir=staging_dir,
                        initial_changeset=current_changeset,
                        plan=plan,
                        step_id=step_id,
                        commands=commands,
                        initial_results=val_results,
                        max_attempts=remaining_budget,
                    )
                )
                all_passed = success

        # Stage 4: Completion & Report
        final_step = ExecutionStep.COMPLETED if all_passed else ExecutionStep.FAILED
        applied_cs_id = current_changeset.changeset_id if all_passed and current_changeset else None

        run_record = run_record.model_copy(
            update={
                "status": final_step,
                "staging_root": str(staging_dir),
                "applied_changeset_id": applied_cs_id or run_record.applied_changeset_id,
            }
        )
        self.checkpoint_store.save_run_record(run_record)

        report = self.report_service.compile_report(
            run_id=run_id,
            plan_id=plan.plan_id,
            source_root=str(src_path),
            staging_root=str(staging_dir),
            validation_results=val_results,
            repair_attempts=repair_attempts,
            applied_changeset=current_changeset if all_passed else None,
        )

        if output_dir is not None:
            self.report_service.save_report(report, output_dir=output_dir)

        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type="RUN_COMPLETED" if all_passed else "RUN_FAILED",
                    actor=actor,
                    payload={
                        "status": report.status.value,
                        "validation_checks": len(report.validation_results),
                        "repair_attempts": len(report.repair_attempts),
                    },
                )
            )

        return run_record, report
