"""Unit tests for SpecialistCoordinator and audit logging under budget constraints."""

from pathlib import Path

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.application.specialists import SpecialistCoordinator
from migration_agent.domain import (
    BudgetLimit,
    BudgetTracker,
    ChangeSet,
    ExclusionSummary,
    InventoryInterpretationRequest,
    MigrationPlan,
    PlanCriticRequest,
    PlanStatus,
    ProjectInventory,
    RepairDiagnosticianRequest,
    RepositoryDescriptor,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
)


def create_test_inventory() -> ProjectInventory:
    return ProjectInventory(
        repository=RepositoryDescriptor(
            name="test-repo",
            root=Path("test-repo"),
        ),
        frameworks=(),
        dependencies=(),
        package_boundaries=(),
        files=(),
        exclusions=ExclusionSummary(),
        issues=(),
    )


def test_specialist_coordinator_interpret_inventory(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    runtime = FakeAgentRuntime()
    coordinator = SpecialistCoordinator(runtime=runtime, audit_logger=store)

    inv = create_test_inventory()
    req = InventoryInterpretationRequest(inventory=inv)
    interpretation = coordinator.interpret_inventory(req, run_id="run-test")

    assert interpretation is not None
    assert "test-repo" in interpretation.architectural_summary
    assert len(runtime.recorded_interpretation_requests) == 1

    # Check budget tracker
    summary = coordinator.budget_tracker.get_summary()
    assert summary.total_turns == 1
    assert summary.total_tokens > 0

    # Verify audit events
    events = store.get_events("run-test")
    event_types = [e.event_type for e in events]
    assert "SPECIALIST_INVOKED" in event_types
    assert "SPECIALIST_COMPLETED" in event_types


def test_specialist_coordinator_criticize_plan(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    runtime = FakeAgentRuntime()
    coordinator = SpecialistCoordinator(runtime=runtime, audit_logger=store)

    inv = create_test_inventory()
    plan = MigrationPlan(
        plan_id="plan-test",
        source_root="test-repo",
        run_id="run-test",
        status=PlanStatus.DRAFT,
        steps=[],
        policy_digest="digest-test",
    )
    req = PlanCriticRequest(plan=plan, inventory=inv)
    critique = coordinator.criticize_plan(req, run_id="run-test")

    assert critique is not None
    assert critique.approval_recommended is True
    assert critique.overall_score >= 0.90
    assert len(runtime.recorded_critique_requests) == 1


def test_specialist_coordinator_diagnose_repair(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    runtime = FakeAgentRuntime()
    coordinator = SpecialistCoordinator(runtime=runtime, audit_logger=store)

    failing = ValidationResult(
        command="npm test",
        profile=ValidationProfile.TEST,
        exit_code=1,
        status=ValidationStatus.FAILED,
        duration_ms=200,
        output_digest="digest",
        diagnostics=("Assertion failed in user-card.spec.js",),
    )
    changeset = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="base123",
        worktree_fingerprint="worktree123",
        changes=(),
    )
    req = RepairDiagnosticianRequest(
        failing_result=failing,
        current_changeset=changeset,
        allowed_scope=("app/components/user-card.js",),
    )
    diagnosis = coordinator.diagnose_repair(req, run_id="run-test")

    assert diagnosis is not None
    assert diagnosis.actionable is True
    assert diagnosis.suggested_file == "app/components/user-card.js"


def test_specialist_coordinator_fails_closed_when_budget_exceeded(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    runtime = FakeAgentRuntime()
    # Configure a tracker with max_total_turns=1
    tracker = BudgetTracker(BudgetLimit(max_total_turns=1))
    coordinator = SpecialistCoordinator(runtime=runtime, audit_logger=store, budget_tracker=tracker)

    inv = create_test_inventory()
    req = InventoryInterpretationRequest(inventory=inv)

    # First call succeeds and consumes 1 turn
    first_res = coordinator.interpret_inventory(req, run_id="run-test")
    assert first_res is not None
    assert tracker.is_exhausted

    # Second call should fail closed and return None
    second_res = coordinator.interpret_inventory(req, run_id="run-test")
    assert second_res is None

    # Check audit log for budget exceeded event
    events = store.get_events("run-test")
    event_types = [e.event_type for e in events]
    assert "SPECIALIST_BUDGET_EXCEEDED" in event_types
