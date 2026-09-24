"""Unit tests for SQLite checkpoints store and JSONL audit logging."""

import json
from pathlib import Path

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.domain import (
    ApprovalSignature,
    AssuranceLevel,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    StepRisk,
    compute_plan_digest,
)
from migration_agent.ports import AuditEvent, OperationalCheckpoint


def _make_plan(plan_id: str = "plan-001") -> MigrationPlan:
    step = MigrationStep(
        step_id="step-001",
        title="Test step",
        description="Description",
        dependencies=[],
        scope="component",
        risk=StepRisk.LOW,
        confidence=1.0,
        evidence=[],
        expected_files=["a.ts"],
        validation_strategy=["test"],
        rollback_note="",
        acceptance_criteria=[],
        unresolved_questions=[],
    )
    return MigrationPlan(
        plan_id=plan_id,
        source_root="/repo",
        run_id="run-001",
        status=PlanStatus.DRAFT,
        steps=[step],
        policy_digest="sha256:pol123",
    )


def test_sqlite_checkpoint_store_lifecycle(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    plan = _make_plan("plan-abc")

    # 1. Save plan
    store.save_plan(plan)

    # 2. Get plan
    retrieved = store.get_plan("plan-abc")
    assert retrieved is not None
    assert retrieved.plan_id == "plan-abc"
    assert retrieved.status == PlanStatus.DRAFT
    assert len(retrieved.steps) == 1
    assert retrieved.steps[0].step_id == "step-001"

    # 3. Update plan status
    updated = plan.model_copy(update={"status": PlanStatus.NEEDS_APPROVAL})
    store.save_plan(updated)
    retrieved_updated = store.get_plan("plan-abc")
    assert retrieved_updated is not None
    assert retrieved_updated.status == PlanStatus.NEEDS_APPROVAL

    # 4. List plans
    plans = store.list_plans()
    assert len(plans) == 1
    assert plans[0].plan_id == "plan-abc"

    # 5. Non-existent plan returns None
    assert store.get_plan("plan-ghost") is None


def test_sqlite_approval_and_checkpoints(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    plan = _make_plan("plan-xyz")
    store.save_plan(plan)

    approval = ApprovalSignature(
        actor="alice",
        plan_digest=compute_plan_digest(plan),
        policy_digest="sha256:pol123",
        signature="sig:alice:123",
        assurance_level=AssuranceLevel.MODE_B,
    )
    store.save_approval("plan-xyz", approval)

    # Save checkpoints
    chk1 = OperationalCheckpoint(
        checkpoint_id="chk-1",
        run_id="run-001",
        step_id="step-001",
        checkpoint_type="STEP_START",
        state_data={"progress": 10},
    )
    chk2 = OperationalCheckpoint(
        checkpoint_id="chk-2",
        run_id="run-001",
        step_id="step-001",
        checkpoint_type="STEP_FINISH",
        state_data={"progress": 100},
    )
    store.save_checkpoint(chk1)
    store.save_checkpoint(chk2)

    checkpoints = store.list_checkpoints("run-001")
    assert len(checkpoints) == 2
    assert checkpoints[0].checkpoint_id == "chk-1"
    assert checkpoints[1].checkpoint_id == "chk-2"


def test_audit_event_logging_and_jsonl(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    audit_file = tmp_path / "audit.jsonl"

    event = AuditEvent(
        event_id="evt-100",
        run_id="run-001",
        event_type="PLAN_CREATED",
        actor="agent",
        payload={"plan_id": "plan-100", "steps": 3},
    )
    store.record_event(event)

    # Check that audit.jsonl contains the event
    assert audit_file.exists()
    lines = audit_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_id"] == "evt-100"
    assert record["event_type"] == "PLAN_CREATED"
    assert record["actor"] == "agent"
    assert record["payload"]["steps"] == 3
