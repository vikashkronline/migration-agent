"""Unit tests for Repair Diagnostician subagent and Invariant 26 scope enforcement."""

from pathlib import Path

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.command_runner import FakeCommandRunner
from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.specialists import (
    DeterministicRepairDiagnosticianAggregator,
)
from migration_agent.application.validation import BoundedRepairService
from migration_agent.domain import (
    ChangeSet,
    FileChange,
    FileMode,
    FileOperation,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    RepairDiagnosis,
    StepRisk,
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
    compute_file_sha256,
)


def test_repair_diagnostician_aggregator_in_scope() -> None:
    diagnosis = RepairDiagnosis(
        root_cause_category="SYNTAX_ERROR",
        actionable=True,
        confidence=0.92,
        suggested_file="src/app/user-card.component.ts",
        diagnostic_details="Missing closing bracket.",
        suggested_fix_summary="Add closing bracket to component template.",
    )
    allowed_scope = ("src/app/user-card.component.ts", "src/app/user-card.component.html")

    is_actionable, target_file, details = (
        DeterministicRepairDiagnosticianAggregator.aggregate_diagnosis(diagnosis, allowed_scope)
    )
    assert is_actionable is True
    assert target_file == "src/app/user-card.component.ts"
    assert "Add closing bracket" in details


def test_repair_diagnostician_aggregator_rejects_out_of_scope() -> None:
    diagnosis = RepairDiagnosis(
        root_cause_category="DEPENDENCY_MISSING",
        actionable=True,
        confidence=0.85,
        suggested_file="package.json",  # OUT OF SCOPE!
        diagnostic_details="Missing rxjs dependency.",
        suggested_fix_summary="Add rxjs to dependencies.",
    )
    allowed_scope = ("src/app/user-card.component.ts",)

    is_actionable, target_file, details = (
        DeterministicRepairDiagnosticianAggregator.aggregate_diagnosis(diagnosis, allowed_scope)
    )
    # Must deterministically reject out-of-scope suggested file per Invariant 26
    assert is_actionable is False
    assert target_file is None
    assert "rejected" in details.lower()
    assert "outside approved scope" in details.lower()


def test_bounded_repair_service_with_diagnostician(tmp_path: Path) -> None:
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir(parents=True)
    state_dir = tmp_path / "state"

    checkpoint_store = SqliteCheckpointStore(state_dir)
    workspace = LocalWorkspaceAdapter()
    runtime = FakeAgentRuntime()

    # Create command runner that fails on attempt 1 and passes on attempt 2
    class SequentialRunner(FakeCommandRunner):
        def __init__(self) -> None:
            super().__init__(default_status=ValidationStatus.PASSED, diagnostics=())
            self.call_count = 0

        def run_command(self, command: ValidationCommand, working_dir: Path) -> ValidationResult:
            self.call_count += 1
            if self.call_count == 1:
                return ValidationResult(
                    command=command.rendered_command,
                    profile=command.profile,
                    status=ValidationStatus.FAILED,
                    exit_code=1,
                    diagnostics=("Assertion failed in user-card.component.ts",),
                )
            return super().run_command(command, working_dir)

    runner = SequentialRunner()

    repair_service = BoundedRepairService(
        command_runner=runner,
        workspace_adapter=workspace,
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
        specialist_runtime=runtime,
        max_budget=3,
    )

    test_file_path = "src/app/user-card.component.ts"
    file_bytes = b"export class UserCardComponent {}\n"
    initial_cs = ChangeSet(
        changeset_id="cs-initial",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="base123",
        worktree_fingerprint="worktree123",
        changes=(
            FileChange(
                path=test_file_path,
                operation=FileOperation.CREATE,
                file_mode=FileMode.STANDARD,
                content_bytes=file_bytes,
                content_digest=compute_file_sha256(file_bytes),
            ),
        ),
    )

    # Materialize file in staging workspace
    workspace.apply_changeset(staging_dir, initial_cs)

    plan = MigrationPlan(
        plan_id="plan-001",
        source_root=str(tmp_path),
        run_id="run-repair-test",
        status=PlanStatus.APPROVED,
        steps=[
            MigrationStep(
                step_id="step-001",
                title="Migrate user card",
                description="Extract and translate.",
                dependencies=[],
                scope="component",
                risk=StepRisk.LOW,
                expected_files=[test_file_path],
            )
        ],
        policy_digest="policy-digest",
    )

    cmd = ValidationCommand(
        executable="npm",
        args=("test",),
        profile=ValidationProfile.TEST,
    )

    success, _final_cs, _attempts, _results = repair_service.run_repair_loop(
        staging_dir=staging_dir,
        initial_changeset=initial_cs,
        plan=plan,
        step_id="step-001",
        commands=[cmd],
    )

    # Diagnostician was called and recorded, repair succeeded
    assert success is True
    assert len(runtime.recorded_diagnosis_requests) >= 1
    assert runtime.recorded_diagnosis_requests[0].allowed_scope == (test_file_path,)
