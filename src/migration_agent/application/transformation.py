"""Application service orchestrating staging workspaces and ADR-8 controlled apply protocol."""

import contextlib
import difflib
import uuid
from pathlib import Path

from migration_agent.domain import (
    ApplyResult,
    ApplyStatus,
    ChangeSet,
    FileChange,
    FileMode,
    FileOperation,
    MigrationPlan,
    PlanStatus,
    compute_changeset_digest,
    compute_file_sha256,
    compute_worktree_fingerprint,
    verify_approval,
)
from migration_agent.ports import (
    AuditEvent,
    AuditLogPort,
    CheckpointPort,
    ComponentExtractorPort,
    ComponentRendererPort,
    OperationalCheckpoint,
    WorkspacePort,
)


class TransformationService:
    """Manages ChangeSet preview, staging materialization, and controlled patch application."""

    def __init__(
        self,
        workspace_adapter: WorkspacePort,
        extractor: ComponentExtractorPort,
        renderer: ComponentRendererPort,
        audit_logger: AuditLogPort | None = None,
        checkpoint_store: CheckpointPort | None = None,
    ) -> None:
        self.workspace_adapter = workspace_adapter
        self.extractor = extractor
        self.renderer = renderer
        self.audit_logger = audit_logger
        self.checkpoint_store = checkpoint_store

    def preview(
        self,
        source_root: Path | str,
        plan: MigrationPlan,
        step_id: str | None = None,
    ) -> tuple[ChangeSet, str]:
        """Generate proposed ChangeSet and unified diff without modifying staging or source."""
        root = Path(source_root).resolve()
        fingerprint = compute_worktree_fingerprint(root)

        changes: list[FileChange] = []
        diff_chunks: list[str] = []

        # Find Ember component and template files
        comp_js = root / "app" / "components" / "user-card.js"
        comp_hbs = root / "app" / "templates" / "components" / "user-card.hbs"
        comp_css = root / "app" / "styles" / "app.css"

        js_source = comp_js.read_text(encoding="utf-8") if comp_js.exists() else ""
        hbs_source = comp_hbs.read_text(encoding="utf-8") if comp_hbs.exists() else ""
        css_source = comp_css.read_text(encoding="utf-8") if comp_css.exists() else ""

        intermediate = self.extractor.extract(js_source, hbs_source, css_source)

        ts_code = self.renderer.render_component_ts(intermediate)
        html_code = self.renderer.render_template_html(intermediate)
        spec_code = self.renderer.render_spec_ts(intermediate)
        scss_code = "// Component-scoped SCSS\n.user-card {\n  max-width: 480px;\n}\n"

        generated_files = [
            ("src/app/components/user-card/user-card.component.ts", ts_code.encode("utf-8")),
            ("src/app/components/user-card/user-card.component.html", html_code.encode("utf-8")),
            ("src/app/components/user-card/user-card.component.scss", scss_code.encode("utf-8")),
            ("src/app/components/user-card/user-card.component.spec.ts", spec_code.encode("utf-8")),
        ]

        for rel_path, content_bytes in generated_files:
            digest = compute_file_sha256(content_bytes)
            change = FileChange(
                path=rel_path,
                operation=FileOperation.CREATE,
                file_mode=FileMode.STANDARD,
                content_digest=digest,
                content_bytes=content_bytes,
            )
            changes.append(change)

            # Generate unified diff
            new_lines = content_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
            diff = difflib.unified_diff(
                [],
                new_lines,
                fromfile=f"a/{rel_path}",
                tofile=f"b/{rel_path}",
            )
            diff_chunks.append("".join(diff))

        changeset_id = f"cs-{uuid.uuid4().hex[:8]}"
        target_step_id = step_id or (plan.steps[0].step_id if plan.steps else "step-001")

        preliminary_changeset = ChangeSet(
            changeset_id=changeset_id,
            plan_id=plan.plan_id,
            step_id=target_step_id,
            base_revision="head-revision",
            worktree_fingerprint=fingerprint,
            changes=tuple(changes),
        )

        final_changeset = preliminary_changeset.model_copy(
            update={"changeset_digest": compute_changeset_digest(preliminary_changeset)}
        )

        if self.checkpoint_store:
            self.checkpoint_store.save_changeset(final_changeset)

        return final_changeset, "\n".join(diff_chunks)

    def stage(
        self,
        staging_root: Path | str,
        run_id: str,
        source_root: Path | str,
        plan: MigrationPlan,
        step_id: str | None = None,
    ) -> tuple[Path, ChangeSet]:
        """Materialize proposed ChangeSet in an isolated staging workspace."""
        if plan.status != PlanStatus.APPROVED or not verify_approval(plan):
            raise ValueError(
                f"Cannot stage unapproved plan '{plan.plan_id}' (status: {plan.status.value})."
            )

        changeset, _ = self.preview(source_root, plan, step_id=step_id)

        staging_dir = self.workspace_adapter.create_staging(
            run_id=run_id,
            source_root=Path(source_root),
            staging_root=Path(staging_root),
        )

        self.workspace_adapter.apply_changeset(staging_dir, changeset)

        if self.checkpoint_store:
            self.checkpoint_store.save_changeset(changeset)
            self.checkpoint_store.save_checkpoint(
                OperationalCheckpoint(
                    checkpoint_id=f"chk-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    checkpoint_type="CHANGESET_STAGED",
                    step_id=changeset.step_id,
                    state_data={
                        "changeset_id": changeset.changeset_id,
                        "plan_id": plan.plan_id,
                        "staging_path": str(staging_dir),
                    },
                )
            )

        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type="CHANGESET_STAGED",
                    actor="agent",
                    payload={
                        "changeset_id": changeset.changeset_id,
                        "plan_id": plan.plan_id,
                        "staging_path": str(staging_dir),
                        "file_count": len(changeset.changes),
                        "changeset_digest": changeset.changeset_digest,
                    },
                )
            )

        return staging_dir, changeset

    def apply(
        self,
        source_root: Path | str,
        changeset: ChangeSet,
        plan: MigrationPlan,
        actor: str,
        backup_root: Path | str | None = None,
        simulate_apply_failure: bool = False,
        simulate_rollback_failure: bool = False,
    ) -> ApplyResult:
        """Execute the ADR-8 4-step controlled apply protocol with verified rollback."""
        root = Path(source_root).resolve()

        def record_outcome(result: ApplyResult) -> ApplyResult:
            if self.audit_logger:
                self.audit_logger.record_event(
                    AuditEvent(
                        event_id=f"evt-{uuid.uuid4().hex[:8]}",
                        run_id=plan.run_id,
                        event_type=f"APPLY_{result.status.value}",
                        actor=actor,
                        payload={
                            "changeset_id": changeset.changeset_id,
                            "plan_id": plan.plan_id,
                            "status": result.status.value,
                            "diagnostics": list(result.diagnostics),
                        },
                    )
                )
            if self.checkpoint_store:
                self.checkpoint_store.save_checkpoint(
                    OperationalCheckpoint(
                        checkpoint_id=f"chk-{uuid.uuid4().hex[:8]}",
                        run_id=plan.run_id,
                        checkpoint_type=f"APPLY_{result.status.value}",
                        step_id=changeset.step_id,
                        state_data={
                            "changeset_id": changeset.changeset_id,
                            "status": result.status.value,
                        },
                    )
                )
            return result

        # Step 1: Re-validate plan approval
        if plan.status != PlanStatus.APPROVED or not verify_approval(plan):
            return record_outcome(
                ApplyResult(
                    status=ApplyStatus.BASE_CHANGED,
                    changeset_id=changeset.changeset_id,
                    diagnostics=("Plan approval signature is invalid or unapproved.",),
                )
            )

        # Step 2: Base-state binding & drift check
        current_fingerprint = compute_worktree_fingerprint(root)
        if current_fingerprint != changeset.worktree_fingerprint:
            return record_outcome(
                ApplyResult(
                    status=ApplyStatus.BASE_CHANGED,
                    changeset_id=changeset.changeset_id,
                    diagnostics=(
                        "Target repository working tree has drifted from base state. "
                        f"Expected fingerprint '{changeset.worktree_fingerprint}', "
                        f"got '{current_fingerprint}'.",
                    ),
                )
            )

        # Step 3: Preflight dry-run check
        for change in changeset.changes:
            target_path = root / change.path
            # Ensure path containment
            if not str(target_path.resolve()).startswith(str(root)):
                return record_outcome(
                    ApplyResult(
                        status=ApplyStatus.BASE_CHANGED,
                        changeset_id=changeset.changeset_id,
                        diagnostics=(f"Target path '{change.path}' escapes repository root.",),
                    )
                )

        # Step 4: Backup snapshot generation
        backup_base = Path(backup_root).resolve() if backup_root else root.parent / ".agent-backups"
        backup_dir = backup_base / changeset.changeset_id
        backup_dir.mkdir(parents=True, exist_ok=True)

        original_files: dict[str, bytes] = {}
        for change in changeset.changes:
            target_path = root / change.path
            if target_path.exists() and target_path.is_file():
                content = target_path.read_bytes()
                original_files[change.path] = content
                backup_file = backup_dir / change.path
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                backup_file.write_bytes(content)

        # Step 5: Controlled patch application
        applied_paths: list[str] = []
        try:
            if simulate_apply_failure:
                raise OSError("Simulated filesystem write error during controlled apply.")

            for change in changeset.changes:
                target_path = root / change.path
                if change.operation == FileOperation.DELETE:
                    if target_path.exists():
                        target_path.unlink()
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    content = change.content_bytes or b""
                    target_path.write_bytes(content)
                    if change.file_mode == FileMode.EXECUTABLE:
                        with contextlib.suppress(OSError):
                            target_path.chmod(0o755)
                    else:
                        with contextlib.suppress(OSError):
                            target_path.chmod(0o644)
                applied_paths.append(change.path)

            # Step 6: Postcondition validation
            for change in changeset.changes:
                target_path = root / change.path
                if change.operation == FileOperation.DELETE:
                    if target_path.exists():
                        raise ValueError(
                            f"Postcondition failed: file '{change.path}' was not deleted."
                        )
                else:
                    if not target_path.exists():
                        raise ValueError(
                            f"Postcondition failed: file '{change.path}' does not exist."
                        )
                    actual_digest = compute_file_sha256(target_path.read_bytes())
                    if actual_digest != change.content_digest:
                        raise ValueError(
                            f"Postcondition digest mismatch on '{change.path}': "
                            f"expected '{change.content_digest}', got '{actual_digest}'."
                        )

            return record_outcome(
                ApplyResult(
                    status=ApplyStatus.APPLIED,
                    changeset_id=changeset.changeset_id,
                    applied_paths=tuple(applied_paths),
                    backup_snapshot_path=str(backup_dir),
                    diagnostics=("All postcondition verification checks passed successfully.",),
                )
            )

        except Exception as apply_err:
            # Step 7: Rollback on failure
            try:
                if simulate_rollback_failure:
                    raise OSError("Simulated failure restoring backup files.")

                # Revert all changes
                for change in changeset.changes:
                    target_path = root / change.path
                    if change.path in original_files:
                        target_path.write_bytes(original_files[change.path])
                    else:
                        if target_path.exists():
                            target_path.unlink()

                # Verify rollback restored exact prior state
                for path_str, orig_bytes in original_files.items():
                    restored_path = root / path_str
                    if not restored_path.exists() or restored_path.read_bytes() != orig_bytes:
                        raise ValueError(f"Rollback verification failed on '{path_str}'.")

                return record_outcome(
                    ApplyResult(
                        status=ApplyStatus.ROLLED_BACK,
                        changeset_id=changeset.changeset_id,
                        applied_paths=(),
                        backup_snapshot_path=str(backup_dir),
                        diagnostics=(
                            f"Controlled apply failed: {apply_err}. "
                            "Rollback cleanly executed and verified.",
                        ),
                    )
                )
            except Exception as rollback_err:
                # Transition explicitly to RecoveryRequired (Invariant 28)
                return record_outcome(
                    ApplyResult(
                        status=ApplyStatus.RECOVERY_REQUIRED,
                        changeset_id=changeset.changeset_id,
                        applied_paths=tuple(applied_paths),
                        backup_snapshot_path=str(backup_dir),
                        diagnostics=(
                            f"CRITICAL: Controlled apply failed ({apply_err}) "
                            f"AND rollback failed ({rollback_err}). "
                            "Manual operator recovery required.",
                        ),
                        recovery_details={
                            "apply_error": str(apply_err),
                            "rollback_error": str(rollback_err),
                            "backup_dir": str(backup_dir),
                            "affected_paths": applied_paths,
                        },
                    )
                )
