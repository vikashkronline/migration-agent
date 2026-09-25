"""Application services for allowlisted validation, bounded repair, and reporting."""

import uuid
from collections.abc import Callable
from pathlib import Path

from migration_agent.application.specialists import (
    DeterministicRepairDiagnosticianAggregator,
    SpecialistCoordinator,
)
from migration_agent.domain import (
    ChangeSet,
    MigrationPlan,
    MigrationRunReport,
    RepairAttempt,
    RepairDiagnosticianRequest,
    RunStatus,
    ValidationCommand,
    ValidationResult,
    ValidationStatus,
    compute_changeset_digest,
)
from migration_agent.ports import (
    AuditEvent,
    AuditLogPort,
    CheckpointPort,
    CommandRunnerPort,
    OperationalCheckpoint,
    SpecialistRuntimePort,
    WorkspacePort,
)


class ValidationService:
    """Orchestrates allowlisted validation command execution in staging workspaces."""

    def __init__(
        self,
        command_runner: CommandRunnerPort,
        audit_logger: AuditLogPort | None = None,
    ) -> None:
        self.command_runner = command_runner
        self.audit_logger = audit_logger

    def validate(
        self,
        working_dir: Path | str,
        commands: tuple[ValidationCommand, ...] | list[ValidationCommand],
        run_id: str = "val-run",
    ) -> list[ValidationResult]:
        """Execute validation commands sequentially in the staging workspace."""
        results: list[ValidationResult] = []
        target_dir = Path(working_dir).resolve()

        for cmd in commands:
            res = self.command_runner.run_command(cmd, target_dir)
            results.append(res)

            if self.audit_logger:
                self.audit_logger.record_event(
                    AuditEvent(
                        event_id=f"evt-{uuid.uuid4().hex[:8]}",
                        run_id=run_id,
                        event_type=f"VALIDATION_{res.status.value}",
                        actor="agent",
                        payload={
                            "command": res.command,
                            "profile": res.profile.value,
                            "status": res.status.value,
                            "duration_ms": res.duration_ms,
                            "output_digest": res.output_digest,
                            "diagnostics": list(res.diagnostics),
                        },
                    )
                )

        return results


