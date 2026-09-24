"""Unit tests for audit journal append-only logging, deterministic redaction, and verification."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from migration_agent.adapters import SqliteCheckpointStore
from migration_agent.domain import RedactionPolicy
from migration_agent.ports import AuditEvent


def test_audit_journal_records_redacted_events_to_db_and_jsonl(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    store = SqliteCheckpointStore(
        state_dir=state_dir, redaction_policy=RedactionPolicy(max_payload_bytes=64)
    )

    event = AuditEvent(
        event_id="evt-001",
        run_id="run-100",
        event_type="STEP_EXECUTION",
        actor="operator",
        payload={
            "api_key": "sk-secret1234567890abcdef",
            "message": "Step started with secret token bearer 9876543210abcdef.",
            "oversized_blob": "X" * 150,
        },
    )

    store.record_event(event)

    # 1. Verify SQLite record has redacted payload
    events = store.get_events("run-100")
    assert len(events) == 1
    retrieved = events[0]
    assert retrieved.event_id == "evt-001"
    assert retrieved.payload["api_key"] == "[REDACTED]"
    assert "[REDACTED]" in retrieved.payload["message"]
    assert "sk-" not in retrieved.payload["message"]
    assert isinstance(retrieved.payload["oversized_blob"], dict)
    assert retrieved.payload["oversized_blob"]["digest"].startswith("sha256:")

    # 2. Verify audit.jsonl contains exact redacted line
    jsonl_path = state_dir / "audit.jsonl"
    assert jsonl_path.is_file()
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    parsed_jsonl = json.loads(lines[0])
    assert parsed_jsonl["event_id"] == "evt-001"
    assert parsed_jsonl["payload"]["api_key"] == "[REDACTED]"
    assert parsed_jsonl["payload"]["oversized_blob"]["size_bytes"] == 150


def test_audit_log_chronological_verification(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    store = SqliteCheckpointStore(state_dir=state_dir)

    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(seconds=10)
    t2 = t0 + timedelta(seconds=20)

    store.record_event(
        AuditEvent(event_id="e1", run_id="run-200", event_type="INIT", actor="agent", timestamp=t0)
    )
    store.record_event(
        AuditEvent(event_id="e2", run_id="run-200", event_type="STAGE", actor="agent", timestamp=t1)
    )
    store.record_event(
        AuditEvent(
            event_id="e3", run_id="run-200", event_type="VALIDATE", actor="agent", timestamp=t2
        )
    )

    assert store.verify_audit_log("run-200") is True


def test_audit_log_verification_fails_on_clock_skew_or_tampering(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    store = SqliteCheckpointStore(state_dir=state_dir)

    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    t_tampered = t0 - timedelta(seconds=100)

    store.record_event(
        AuditEvent(event_id="e1", run_id="run-300", event_type="INIT", actor="agent", timestamp=t0)
    )
    # Event inserted with backwards timestamp
    store.record_event(
        AuditEvent(
            event_id="e2",
            run_id="run-300",
            event_type="CORRUPT",
            actor="agent",
            timestamp=t_tampered,
        )
    )

    assert store.verify_audit_log("run-300") is False
