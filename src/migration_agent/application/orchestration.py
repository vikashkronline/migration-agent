import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.application.analysis import AnalysisService
from migration_agent.application.inventory import InventoryService
from migration_agent.application.planning import PlanningService
from migration_agent.application.transformation import TransformationService
from migration_agent.application.validation import (
    BoundedRepairService,
    ReportService,
    ValidationService,
)
from migration_agent.domain import (
    ApplyStatus,
    AssuranceLevel,
    ChangeSet,
    ExecutionStep,
    MigrationPlan,
    MigrationRunReport,
    PlanStatus,
    RepairAttempt,
    RunRecord,
    RunStatus,
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
    verify_approval,
)
from migration_agent.ports import (
    AuditEvent,
    AuditLogPort,
    CheckpointPort,
    GovernancePort,
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


class MigrationPipelineResult(BaseModel):
    """Structured result of executing the end-to-end migration pipeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str  # "ok", "dry_run", "failed", "aborted"
    run_id: str
    plan_id: str
    step_id: str | None = None
    applied_paths: tuple[str, ...] = Field(default_factory=tuple)
    changeset_id: str | None = None
    changeset_digest: str | None = None
    validation_status: str | None = None
    validation_checks_count: int = 0
    repair_attempts_count: int = 0
    backup_snapshot_path: str | None = None
    dry_run: bool = False
    diagnostics: tuple[str, ...] = Field(default_factory=tuple)
    json_report_path: str | None = None
    md_report_path: str | None = None


class MigrationPipelineService:
    """End-to-end migration orchestrator providing frictionless execution from repo to apply."""

    def __init__(
        self,
        checkpoint_store: CheckpointPort,
        transformation_service: TransformationService,
        validation_service: ValidationService,
        repair_service: BoundedRepairService,
        report_service: ReportService,
        planning_service: PlanningService,
        governance: GovernancePort,
        inventory_service: InventoryService | None = None,
        analysis_service: AnalysisService | None = None,
        audit_logger: AuditLogPort | None = None,
    ) -> None:
        self.checkpoint_store = checkpoint_store
        self.transformation_service = transformation_service
        self.validation_service = validation_service
        self.repair_service = repair_service
        self.report_service = report_service
        self.planning_service = planning_service
        self.governance = governance
        self.inventory_service = inventory_service
        self.analysis_service = analysis_service
        self.audit_logger = audit_logger

    @staticmethod
    def _verify_git_clean(repo_root: Path) -> None:
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                raise RuntimeError(
                    f"Target repository at '{repo_root}' has uncommitted dirty changes "
                    "(Invariant 25). Commit or stash changes before migrating, or pass "
                    "allow_dirty=True."
                )
        except FileNotFoundError:
            pass

    def migrate(
        self,
        project_path: Path | str,
        *,
        step_id: str | None = None,
        plan_id: str | None = None,
        auto_approve: bool = False,
        skip_validation: bool = False,
        dry_run: bool = False,
        allow_dirty: bool = False,
        commands: tuple[ValidationCommand, ...] | list[ValidationCommand] | None = None,
        staging_root: Path | str | None = None,
        backup_root: Path | str | None = None,
        output_dir: Path | str | None = None,
        actor: str = "operator",
        max_repairs: int = 3,
        confirm_callback: Callable[[MigrationPlan], bool] | None = None,
    ) -> MigrationPipelineResult:
        """Execute end-to-end migration pipeline across all phases."""
        resolved_path = Path(project_path).resolve()
        if not resolved_path.is_dir():
            raise ValueError(
                f"Project path '{resolved_path}' does not exist or is not a directory."
            )

        if (resolved_path / ".git").is_dir() and not allow_dirty:
            self._verify_git_clean(resolved_path)

        self.governance.ensure_governance_layout(str(resolved_path))

        # Phase 1: Planning
        if plan_id:
            plan = self.planning_service.get_plan(plan_id, project_root=str(resolved_path))
            if plan is None:
                plan = self.checkpoint_store.get_plan(plan_id)
            if plan is None:
                raise ValueError(f"Migration plan '{plan_id}' not found.")
        else:
            if self.inventory_service is None or self.analysis_service is None:
                raise ValueError(
                    "InventoryService and AnalysisService are required to generate plan."
                )
            inv = self.inventory_service.inventory(resolved_path)
            _, analysis = self.analysis_service.analyze(
                resolved_path, provider="gemini", model="gemini-2.5-pro", dry_run=True
            )
            plan, _ = self.planning_service.create_plan(
                inventory=inv,
                analysis=analysis,
                project_root=str(resolved_path),
            )

        # Phase 2: Approval
        is_approved = plan.status == PlanStatus.APPROVED and verify_approval(plan)
        if not is_approved:
            if auto_approve:
                plan = self.planning_service.approve_plan(
                    plan.plan_id,
                    actor=actor,
                    assurance_level=AssuranceLevel.MODE_B,
                    project_root=str(resolved_path),
                )
            elif confirm_callback is not None:
                approved = confirm_callback(plan)
                if not approved:
                    return MigrationPipelineResult(
                        status="aborted",
                        run_id=plan.run_id,
                        plan_id=plan.plan_id,
                        step_id=step_id,
                        diagnostics=("Migration plan approval rejected by user.",),
                    )
                plan = self.planning_service.approve_plan(
                    plan.plan_id,
                    actor=actor,
                    assurance_level=AssuranceLevel.MODE_B,
                    project_root=str(resolved_path),
                )
            else:
                raise ValueError(
                    f"Migration plan '{plan.plan_id}' requires approval. "
                    "Pass auto_approve=True or approve the plan prior to migration."
                )

        # Phase 3: Dry run preview
        if dry_run:
            changeset, diff_text = self.transformation_service.preview(
                resolved_path, plan, step_id=step_id
            )
            first_few_diff = tuple(diff_text.splitlines()[:20]) if diff_text else ()
            return MigrationPipelineResult(
                status="dry_run",
                run_id=plan.run_id,
                plan_id=plan.plan_id,
                step_id=step_id,
                applied_paths=tuple(c.path for c in changeset.changes),
                changeset_id=changeset.changeset_id,
                changeset_digest=changeset.changeset_digest,
                dry_run=True,
                diagnostics=first_few_diff,
            )

        # Phase 4: Staging workspace materialization
        effective_staging = (
            Path(staging_root) if staging_root else (resolved_path.parent / ".agent_staging")
        )
        staging_dir, current_changeset = self.transformation_service.stage(
            staging_root=effective_staging,
            run_id=plan.run_id,
            source_root=resolved_path,
            plan=plan,
            step_id=step_id,
        )

        # Phase 5: Validation & Bounded Self-Repair
        effective_commands: tuple[ValidationCommand, ...] = ()
        if commands is not None:
            effective_commands = tuple(commands)
        elif not skip_validation:
            reg = self.transformation_service.registry
            if reg is not None:
                target_adapter = reg.get_adapter("angular")
                if target_adapter and target_adapter.capabilities.supports_validation:
                    cmds: list[ValidationCommand] = []
                    for p in (
                        ValidationProfile.LINT,
                        ValidationProfile.TYPECHECK,
                        ValidationProfile.TEST,
                        ValidationProfile.BUILD,
                    ):
                        cmds.extend(target_adapter.get_validation_commands(p))
                    effective_commands = tuple(cmds)

        val_results: list[ValidationResult] = []
        repair_attempts: list[RepairAttempt] = []
        val_status = "SKIPPED"
        all_passed = True

        if not skip_validation and effective_commands:
            self.checkpoint_store.update_run_status(plan.run_id, ExecutionStep.VALIDATING)
            val_results = list(
                self.validation_service.validate(
                    staging_dir, effective_commands, run_id=plan.run_id
                )
            )
            all_passed = all(r.status == ValidationStatus.PASSED for r in val_results)

            if not all_passed and max_repairs > 0:
                self.checkpoint_store.update_run_status(plan.run_id, ExecutionStep.REPAIRING)
                active_step_id = step_id or (plan.steps[0].step_id if plan.steps else "step-001")
                success, current_changeset, repairs, repaired_val = (
                    self.repair_service.run_repair_loop(
                        staging_dir=staging_dir,
                        initial_changeset=current_changeset,
                        plan=plan,
                        step_id=active_step_id,
                        commands=effective_commands,
                        initial_results=val_results,
                        max_attempts=max_repairs,
                    )
                )
                all_passed = success
                repair_attempts = list(repairs)
                val_results = list(repaired_val)

            val_status = "PASSED" if all_passed else "FAILED"

        if not all_passed:
            report = self.report_service.compile_report(
                run_id=plan.run_id,
                plan_id=plan.plan_id,
                source_root=str(resolved_path),
                staging_root=str(staging_dir),
                validation_results=val_results,
                repair_attempts=repair_attempts,
                terminal_status=RunStatus.FAILED,
            )
            json_path = None
            md_path = None
            if output_dir:
                out_p = Path(output_dir)
                out_p.mkdir(parents=True, exist_ok=True)
                self.report_service.save_report(report, output_dir=out_p)
                json_path = str(out_p / f"run_report_{report.run_id}.json")
                md_path = str(out_p / f"run_report_{report.run_id}.md")

            return MigrationPipelineResult(
                status="failed",
                run_id=plan.run_id,
                plan_id=plan.plan_id,
                step_id=step_id,
                changeset_id=current_changeset.changeset_id,
                changeset_digest=current_changeset.changeset_digest,
                validation_status=val_status,
                validation_checks_count=len(val_results),
                repair_attempts_count=len(repair_attempts),
                diagnostics=tuple(
                    diag
                    for r in val_results
                    if r.status != ValidationStatus.PASSED
                    for diag in r.diagnostics
                ),
                json_report_path=json_path,
                md_report_path=md_path,
            )

        # Phase 6: Controlled Apply (ADR-8)
        apply_res = self.transformation_service.apply(
            source_root=resolved_path,
            changeset=current_changeset,
            plan=plan,
            actor=actor,
            backup_root=backup_root,
        )
        if apply_res.status != ApplyStatus.APPLIED:
            return MigrationPipelineResult(
                status="failed",
                run_id=plan.run_id,
                plan_id=plan.plan_id,
                step_id=step_id,
                changeset_id=current_changeset.changeset_id,
                changeset_digest=current_changeset.changeset_digest,
                validation_status=val_status,
                validation_checks_count=len(val_results),
                repair_attempts_count=len(repair_attempts),
                backup_snapshot_path=apply_res.backup_snapshot_path,
                diagnostics=apply_res.diagnostics,
            )

        # Phase 7: Audit & Final Report
        report = self.report_service.compile_report(
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            source_root=str(resolved_path),
            staging_root=str(staging_dir),
            validation_results=val_results,
            repair_attempts=repair_attempts,
            applied_changeset=current_changeset,
            terminal_status=RunStatus.SUCCESS,
        )
        json_path = None
        md_path = None
        if output_dir:
            out_p = Path(output_dir)
            out_p.mkdir(parents=True, exist_ok=True)
            self.report_service.save_report(report, output_dir=out_p)
            json_path = str(out_p / f"run_report_{report.run_id}.json")
            md_path = str(out_p / f"run_report_{report.run_id}.md")

        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    run_id=plan.run_id,
                    event_type="PIPELINE_MIGRATION_COMPLETED",
                    actor=actor,
                    payload={
                        "plan_id": plan.plan_id,
                        "step_id": step_id,
                        "changeset_id": current_changeset.changeset_id,
                        "applied_paths_count": len(apply_res.applied_paths),
                        "validation_status": val_status,
                    },
                )
            )

        return MigrationPipelineResult(
            status="ok",
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            step_id=step_id,
            applied_paths=apply_res.applied_paths,
            changeset_id=current_changeset.changeset_id,
            changeset_digest=current_changeset.changeset_digest,
            validation_status=val_status,
            validation_checks_count=len(val_results),
            repair_attempts_count=len(repair_attempts),
            backup_snapshot_path=apply_res.backup_snapshot_path,
            json_report_path=json_path,
            md_report_path=md_path,
        )
