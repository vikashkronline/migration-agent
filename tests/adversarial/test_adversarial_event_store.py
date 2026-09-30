"""Adversarial test suite for Section 15.4: Event Store & Tamper Evidence.

Tests security invariants for:
- Strict Ordering & Monotonicity of Audit Events
- Crash Recovery State Resumption from SQLite Checkpoints
- Split-Brain Rejection (SQLite as single source of truth vs JSONL export)
- Tamper Evidence & Audit Log Verification
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.domain import (
    ExecutionStep,
    RunRecord,
)
from migration_agent.ports.checkpoints import AuditEvent, OperationalCheckpoint


def test_strict_ordering_and_monotonicity(tmp_path: Path) -> None:
    """Audit events must maintain strictly monotonic chronological ordering."""
    state_dir = tmp_path / "state"
    store = SqliteCheckpointStore(state_dir=state_dir)
    run_id = "run-ordered-1"

    now = datetime.now(UTC)
    # Append events with increasing timestamps
    for i in range(5):
        store.record_event(
            AuditEvent(
                event_id=f"ev-{i}",
                run_id=run_id,
                event_type="STEP_PROGRESS",
                actor="agent-system",
                timestamp=now + timedelta(seconds=i),
                payload={"step_index": i},
            )
        )

    # Verification must pass
    assert store.verify_audit_log(run_id) is True

    # Retrieve events and verify ordering
    events = store.get_events(run_id)
    assert len(events) == 5
    for i in range(1, len(events)):
        assert events[i].timestamp >= events[i - 1].timestamp


def test_tampered_audit_event_ordering_fails_verification(tmp_path: Path) -> None:
    """Tampering with audit event timestamps or out-of-order records must fail verification."""
    state_dir = tmp_path / "state"
    store = SqliteCheckpointStore(state_dir=state_dir)
    run_id = "run-tamper-audit"

    t1 = datetime(2026, 9, 30, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 30, 9, 0, 0, tzinfo=UTC)  # Back-dated in time

    store.record_event(
        AuditEvent(
            event_id="ev-1",
            run_id=run_id,
            event_type="INIT",
            actor="admin",
            timestamp=t1,
            payload={},
        )
    )
    store.record_event(
        AuditEvent(
            event_id="ev-2",
            run_id=run_id,
            event_type="CORRUPTED_EVENT",
            actor="attacker",
            timestamp=t2,
            payload={},
        )
    )

    # verify_audit_log must detect inverted timestamps and return False
    assert store.verify_audit_log(run_id) is False


def test_split_brain_rejection_sqlite_is_canonical(tmp_path: Path) -> None:
    """Modifying or deleting external JSONL audit log must not alter canonical SQLite state."""
    state_dir = tmp_path / "state"
    store = SqliteCheckpointStore(state_dir=state_dir)
    run_id = "run-split-brain"

    # Save run record and events
    run = RunRecord(
        run_id=run_id,
        plan_id="plan-1",
        source_root="/repo",
        status=ExecutionStep.INITIALIZED,
        current_step_id="step-1",
    )
    store.save_run_record(run)

    store.record_event(
        AuditEvent(
            event_id="ev-canonical",
            run_id=run_id,
            event_type="RUN_STARTED",
            actor="orchestrator",
            timestamp=datetime.now(UTC),
            payload={"initial": True},
        )
    )

    # Adversary deletes or rewrites audit.jsonl to claim a different state
    audit_jsonl = store.audit_log_path
    assert audit_jsonl.is_file()
    tampered_jsonl_content = json.dumps({"event_id": "fake", "status": "COMPLETED"}) + "\n"
    audit_jsonl.write_text(tampered_jsonl_content, encoding="utf-8")

    # Authoritative SQLite query remains unaffected and returns canonical state
    canonical_run = store.get_run_record(run_id)
    assert canonical_run is not None
    assert canonical_run.status == ExecutionStep.INITIALIZED
    events = store.get_events(run_id)
    assert len(events) == 1
    assert events[0].event_id == "ev-canonical"


def test_crash_recovery_resumption_from_checkpoints(tmp_path: Path) -> None:
    """Simulated in-memory crash cleanly resumes from SQLite operational checkpoints."""
    state_dir = tmp_path / "state"
    store = SqliteCheckpointStore(state_dir=state_dir)
    run_id = "run-resumption-test"

    # Step 1: Record initial operational progress
    store.save_checkpoint(
        OperationalCheckpoint(
            checkpoint_id="chk-1",
            run_id=run_id,
            checkpoint_type="STEP_COMPLETED",
            step_id="step-1",
            state_data={"step_number": 1, "status": "COMPLETED"},
        )
    )
    store.save_checkpoint(
        OperationalCheckpoint(
            checkpoint_id="chk-2",
            run_id=run_id,
            checkpoint_type="STEP_STAGED",
            step_id="step-2",
            state_data={"step_number": 2, "staging_dir": "/tmp/staged_step_2"},
        )
    )

    # Step 2: Simulate process crash by creating a brand-new store instance pointing to same DB
    restarted_store = SqliteCheckpointStore(state_dir=state_dir)
    checkpoints = restarted_store.list_checkpoints(run_id)

    assert len(checkpoints) == 2
    assert checkpoints[0].step_id == "step-1"
    assert checkpoints[1].step_id == "step-2"
    assert checkpoints[1].checkpoint_type == "STEP_STAGED"
    assert checkpoints[1].state_data["staging_dir"] == "/tmp/staged_step_2"