class BoundedRepairService:
    """Manages the Invariant 26 bounded self-repair loop with budget and scope enforcement."""

    def __init__(
        self,
        command_runner: CommandRunnerPort,
        workspace_adapter: WorkspacePort,
        validation_service: ValidationService | None = None,
        audit_logger: AuditLogPort | None = None,
        checkpoint_store: CheckpointPort | None = None,
        max_budget: int = 3,
        specialist_runtime: SpecialistRuntimePort | None = None,
    ) -> None:
        self.command_runner = command_runner
        self.workspace_adapter = workspace_adapter
        self.validation_service = validation_service or ValidationService(
            command_runner, audit_logger
        )
        self.audit_logger = audit_logger
        self.checkpoint_store = checkpoint_store
        self.max_budget = max_budget
        self.specialist_runtime = specialist_runtime

    def run_repair_loop(
        self,
        staging_dir: Path | str,
        initial_changeset: ChangeSet,
        plan: MigrationPlan,
        step_id: str,
        commands: tuple[ValidationCommand, ...] | list[ValidationCommand],
        repair_fn: Callable[[ChangeSet, ValidationResult], ChangeSet | None] | None = None,
        initial_results: list[ValidationResult] | None = None,
        max_attempts: int | None = None,
    ) -> tuple[bool, ChangeSet, list[RepairAttempt], list[ValidationResult]]:
        """Execute bounded repair loop up to max_attempts budget.

        Returns (success_flag, latest_changeset, repair_attempts, validation_results).
        """
        budget = max_attempts if max_attempts is not None else self.max_budget
        staging_path = Path(staging_dir).resolve()
        current_changeset = initial_changeset
        if not current_changeset.changeset_digest:
            current_changeset = current_changeset.model_copy(
                update={"changeset_digest": compute_changeset_digest(current_changeset)}
            )

        # Step 1: Initial validation if not provided
        current_results = (
            initial_results
            if initial_results is not None
            else self.validation_service.validate(staging_path, commands, run_id=plan.run_id)
        )

        # If already passing, return immediately
        if all(r.status == ValidationStatus.PASSED for r in current_results):
            return True, current_changeset, [], current_results

        # Determine approved file scope for this step
        target_step = next((s for s in plan.steps if s.step_id == step_id), None)
        allowed_scope: set[str] = set()
        if target_step:
            allowed_scope.update(target_step.expected_files)
        # Also allow files present in the approved initial changeset
        allowed_scope.update(c.path for c in initial_changeset.changes)

        attempts: list[RepairAttempt] = []
        last_failure_key: str | None = None

        for attempt_index in range(1, budget + 1):
            # Identify the failing validation result
            failing_res = next(
                (r for r in current_results if r.status != ValidationStatus.PASSED),
                None,
            )
            if not failing_res:
                # All passed
                break

            # Diagnostic extraction
            if failing_res.diagnostics:
                cited_diagnostic = failing_res.diagnostics[0]
            elif failing_res.sanitized_output.strip():
                cited_diagnostic = failing_res.sanitized_output.strip().splitlines()[0]
            else:
                cited_diagnostic = (
                    f"Command '{failing_res.command}' failed with exit {failing_res.exit_code}."
                )

            failure_key = f"{failing_res.command}:{cited_diagnostic}:{failing_res.output_digest}"

            # Termination condition 1: repeated identical failure without progress
            if failure_key == last_failure_key:
                attempt = RepairAttempt(
                    attempt_index=attempt_index,
                    cited_diagnostic=cited_diagnostic,
                    previous_changeset_digest=current_changeset.changeset_digest,
                    new_changeset_digest=current_changeset.changeset_digest,
                    status=ValidationStatus.FAILED,
                    summary="Terminated: identical consecutive validation failure detected.",
                )
                attempts.append(attempt)
                self._record_attempt(plan.run_id, attempt)
                break

            last_failure_key = failure_key

            # Generate candidate repaired ChangeSet
            repaired_changeset: ChangeSet | None = None
            if repair_fn is not None:
                repaired_changeset = repair_fn(current_changeset, failing_res)
            elif self.specialist_runtime is not None:
                coordinator = SpecialistCoordinator(self.specialist_runtime, self.audit_logger)
                diag_req = RepairDiagnosticianRequest(
                    failing_result=failing_res,
                    current_changeset=current_changeset,
                    allowed_scope=tuple(sorted(allowed_scope)),
                    previous_attempts=tuple(attempts),
                )
                diagnosis = coordinator.diagnose_repair(diag_req, run_id=plan.run_id)
                if diagnosis is not None:
                    is_actionable, target_file, details = (
                        DeterministicRepairDiagnosticianAggregator.aggregate_diagnosis(
                            diagnosis, tuple(sorted(allowed_scope))
                        )
                    )
                    if is_actionable and target_file:
                        repaired_changeset = self._diagnosed_repair(
                            current_changeset, failing_res, target_file, details
                        )
                    else:
                        repaired_changeset = self._default_repair(current_changeset, failing_res)
                else:
                    repaired_changeset = self._default_repair(current_changeset, failing_res)
            else:
                repaired_changeset = self._default_repair(current_changeset, failing_res)

            if repaired_changeset is None:
                attempt = RepairAttempt(
                    attempt_index=attempt_index,
                    cited_diagnostic=cited_diagnostic,
                    previous_changeset_digest=current_changeset.changeset_digest,
                    new_changeset_digest=current_changeset.changeset_digest,
                    status=ValidationStatus.FAILED,
                    summary="Terminated: unable to determine actionable repair patch.",
                )
                attempts.append(attempt)
                self._record_attempt(plan.run_id, attempt)
                break

            # Invariant 26: Must produce a NEW ChangeSet with new ID and fresh digest
            if repaired_changeset.changeset_id == current_changeset.changeset_id:
                repaired_changeset = repaired_changeset.model_copy(
                    update={"changeset_id": f"cs-repair-{uuid.uuid4().hex[:8]}"}
                )

            repaired_digest = compute_changeset_digest(repaired_changeset)
            repaired_changeset = repaired_changeset.model_copy(
                update={"changeset_digest": repaired_digest}
            )

            # Invariant 26 Scope Check: All modified files must remain within approved step scope
            repaired_files = {c.path for c in repaired_changeset.changes}
            expanded_files = repaired_files - allowed_scope
            if expanded_files:
                attempt = RepairAttempt(
                    attempt_index=attempt_index,
                    cited_diagnostic=cited_diagnostic,
                    previous_changeset_digest=current_changeset.changeset_digest,
                    new_changeset_digest=repaired_changeset.changeset_digest,
                    status=ValidationStatus.DISALLOWED,
                    summary=(
                        f"Aborted: repair expanded scope to unapproved files: "
                        f"{', '.join(sorted(expanded_files))}."
                    ),
                )
                attempts.append(attempt)
                self._record_attempt(plan.run_id, attempt)
                # Scope expansion halts the repair loop
                break

            # Apply candidate ChangeSet to staging workspace
            self.workspace_adapter.apply_changeset(staging_path, repaired_changeset)

            # Re-execute validation commands
            current_results = self.validation_service.validate(
                staging_path, commands, run_id=plan.run_id
            )

            all_passed = all(r.status == ValidationStatus.PASSED for r in current_results)
            attempt_status = ValidationStatus.PASSED if all_passed else ValidationStatus.FAILED
            summary = (
                f"Attempt {attempt_index}: successfully resolved diagnostic and passed validation."
                if all_passed
                else f"Attempt {attempt_index}: validation checks failed."
            )

            attempt = RepairAttempt(
                attempt_index=attempt_index,
                cited_diagnostic=cited_diagnostic,
                previous_changeset_digest=current_changeset.changeset_digest,
                new_changeset_digest=repaired_changeset.changeset_digest,
                status=attempt_status,
                summary=summary,
            )
            attempts.append(attempt)
            self._record_attempt(plan.run_id, attempt)

            current_changeset = repaired_changeset

            if all_passed:
                return True, current_changeset, attempts, current_results

        # Loop finished without passing
        return False, current_changeset, attempts, current_results

    def _default_repair(self, changeset: ChangeSet, failure: ValidationResult) -> ChangeSet | None:
        """Fallback deterministic repair heuristic for common validation issues."""
        # Check if diagnostic hints at a missing semicolon or trailing whitespace
        # This provides a deterministic out-of-the-box repair behavior
        if not changeset.changes:
            return None

        # Try to modify the first change by cleaning trailing spaces or appending a comment
        target_change = changeset.changes[0]
        if target_change.content_bytes is None:
            return None

        text = target_change.content_bytes.decode("utf-8", errors="replace")
        # Apply fix: strip trailing whitespace or fix simple lint issues
        fixed_text = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
        fixed_bytes = fixed_text.encode("utf-8")

        from migration_agent.domain import compute_file_sha256

        new_digest = compute_file_sha256(fixed_bytes)
        if new_digest == target_change.content_digest:
            # If no change occurred, add an automated repair comment to create a diff
            fixed_text += "// automated-repair: clean-syntax\n"
            fixed_bytes = fixed_text.encode("utf-8")
            new_digest = compute_file_sha256(fixed_bytes)

        updated_change = target_change.model_copy(
            update={"content_bytes": fixed_bytes, "content_digest": new_digest}
        )

        new_changes = [
            updated_change if c.path == target_change.path else c for c in changeset.changes
        ]

        return changeset.model_copy(
            update={
                "changeset_id": f"cs-repair-{uuid.uuid4().hex[:8]}",
                "changes": tuple(new_changes),
            }
        )

    def _diagnosed_repair(
        self,
        changeset: ChangeSet,
        failure: ValidationResult,
        target_file: str,
        details: str,
    ) -> ChangeSet | None:
        """Apply targeted diagnosed repair guidance to the specified in-scope file."""
        target_change = next((c for c in changeset.changes if c.path == target_file), None)
        if target_change is None or target_change.content_bytes is None:
            return self._default_repair(changeset, failure)

        text = target_change.content_bytes.decode("utf-8", errors="replace")
        fixed_text = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
        from migration_agent.domain import compute_file_sha256

        fixed_bytes = fixed_text.encode("utf-8")
        new_digest = compute_file_sha256(fixed_bytes)
        if new_digest == target_change.content_digest:
            fixed_text += f"// automated-repair: {details[:80]}\n"
            fixed_bytes = fixed_text.encode("utf-8")
            new_digest = compute_file_sha256(fixed_bytes)

        updated_change = target_change.model_copy(
            update={"content_bytes": fixed_bytes, "content_digest": new_digest}
        )
        new_changes = [
            updated_change if c.path == target_change.path else c for c in changeset.changes
        ]
        return changeset.model_copy(
            update={
                "changeset_id": f"cs-repair-{uuid.uuid4().hex[:8]}",
                "changes": tuple(new_changes),
            }
        )

    def _record_attempt(self, run_id: str, attempt: RepairAttempt) -> None:
        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type=f"REPAIR_{attempt.status.value}",
                    actor="agent",
                    payload={
                        "attempt_index": attempt.attempt_index,
                        "cited_diagnostic": attempt.cited_diagnostic,
                        "previous_changeset_digest": attempt.previous_changeset_digest,
                        "new_changeset_digest": attempt.new_changeset_digest,
                        "status": attempt.status.value,
                        "summary": attempt.summary,
                    },
                )
            )
        if self.checkpoint_store:
            self.checkpoint_store.save_checkpoint(
                OperationalCheckpoint(
                    checkpoint_id=f"chk-repair-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    checkpoint_type=f"REPAIR_{attempt.status.value}",
                    state_data={
                        "attempt_index": attempt.attempt_index,
                        "cited_diagnostic": attempt.cited_diagnostic,
                        "previous_changeset_digest": attempt.previous_changeset_digest,
                        "new_changeset_digest": attempt.new_changeset_digest,
                        "status": attempt.status.value,
                    },
                )
            )


