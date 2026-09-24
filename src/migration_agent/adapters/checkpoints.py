"""SQLite and JSONL storage tiering adapter for operational checkpoints and audit logging."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from migration_agent.domain import (
    ApprovalSignature,
    ChangeSet,
    ExecutionStep,
    MigrationPlan,
    MigrationRunReport,
    RedactionPolicy,
    RunRecord,
    compute_plan_digest,
)
from migration_agent.ports import (
    AuditEvent,
    AuditLogPort,
    CheckpointPort,
    OperationalCheckpoint,
)


class SqliteCheckpointStore(CheckpointPort, AuditLogPort):
    """Canonical SQLite execution state store and append-only JSONL audit event mirror."""

    def __init__(
        self,
        state_dir: Path | str,
        redaction_policy: RedactionPolicy | None = None,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_dir / "checkpoints.db"
        self.audit_log_path = self.state_dir / "audit.jsonl"
        self.redactor = redaction_policy or RedactionPolicy()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    source_root TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    policy_digest TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    policy_digest TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    assurance_level TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(plan_id) REFERENCES plans(plan_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT,
                    checkpoint_type TEXT NOT NULL,
                    state_data_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS changesets (
                    changeset_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    changeset_digest TEXT NOT NULL,
                    content_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_reports (
                    run_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    source_root TEXT NOT NULL,
                    staging_root TEXT,
                    status TEXT NOT NULL,
                    current_step_id TEXT,
                    applied_changeset_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def save_plan(self, plan: MigrationPlan) -> None:
        """Persist or update a migration plan in the operational SQLite database."""
        plan_digest = compute_plan_digest(plan)
        content_json = plan.model_dump_json()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO plans (
                    plan_id, source_root, run_id, status, plan_digest,
                    policy_digest, content_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    status = excluded.status,
                    plan_digest = excluded.plan_digest,
                    policy_digest = excluded.policy_digest,
                    content_json = excluded.content_json,
                    updated_at = excluded.updated_at
                """,
                (
                    plan.plan_id,
                    plan.source_root,
                    plan.run_id,
                    plan.status.value,
                    plan_digest,
                    plan.policy_digest,
                    content_json,
                    plan.created_at.isoformat(),
                    plan.updated_at.isoformat(),
                ),
            )

    def get_plan(self, plan_id: str) -> MigrationPlan | None:
        """Retrieve a migration plan by its unique ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT content_json FROM plans WHERE plan_id = ?",
                (plan_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return MigrationPlan.model_validate_json(row["content_json"])

    def list_plans(self) -> list[MigrationPlan]:
        """List all migration plans in descending order of creation."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT content_json FROM plans ORDER BY created_at DESC")
            return [MigrationPlan.model_validate_json(row["content_json"]) for row in cursor]

    def save_approval(self, plan_id: str, approval: ApprovalSignature) -> None:
        """Record an approval signature in the approvals table."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO approvals (
                    plan_id, actor, plan_digest, policy_digest,
                    signature, assurance_level, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    approval.actor,
                    approval.plan_digest,
                    approval.policy_digest,
                    approval.signature,
                    approval.assurance_level.value,
                    approval.timestamp.isoformat(),
                ),
            )

    def save_checkpoint(self, checkpoint: OperationalCheckpoint) -> None:
        """Record an operational checkpoint."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints (
                    checkpoint_id, run_id, step_id, checkpoint_type,
                    state_data_json, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.run_id,
                    checkpoint.step_id,
                    checkpoint.checkpoint_type,
                    json.dumps(checkpoint.state_data, sort_keys=True),
                    checkpoint.timestamp.isoformat(),
                ),
            )

    def list_checkpoints(self, run_id: str) -> list[OperationalCheckpoint]:
        """List all checkpoints associated with a given run ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM checkpoints WHERE run_id = ? ORDER BY timestamp ASC",
                (run_id,),
            )
            checkpoints: list[OperationalCheckpoint] = []
            for row in cursor:
                checkpoints.append(
                    OperationalCheckpoint(
                        checkpoint_id=row["checkpoint_id"],
                        run_id=row["run_id"],
                        step_id=row["step_id"],
                        checkpoint_type=row["checkpoint_type"],
                        state_data=json.loads(row["state_data_json"]),
                        timestamp=row["timestamp"],
                    )
                )
            return checkpoints

    def record_event(self, event: AuditEvent) -> None:
        """Persist audit event to SQLite and append to audit.jsonl with redaction applied."""
        redacted_payload = self.redactor.redact_payload(event.payload)
        payload_json = json.dumps(redacted_payload, sort_keys=True)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO audit_events (
                    event_id, run_id, event_type, actor, timestamp, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.run_id,
                    event.event_type,
                    event.actor,
                    event.timestamp.isoformat(),
                    payload_json,
                ),
            )

        # Mirror append to audit.jsonl
        line = json.dumps(
            {
                "event_id": event.event_id,
                "run_id": event.run_id,
                "event_type": event.event_type,
                "actor": event.actor,
                "timestamp": event.timestamp.isoformat(),
                "payload": redacted_payload,
            },
            sort_keys=True,
        )
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def get_events(self, run_id: str) -> list[AuditEvent]:
        """Retrieve all audit events associated with a run in chronological order."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM audit_events WHERE run_id = ? ORDER BY rowid ASC",
                (run_id,),
            )
            events: list[AuditEvent] = []
            for row in cursor:
                events.append(
                    AuditEvent(
                        event_id=row["event_id"],
                        run_id=row["run_id"],
                        event_type=row["event_type"],
                        actor=row["actor"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        payload=json.loads(row["payload_json"]),
                    )
                )
            return events

    def verify_audit_log(self, run_id: str) -> bool:
        """Verify the integrity and chronological sequence of audit events for a run."""
        events = self.get_events(run_id)
        if not events:
            return True
        return all(events[i].timestamp >= events[i - 1].timestamp for i in range(1, len(events)))

    def save_changeset(self, changeset: ChangeSet) -> None:
        """Persist a ChangeSet in the operational SQLite database."""
        content_json = changeset.model_dump_json()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO changesets (
                    changeset_id, plan_id, step_id, changeset_digest, content_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    changeset.changeset_id,
                    changeset.plan_id,
                    changeset.step_id,
                    changeset.changeset_digest,
                    content_json,
                ),
            )

    def get_changeset(self, changeset_id: str) -> ChangeSet | None:
        """Retrieve a ChangeSet by its unique ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT content_json FROM changesets WHERE changeset_id = ?",
                (changeset_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return ChangeSet.model_validate_json(row["content_json"])

    def save_run_report(self, report: MigrationRunReport) -> None:
        """Persist a migration run report in the operational SQLite database."""
        content_json = report.model_dump_json()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO run_reports (
                    run_id, plan_id, status, content_json, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report.run_id,
                    report.plan_id,
                    report.status.value,
                    content_json,
                    report.timestamp.isoformat(),
                ),
            )

    def get_run_report(self, run_id: str) -> MigrationRunReport | None:
        """Retrieve a migration run report by its unique run ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT content_json FROM run_reports WHERE run_id = ?",
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return MigrationRunReport.model_validate_json(row["content_json"])

    def save_run_record(self, run: RunRecord) -> None:
        """Persist or update a migration run state record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, plan_id, source_root, staging_root, status,
                    current_step_id, applied_changeset_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    plan_id = excluded.plan_id,
                    source_root = excluded.source_root,
                    staging_root = excluded.staging_root,
                    status = excluded.status,
                    current_step_id = excluded.current_step_id,
                    applied_changeset_id = excluded.applied_changeset_id,
                    updated_at = excluded.updated_at
                """,
                (
                    run.run_id,
                    run.plan_id,
                    run.source_root,
                    run.staging_root,
                    run.status.value,
                    run.current_step_id,
                    run.applied_changeset_id,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ),
            )

    def get_run_record(self, run_id: str) -> RunRecord | None:
        """Retrieve a migration run record by its unique run ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return RunRecord(
                run_id=row["run_id"],
                plan_id=row["plan_id"],
                source_root=row["source_root"],
                staging_root=row["staging_root"],
                status=ExecutionStep(row["status"]),
                current_step_id=row["current_step_id"],
                applied_changeset_id=row["applied_changeset_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    def list_run_records(self) -> list[RunRecord]:
        """List all recorded migration runs."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM runs ORDER BY created_at DESC")
            return [
                RunRecord(
                    run_id=row["run_id"],
                    plan_id=row["plan_id"],
                    source_root=row["source_root"],
                    staging_root=row["staging_root"],
                    status=ExecutionStep(row["status"]),
                    current_step_id=row["current_step_id"],
                    applied_changeset_id=row["applied_changeset_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                for row in cursor
            ]

    def update_run_status(
        self,
        run_id: str,
        status: ExecutionStep,
        current_step_id: str | None = None,
        applied_changeset_id: str | None = None,
    ) -> None:
        """Update the operational status and progress of a run."""
        now = datetime.now(UTC).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE runs SET
                    status = ?,
                    current_step_id = coalesce(?, current_step_id),
                    applied_changeset_id = coalesce(?, applied_changeset_id),
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    status.value,
                    current_step_id,
                    applied_changeset_id,
                    now,
                    run_id,
                ),
            )
