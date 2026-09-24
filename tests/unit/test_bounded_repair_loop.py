"""Tests for ValidationService and BoundedRepairService (Invariant 26)."""

from pathlib import Path
from unittest.mock import MagicMock

from migration_agent.adapters.command_runner import FakeCommandRunner
from migration_agent.application.validation import (
    BoundedRepairService,
    ValidationService,
)
from migration_agent.domain import (
    ChangeSet,
    FileChange,
    FileMode,
    FileOperation,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
    compute_changeset_digest,
    compute_file_sha256,
)


def _make_dummy_plan() -> MigrationPlan:
    step = MigrationStep(
        step_id="step-001",
        title="Convert user-card component",
        description="Convert user-card component",
        expected_files=(
            "src/app/components/user-card/user-card.component.ts",
            "src/app/components/user-card/user-card.component.html",
        ),
        validation_strategy=("npm test",),
    )
    return MigrationPlan(
        plan_id="plan-test-01",
        source_root="/mock/source",
        run_id="run-test-01",
        status=PlanStatus.APPROVED,
        policy_digest="policy-001",
        steps=[step],
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


def test_validation_service_success_and_audit(tmp_path: Path) -> None:
    runner = FakeCommandRunner(default_status=ValidationStatus.PASSED)
    audit_mock = MagicMock()
    service = ValidationService(command_runner=runner, audit_logger=audit_mock)

    cmd = ValidationCommand(executable="npm", args=("test",), profile=ValidationProfile.TEST)
    results = service.validate(tmp_path, [cmd], run_id="run-123")

    assert len(results) == 1
    assert results[0].status == ValidationStatus.PASSED
    assert audit_mock.record_event.called


def test_bounded_repair_loop_already_passing(tmp_path: Path) -> None:
    runner = FakeCommandRunner(default_status=ValidationStatus.PASSED)
    ws_mock = MagicMock()
    repair_service = BoundedRepairService(command_runner=runner, workspace_adapter=ws_mock)

    plan = _make_dummy_plan()
    changeset = _make_dummy_changeset()
    cmd = ValidationCommand(executable="npm", args=("test",), profile=ValidationProfile.TEST)

    success, latest_cs, attempts, _ = repair_service.run_repair_loop(
        staging_dir=tmp_path,
        initial_changeset=changeset,
        plan=plan,
        step_id="step-001",
        commands=[cmd],
    )

    assert success is True
    assert latest_cs.changeset_id == changeset.changeset_id
    assert len(attempts) == 0
    assert not ws_mock.apply_changeset.called


def test_bounded_repair_loop_successful_repair(tmp_path: Path) -> None:
    runner = FakeCommandRunner()
    ws_mock = MagicMock()
    checkpoint_mock = MagicMock()
    audit_mock = MagicMock()

    val_service = ValidationService(command_runner=runner)
    repair_service = BoundedRepairService(
        command_runner=runner,
        workspace_adapter=ws_mock,
        validation_service=val_service,
        audit_logger=audit_mock,
        checkpoint_store=checkpoint_mock,
        max_budget=3,
    )

    plan = _make_dummy_plan()
    changeset = _make_dummy_changeset()
    cmd = ValidationCommand(executable="npm", args=("test",), profile=ValidationProfile.TEST)

    # Initial failed result
    fail_res = ValidationResult(
        command="npm test",
        profile=ValidationProfile.TEST,
        status=ValidationStatus.FAILED,
        exit_code=1,
        sanitized_output="Error: missing semicolon",
        output_digest="digest-fail-1",
        diagnostics=("Error: missing semicolon",),
    )

    # Repair function that fixes the code
    def custom_repair(cs: ChangeSet, fail: ValidationResult) -> ChangeSet:
        new_content = b"export class UserCardComponent {};"
        fixed_change = cs.changes[0].model_copy(
            update={
                "content_bytes": new_content,
                "content_digest": compute_file_sha256(new_content),
            }
        )
        new_cs = cs.model_copy(
            update={
                "changeset_id": "cs-repaired-999",
                "changes": (fixed_change,),
            }
        )
        return new_cs.model_copy(update={"changeset_digest": compute_changeset_digest(new_cs)})

    # Make subsequent validation pass
    runner.default_status = ValidationStatus.PASSED

    success, latest_cs, attempts, _ = repair_service.run_repair_loop(
        staging_dir=tmp_path,
        initial_changeset=changeset,
        plan=plan,
        step_id="step-001",
        commands=[cmd],
        repair_fn=custom_repair,
        initial_results=[fail_res],
    )

    assert success is True
    assert len(attempts) == 1
    assert attempts[0].status == ValidationStatus.PASSED
    assert attempts[0].cited_diagnostic == "Error: missing semicolon"
    assert attempts[0].previous_changeset_digest == changeset.changeset_digest
    assert attempts[0].new_changeset_digest != changeset.changeset_digest
    assert latest_cs.changeset_id != changeset.changeset_id
    assert ws_mock.apply_changeset.called
    assert checkpoint_mock.save_checkpoint.called
    assert audit_mock.record_event.called


def test_bounded_repair_loop_repeated_identical_failure(tmp_path: Path) -> None:
    runner = FakeCommandRunner(
        default_status=ValidationStatus.FAILED,
        default_exit_code=1,
        default_output="Repeated compiler error",
        diagnostics=("Repeated compiler error",),
    )
    ws_mock = MagicMock()
    repair_service = BoundedRepairService(
        command_runner=runner, workspace_adapter=ws_mock, max_budget=3
    )

    plan = _make_dummy_plan()
    changeset = _make_dummy_changeset()
    cmd = ValidationCommand(executable="npm", args=("test",), profile=ValidationProfile.TEST)

    # Initial failed result
    fail_res = ValidationResult(
        command="npm test",
        profile=ValidationProfile.TEST,
        status=ValidationStatus.FAILED,
        exit_code=1,
        sanitized_output="Repeated compiler error",
        output_digest="sha256:fake-output-digest",
        diagnostics=("Repeated compiler error",),
    )

    success, _latest_cs, attempts, _ = repair_service.run_repair_loop(
        staging_dir=tmp_path,
        initial_changeset=changeset,
        plan=plan,
        step_id="step-001",
        commands=[cmd],
        initial_results=[fail_res],
    )

    assert success is False
    # Attempt 1 ran default repair and failed identically to initial result
    # In attempt 2, identical consecutive failure is detected and loop terminates early
    assert len(attempts) <= 2
    assert any("identical consecutive validation failure" in a.summary for a in attempts)


def test_bounded_repair_loop_scope_expansion_detection(tmp_path: Path) -> None:
    runner = FakeCommandRunner(default_status=ValidationStatus.FAILED)
    ws_mock = MagicMock()
    repair_service = BoundedRepairService(
        command_runner=runner, workspace_adapter=ws_mock, max_budget=3
    )

    plan = _make_dummy_plan()
    changeset = _make_dummy_changeset()
    cmd = ValidationCommand(executable="npm", args=("test",), profile=ValidationProfile.TEST)

    fail_res = ValidationResult(
        command="npm test",
        profile=ValidationProfile.TEST,
        status=ValidationStatus.FAILED,
        exit_code=1,
        sanitized_output="Module not found: ../unapproved.ts",
        output_digest="sha256:diag-scope",
        diagnostics=("Module not found: ../unapproved.ts",),
    )

    # Repair function tries to create an unapproved file outside step scope
    def rogue_repair(cs: ChangeSet, fail: ValidationResult) -> ChangeSet:
        rogue_content = b"export const rogue = 1;"
        rogue_change = FileChange(
            path="src/unapproved_file.ts",
            operation=FileOperation.CREATE,
            file_mode=FileMode.STANDARD,
            content_digest=compute_file_sha256(rogue_content),
            content_bytes=rogue_content,
        )
        return cs.model_copy(
            update={
                "changeset_id": "cs-rogue",
                "changes": (cs.changes[0], rogue_change),
            }
        )

    success, _latest_cs, attempts, _ = repair_service.run_repair_loop(
        staging_dir=tmp_path,
        initial_changeset=changeset,
        plan=plan,
        step_id="step-001",
        commands=[cmd],
        repair_fn=rogue_repair,
        initial_results=[fail_res],
    )

    assert success is False
    assert len(attempts) == 1
    assert attempts[0].status == ValidationStatus.DISALLOWED
    assert "expanded scope to unapproved files" in attempts[0].summary
    # Ensure rogue changeset was NOT applied to workspace
    assert not ws_mock.apply_changeset.called