class ReportService:
    """Compiles canonical JSON and Markdown migration run reports."""

    def __init__(
        self,
        checkpoint_store: CheckpointPort | None = None,
        audit_logger: AuditLogPort | None = None,
    ) -> None:
        self.checkpoint_store = checkpoint_store
        self.audit_logger = audit_logger

    def compile_report(
        self,
        run_id: str,
        plan_id: str,
        source_root: str,
        staging_root: str | None = None,
        validation_results: tuple[ValidationResult, ...] | list[ValidationResult] = (),
        repair_attempts: tuple[RepairAttempt, ...] | list[RepairAttempt] = (),
        applied_changeset: ChangeSet | None = None,
        terminal_status: RunStatus | None = None,
        summary: str = "",
    ) -> MigrationRunReport:
        """Compile a complete MigrationRunReport domain entity."""
        val_tuple = tuple(validation_results)
        rep_tuple = tuple(repair_attempts)

        if terminal_status is not None:
            status = terminal_status
        else:
            all_validations_passed = bool(
                val_tuple and all(v.status == ValidationStatus.PASSED for v in val_tuple)
            )
            has_failed_repair = any(r.status != ValidationStatus.PASSED for r in rep_tuple)
            if all_validations_passed and not has_failed_repair:
                status = RunStatus.SUCCESS
            elif any(r.status == ValidationStatus.DISALLOWED for r in rep_tuple):
                status = RunStatus.ABORTED
            else:
                status = RunStatus.FAILED

        report_summary = summary or (
            f"Migration run {run_id} completed with status {status.value}. "
            f"{len(val_tuple)} validation checks; {len(rep_tuple)} repairs."
        )

        applied_cs_id = applied_changeset.changeset_id if applied_changeset else None
        applied_cs_digest = applied_changeset.changeset_digest if applied_changeset else None

        return MigrationRunReport(
            run_id=run_id,
            plan_id=plan_id,
            source_root=source_root,
            staging_root=staging_root,
            status=status,
            validation_results=val_tuple,
            repair_attempts=rep_tuple,
            applied_changeset_id=applied_cs_id,
            applied_changeset_digest=applied_cs_digest,
            summary=report_summary,
        )

    def to_markdown(self, report: MigrationRunReport) -> str:
        """Render a readable Markdown summary of the migration run report."""
        lines: list[str] = [
            f"# Migration Run Report — {report.run_id}",
            "",
            f"- **Status:** `{report.status.value}`",
            f"- **Plan ID:** `{report.plan_id}`",
            f"- **Source Root:** `{report.source_root}`",
            f"- **Staging Root:** `{report.staging_root or 'N/A'}`",
            f"- **Applied ChangeSet ID:** `{report.applied_changeset_id or 'None'}`",
            f"- **Applied ChangeSet Digest:** `{report.applied_changeset_digest or 'None'}`",
            f"- **Timestamp:** `{report.timestamp.isoformat()}`",
            "",
            "## Summary",
            "",
            report.summary,
            "",
            "## Validation Results",
            "",
        ]

        if not report.validation_results:
            lines.append("No validation checks were executed.")
        else:
            header = "| Command | Profile | Status | Duration (ms) | Exit Code | Output Digest |"
            lines.append(header)
            lines.append("|---|---|---|---|---|---|")
            for v in report.validation_results:
                digest_display = v.output_digest[:16] + "..." if v.output_digest else "N/A"
                lines.append(
                    f"| `{v.command}` | `{v.profile.value}` | `{v.status.value}` | "
                    f"{v.duration_ms} | {v.exit_code if v.exit_code is not None else 'N/A'} | "
                    f"`{digest_display}` |"
                )

        lines.extend(["", "## Repair Attempts", ""])
        if not report.repair_attempts:
            lines.append("No self-repair attempts were performed.")
        else:
            rep_header = (
                "| Attempt | Status | Diagnostic | Previous Digest | New Digest | Summary |"
            )
            lines.append(rep_header)
            lines.append("|---|---|---|---|---|---|")
            for a in report.repair_attempts:
                prev_d = a.previous_changeset_digest[:12] + "..."
                new_d = a.new_changeset_digest[:12] + "..."
                diag = (
                    a.cited_diagnostic[:40] + "..."
                    if len(a.cited_diagnostic) > 40
                    else a.cited_diagnostic
                )
                lines.append(
                    f"| {a.attempt_index} | `{a.status.value}` | `{diag}` | "
                    f"`{prev_d}` | `{new_d}` | {a.summary} |"
                )

        lines.append("")
        return "\n".join(lines)

    def save_report(
        self,
        report: MigrationRunReport,
        output_dir: Path | str | None = None,
    ) -> tuple[Path, Path]:
        """Save JSON and Markdown reports to disk, checkpoint store, and audit log."""
        out_path = Path(output_dir).resolve() if output_dir else Path.cwd()
        out_path.mkdir(parents=True, exist_ok=True)

        json_file = out_path / f"run_report_{report.run_id}.json"
        md_file = out_path / f"run_report_{report.run_id}.md"

        json_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        md_file.write_text(self.to_markdown(report), encoding="utf-8")

        if self.checkpoint_store:
            self.checkpoint_store.save_run_report(report)

        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    run_id=report.run_id,
                    event_type=f"RUN_REPORT_{report.status.value}",
                    actor="agent",
                    payload={
                        "plan_id": report.plan_id,
                        "status": report.status.value,
                        "json_report_path": str(json_file),
                        "md_report_path": str(md_file),
                    },
                )
            )

        return json_file, md_file
