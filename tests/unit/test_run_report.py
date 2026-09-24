"""Tests for ReportService and MigrationRunReport persistence."""

from pathlib import Path

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.application.validation import ReportService
from migration_agent.domain import (
    ChangeSet,
    FileChange,
    FileMode,
    FileOperation,
    RepairAttempt,
    RunStatus,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
    compute_changeset_digest,
    compute_file_sha256,
)


def _make_dummy_changeset() -> ChangeSet:
    content = b"export class UserCardComponent {}"
    change = FileChange(
        path="src/app/components/user-card/user-card.component.ts",
        operation=FileOperation.CREATE,
        file_mode=FileMode.STANDARD,
        content_digest=compute_file_sha256(content),
        content_bytes=content,
    )
    cs = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-test-01",
        step_id="step-001",
        base_revision="rev-0",
        worktree_fingerprint="fp-0",
        changes=(change,),
    )
    return cs.model_copy(update={"changeset_digest": compute_changeset_digest(cs)})


def test_report_service_compile_and_markdown(tmp_path: Path) -> None:
    service = ReportService()
    cs = _make_dummy_changeset()

    val_res = ValidationResult(
        command="npm test",
        profile=ValidationProfile.TEST,
        status=ValidationStatus.PASSED,
        exit_code=0,
        duration_ms=120,
        output_digest="digest-1234567890abcdef",
    )

    report = service.compile_report(
        run_id="run-report-01",
        plan_id="plan-report-01",
        source_root="/mock/source",
        staging_root="/mock/staging",
        validation_results=[val_res],
        applied_changeset=cs,
    )

    assert report.status == RunStatus.SUCCESS
    assert report.applied_changeset_id == cs.changeset_id
    assert report.applied_changeset_digest == cs.changeset_digest

    md = service.to_markdown(report)
    assert "# Migration Run Report — run-report-01" in md
    assert "- **Status:** `SUCCESS`" in md
    assert "| `npm test` | `TEST` | `PASSED` | 120 | 0 |" in md


def test_report_service_aborted_status() -> None:
    service = ReportService()
    attempt = RepairAttempt(
        attempt_index=1,
        cited_diagnostic="Rogue file",
        previous_changeset_digest="prev",
        new_changeset_digest="new",
        status=ValidationStatus.DISALLOWED,
        summary="Scope expansion detected",
    )
    report = service.compile_report(
        run_id="run-abort-01",
        plan_id="plan-01",
        source_root="/mock/source",
        repair_attempts=[attempt],
    )
    assert report.status == RunStatus.ABORTED


def test_report_service_save_and_sqlite_persistence(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(state_dir=tmp_path / "state")
    service = ReportService(checkpoint_store=store, audit_logger=store)

    val_res = ValidationResult(
        command="npm run lint",
        profile=ValidationProfile.LINT,
        status=ValidationStatus.PASSED,
        exit_code=0,
    )

    report = service.compile_report(
        run_id="run-save-01",
        plan_id="plan-save-01",
        source_root="/mock/source",
        validation_results=[val_res],
    )

    out_dir = tmp_path / "reports"
    json_path, md_path = service.save_report(report, output_dir=out_dir)

    assert json_path.is_file()
    assert md_path.is_file()

    # Verify SQLite persistence
    persisted = store.get_run_report("run-save-01")
    assert persisted is not None
    assert persisted.run_id == "run-save-01"
    assert persisted.status == RunStatus.SUCCESS
    assert len(persisted.validation_results) == 1
    assert persisted.validation_results[0].command == "npm run lint"

    # Verify non-existent returns None
    assert store.get_run_report("unknown-run") is None
