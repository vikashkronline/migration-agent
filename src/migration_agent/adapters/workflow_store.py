"""Transactional request deduplication, workflow CAS, and monotonic writer leases."""

import os
import sqlite3
import time
from datetime import UTC, datetime, timedelta

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.domain.apply_approval import ApplyApprovalRecord
from migration_agent.domain.browser_validation import BrowserCapture, BrowserReview
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.execution import NativeExecutionConsent
from migration_agent.domain.host_workflow import (
    TERMINAL_OPERATIONS,
    AnalysisProposal,
    Lifecycle,
    Operation,
    OperationStatus,
    ValidationExecution,
    WorkflowRecord,
    WriterLease,
    validate_transition,
)


class SqliteWorkflowStore(SqliteCheckpointStore):
    def _init_db(self) -> None:
        super()._init_db()
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS browser_captures (
                    capture_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    content_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS browser_reviews (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    capture_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    digest TEXT UNIQUE NOT NULL, content_json TEXT NOT NULL);
            """)
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    request_id TEXT NOT NULL, kind TEXT NOT NULL, payload_digest TEXT NOT NULL,
                    status TEXT NOT NULL, content_json TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operation_requests (
                    project_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL, kind TEXT NOT NULL, payload_digest TEXT NOT NULL,
                    PRIMARY KEY(project_id, request_id));
                CREATE TABLE IF NOT EXISTS writer_leases (
                    project_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    generation INTEGER NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS host_workflows (
                    project_id TEXT NOT NULL, plan_id TEXT NOT NULL, step_id TEXT NOT NULL,
                    version INTEGER NOT NULL, content_json TEXT NOT NULL,
                    PRIMARY KEY(project_id, plan_id, step_id));
                CREATE TABLE IF NOT EXISTS host_analyses (
                    project_id TEXT NOT NULL, analysis_id TEXT NOT NULL, content_json TEXT NOT NULL,
                    PRIMARY KEY(project_id, analysis_id));
                CREATE TABLE IF NOT EXISTS destination_heads (
                    project_id TEXT NOT NULL, root TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    PRIMARY KEY(project_id, root));
                CREATE TABLE IF NOT EXISTS apply_approvals (
                    nonce TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    consumed INTEGER NOT NULL DEFAULT 0, content_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS validation_executions (
                    digest TEXT PRIMARY KEY, project_id TEXT NOT NULL, content_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS native_consents (
                    consent_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, plan_id TEXT NOT NULL,
                    step_id TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
                    content_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS native_consent_changesets (
                    consent_id TEXT NOT NULL, changeset_id TEXT NOT NULL,
                    PRIMARY KEY(consent_id, changeset_id));
            """)

    def claim_request(self, operation: Operation) -> tuple[Operation, bool]:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM operation_requests WHERE project_id=? AND request_id=?",
                (operation.project_id, operation.request_id),
            ).fetchone()
            if row:
                if (
                    row["kind"] != operation.kind
                    or row["payload_digest"] != operation.payload_digest
                ):
                    raise ValueError("REQUEST_CONFLICT: request_id already binds different input.")
                saved = conn.execute(
                    "SELECT content_json FROM operations WHERE operation_id=?",
                    (row["operation_id"],),
                ).fetchone()
                if not saved:
                    raise ValueError("OPERATION_EXPIRED: retained request cannot execute again.")
                previous = Operation.model_validate_json(saved[0])
                if (
                    previous.principal_id != operation.principal_id
                    or previous.actor != operation.actor
                    or previous.access_digest != operation.access_digest
                ):
                    raise ValueError(
                        "REQUEST_CONFLICT: replay belongs to another actor or access revision."
                    )
                return previous, False
            conn.execute(
                "INSERT INTO operation_requests VALUES (?,?,?,?,?)",
                (
                    operation.project_id,
                    operation.request_id,
                    operation.operation_id,
                    operation.kind,
                    operation.payload_digest,
                ),
            )
            conn.execute(
                "INSERT INTO operations VALUES (?,?,?,?,?,?,?,?)",
                (
                    operation.operation_id,
                    operation.project_id,
                    operation.request_id,
                    operation.kind,
                    operation.payload_digest,
                    operation.status.value,
                    operation.model_dump_json(),
                    operation.updated_at.isoformat(),
                ),
            )
            return operation, True

    def get_operation(self, project_id: str, operation_id: str) -> Operation:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content_json FROM operations WHERE project_id=? AND operation_id=?",
                (project_id, operation_id),
            ).fetchone()
            if not row:
                raise ValueError("OPERATION_NOT_FOUND: operation unavailable for this project.")
            return Operation.model_validate_json(row[0])

    def save_operation(self, operation: Operation, lease: WriterLease | None = None) -> None:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if lease:
                self._verify(conn, lease)
            row = conn.execute(
                "SELECT content_json FROM operations WHERE operation_id=?",
                (operation.operation_id,),
            ).fetchone()
            if not row:
                raise ValueError("OPERATION_NOT_FOUND: operation unavailable.")
            previous = Operation.model_validate_json(row[0])
            if (
                previous.project_id,
                previous.request_id,
                previous.payload_digest,
                previous.kind,
            ) != (
                operation.project_id,
                operation.request_id,
                operation.payload_digest,
                operation.kind,
            ):
                raise ValueError("OPERATION_MISMATCH: immutable request identity changed.")
            if previous.status in TERMINAL_OPERATIONS:
                raise ValueError("OPERATION_TERMINAL: completed operations cannot be rewritten.")
            if previous.status == OperationStatus.CANCEL_REQUESTED and operation.status not in {
                OperationStatus.CANCELLED,
                OperationStatus.RECOVERY_REQUIRED,
            }:
                raise ValueError("CANCEL_REQUESTED: stop at a safe boundary.")
            conn.execute(
                "UPDATE operations SET status=?,content_json=?,updated_at=? WHERE operation_id=?",
                (
                    operation.status.value,
                    operation.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                    operation.operation_id,
                ),
            )

    def cancel_operation(self, project_id: str, operation_id: str) -> Operation:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT content_json FROM operations WHERE project_id=? AND operation_id=?",
                (project_id, operation_id),
            ).fetchone()
            if not row:
                raise ValueError("OPERATION_NOT_FOUND: operation unavailable.")
            operation = Operation.model_validate_json(row[0])
            if operation.kind == "apply" and operation.status == OperationStatus.RUNNING:
                raise ValueError(
                    "APPLY_CRITICAL_SECTION: cancellation is unavailable during apply."
                )
            if operation.status in TERMINAL_OPERATIONS:
                return operation
            updated = operation.model_copy(
                update={
                    "status": OperationStatus.CANCELLED
                    if operation.status == OperationStatus.QUEUED
                    else OperationStatus.CANCEL_REQUESTED,
                    "message": "Cancellation requested",
                    "updated_at": datetime.now(UTC),
                }
            )
            conn.execute(
                "UPDATE operations SET status=?,content_json=? WHERE operation_id=?",
                (updated.status.value, updated.model_dump_json(), operation_id),
            )
            return updated

    def list_active_operations(self, project_id: str) -> list[Operation]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT content_json FROM operations WHERE project_id=? "
                "AND status IN ('QUEUED','RUNNING','CANCEL_REQUESTED') "
                "ORDER BY operation_id",
                (project_id,),
            )
            return [Operation.model_validate_json(row[0]) for row in rows]

    def purge_operations(self) -> None:
        cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM operations WHERE updated_at<? AND status IN "
                "('SUCCEEDED','FAILED','CANCELLED')",
                (cutoff,),
            )

    @staticmethod
    def _verify(conn: sqlite3.Connection, lease: WriterLease) -> None:
        row = conn.execute(
            "SELECT * FROM writer_leases WHERE project_id=?", (lease.project_id,)
        ).fetchone()
        if (
            not row
            or row["owner"] != lease.owner
            or row["generation"] != lease.generation
            or row["expires_at"] <= time.time()
        ):
            raise ValueError("LEASE_LOST: writer generation or expiry is invalid.")

    def acquire_lease(self, project_id: str, owner: str, ttl: int = 60) -> WriterLease:
        if not 1 <= ttl <= 3600:
            raise ValueError("INVALID_LEASE: lease duration outside limits.")
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM writer_leases WHERE project_id=?", (project_id,)
            ).fetchone()
            if row and row["expires_at"] > time.time():
                raise ValueError("WRITER_BUSY: another project writer owns the lease.")
            lease = WriterLease(
                project_id=project_id,
                owner=owner,
                generation=row["generation"] + 1 if row else 1,
                expires_at=time.time() + ttl,
            )
            conn.execute(
                "INSERT INTO writer_leases VALUES (?,?,?,?) ON CONFLICT(project_id) "
                "DO UPDATE SET owner=excluded.owner,generation=excluded.generation,"
                "expires_at=excluded.expires_at",
                (project_id, owner, lease.generation, lease.expires_at),
            )
            return lease

    def verify_lease(self, lease: WriterLease) -> None:
        with self._get_connection() as conn:
            self._verify(conn, lease)

    def renew_lease(self, lease: WriterLease, ttl: int = 300) -> None:
        if not 1 <= ttl <= 3600:
            raise ValueError("LEASE_TTL_INVALID: lease TTL must be bounded.")
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            conn.execute(
                "UPDATE writer_leases SET expires_at=MAX(expires_at,?) WHERE project_id=?",
                (time.time() + ttl, lease.project_id),
            )

    def release_lease(self, lease: WriterLease) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE writer_leases SET expires_at=0 WHERE project_id=? "
                "AND owner=? AND generation=?",
                (lease.project_id, lease.owner, lease.generation),
            )

    def save_workflow(self, record: WorkflowRecord, lease: WriterLease) -> WorkflowRecord:
        if record.project_id != lease.project_id:
            raise ValueError("PROJECT_MISMATCH: writer cannot update another project.")
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            row = conn.execute(
                "SELECT content_json FROM host_workflows WHERE project_id=? "
                "AND plan_id=? AND step_id=?",
                (record.project_id, record.plan_id, record.step_id),
            ).fetchone()
            if row:
                previous = WorkflowRecord.model_validate_json(row[0])
                if previous.version != record.version:
                    raise ValueError("STALE_CHECKPOINT: workflow was modified by another writer.")
                if previous.destination is not None and previous.destination != record.destination:
                    raise ValueError(
                        "DESTINATION_IMMUTABLE: a changed target snapshot needs a new plan."
                    )
                if (
                    previous.architecture_digest is not None
                    and previous.architecture_digest != record.architecture_digest
                ):
                    raise ValueError("ARCHITECTURE_IMMUTABLE: changed decisions need a new plan.")
                if (
                    previous.source_root,
                    previous.run_id,
                    previous.base_revision,
                    previous.worktree_fingerprint,
                    previous.policy_digest,
                    previous.plan_digest,
                ) != (
                    record.source_root,
                    record.run_id,
                    record.base_revision,
                    record.worktree_fingerprint,
                    record.policy_digest,
                    record.plan_digest,
                ):
                    raise ValueError("BASE_IMMUTABLE: changed base requires a new plan.")
                if record.state != previous.state:
                    validate_transition(previous.state, record.state)
            elif record.state != Lifecycle.PLAN_SAVED or record.version != 0:
                raise ValueError("INVALID_TRANSITION: new workflows start at PLAN_SAVED.")
            if record.state == Lifecycle.BASE_CHANGED:
                record = record.model_copy(
                    update={
                        "changeset_id": None,
                        "changeset_digest": None,
                        "staging_path": None,
                        "staging_fingerprint": None,
                        "validation_results": (),
                        "validation_digest": None,
                        "browser_evidence": None,
                        "approval_nonce": None,
                    }
                )
            saved = record.model_copy(update={"version": record.version + 1})
            if record.state == Lifecycle.APPLY_COMPLETED and record.destination:
                if not record.staging_fingerprint:
                    raise ValueError(
                        "DESTINATION_CHECKPOINT_INVALID: verified publication required."
                    )
                head = conn.execute(
                    "SELECT fingerprint FROM destination_heads WHERE project_id=? AND root=?",
                    (record.project_id, record.destination.root),
                ).fetchone()
                if head and head[0] not in {
                    record.destination.fingerprint,
                    record.staging_fingerprint,
                }:
                    raise ValueError(
                        "DESTINATION_CHANGED: another publication advanced this target."
                    )
                conn.execute(
                    "INSERT INTO destination_heads VALUES (?,?,?) ON CONFLICT(project"
                    "_id,root) DO UPDATE SET fingerprint=excluded.fingerprint",
                    (record.project_id, record.destination.root, record.staging_fingerprint),
                )
            conn.execute(
                "INSERT INTO host_workflows VALUES (?,?,?,?,?) ON CONFLICT"
                "(project_id,plan_id,step_id) DO UPDATE SET version=excluded.version,"
                "content_json=excluded.content_json",
                (
                    record.project_id,
                    record.plan_id,
                    record.step_id,
                    saved.version,
                    saved.model_dump_json(),
                ),
            )
            return saved

    def destination_head(self, project_id: str, root: str) -> str | None:
        with self._get_connection() as connection:
            row = connection.execute(
                "SELECT fingerprint FROM destination_heads WHERE project_id=? AND root=?",
                (project_id, root),
            ).fetchone()
            return str(row[0]) if row else None

    def get_workflow(self, project_id: str, plan_id: str, step_id: str) -> WorkflowRecord:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content_json FROM host_workflows WHERE project_id=? "
                "AND plan_id=? AND step_id=?",
                (project_id, plan_id, step_id),
            ).fetchone()
            if not row:
                raise ValueError("WORKFLOW_NOT_FOUND: step has no operational checkpoint.")
            return WorkflowRecord.model_validate_json(row[0])

    def list_workflows(self, project_id: str) -> list[WorkflowRecord]:
        with self._get_connection() as conn:
            return [
                WorkflowRecord.model_validate_json(row[0])
                for row in conn.execute(
                    "SELECT content_json FROM host_workflows WHERE project_id=? "
                    "ORDER BY plan_id,step_id",
                    (project_id,),
                )
            ]

    def save_analysis(
        self, project_id: str, analysis_id: str, proposal: AnalysisProposal, lease: WriterLease
    ) -> None:
        if project_id != lease.project_id:
            raise ValueError("PROJECT_MISMATCH: analysis owner mismatch.")
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            conn.execute(
                "INSERT INTO host_analyses VALUES (?,?,?)",
                (project_id, analysis_id, proposal.model_dump_json()),
            )

    def get_analysis(self, project_id: str, analysis_id: str) -> AnalysisProposal:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content_json FROM host_analyses WHERE project_id=? AND analysis_id=?",
                (project_id, analysis_id),
            ).fetchone()
            if not row:
                raise ValueError("ANALYSIS_NOT_FOUND: analysis unavailable for this project.")
            return AnalysisProposal.model_validate_json(row[0])

    def save_apply_approval(self, record: ApplyApprovalRecord, lease: WriterLease) -> None:
        if record.project_id != lease.project_id:
            raise ValueError("PROJECT_MISMATCH: approval owner mismatch.")
        from migration_agent.adapters.filesystem import validate_repository_path
        from migration_agent.application.host_proposals import opaque_id

        opaque_id(record.run_id)
        opaque_id(record.step_id)
        opaque_id(record.nonce)
        mirror = validate_repository_path(
            self.state_dir.resolve(),
            f"runs/{record.run_id}/approvals/{record.step_id}-{record.nonce}.json",
        )
        mirror.parent.mkdir(parents=True, exist_ok=True)
        payload = record.model_dump_json(indent=2)
        temporary = mirror.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, mirror)
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            conn.execute(
                "INSERT INTO apply_approvals VALUES (?,?,0,?)",
                (record.nonce, record.project_id, record.model_dump_json()),
            )

    def get_apply_approval(self, nonce: str) -> ApplyApprovalRecord:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content_json FROM apply_approvals WHERE nonce=? AND consumed=0", (nonce,)
            ).fetchone()
            if not row:
                raise ValueError("APPROVAL_REQUIRED: no unconsumed human approval record.")
            return ApplyApprovalRecord.model_validate_json(row[0])

    def consume_apply_approval(self, nonce: str, lease: WriterLease) -> None:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            cursor = conn.execute(
                "UPDATE apply_approvals SET consumed=1 WHERE nonce=? "
                "AND project_id=? AND consumed=0",
                (nonce, lease.project_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("APPROVAL_CONSUMED: approval cannot authorize another attempt.")

    def save_validation_execution(self, execution: ValidationExecution, lease: WriterLease) -> str:
        from migration_agent.domain.canonical import compute_canonical_digest

        if execution.project_id != lease.project_id:
            raise ValueError("PROJECT_MISMATCH: validation execution owner mismatch.")
        digest = compute_canonical_digest(execution.model_dump(mode="json"))
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            conn.execute(
                "INSERT INTO validation_executions VALUES (?,?,?)",
                (digest, execution.project_id, execution.model_dump_json()),
            )
        return digest

    def get_validation_execution(self, digest: str) -> ValidationExecution:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content_json FROM validation_executions WHERE digest=?", (digest,)
            ).fetchone()
            if not row:
                raise ValueError("VALIDATION_REQUIRED: immutable execution provenance is absent.")
            return ValidationExecution.model_validate_json(row[0])

    def save_native_consent(self, record: NativeExecutionConsent, lease: WriterLease) -> None:
        if record.project_id != lease.project_id:
            raise ValueError("PROJECT_MISMATCH: consent owner mismatch.")
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            conn.execute(
                (
                    "UPDATE native_consents SET revoked=1 WHERE project_id=? AND "
                    "plan_id=? AND step_id=?"
                ),
                (record.project_id, record.plan_id, record.step_id),
            )
            conn.execute(
                "INSERT INTO native_consents VALUES (?,?,?,?,0,?)",
                (
                    record.consent_id,
                    record.project_id,
                    record.plan_id,
                    record.step_id,
                    record.model_dump_json(),
                ),
            )
            conn.execute(
                "INSERT INTO native_consent_changesets VALUES (?,?)",
                (record.consent_id, record.initial_changeset_id),
            )

    def get_native_consent(
        self, project_id: str, plan_id: str, step_id: str, consent_id: str | None = None
    ) -> NativeExecutionConsent:
        with self._get_connection() as conn:
            row = conn.execute(
                (
                    "SELECT content_json FROM native_consents WHERE project_id=? AND "
                    "plan_id=? AND step_id=? AND revoked=0"
                )
                + (" AND consent_id=?" if consent_id else ""),
                (project_id, plan_id, step_id, consent_id)
                if consent_id
                else (project_id, plan_id, step_id),
            ).fetchone()
            if not row:
                raise ValueError(
                    "NATIVE_CONSENT_REQUIRED: run agent validation authorize in a human terminal."
                )
            return NativeExecutionConsent.model_validate_json(row[0])

    def use_native_consent(
        self, record: NativeExecutionConsent, changeset_id: str, lease: WriterLease
    ) -> None:
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            active = conn.execute(
                "SELECT revoked FROM native_consents WHERE consent_id=? AND project_id=?",
                (record.consent_id, lease.project_id),
            ).fetchone()
            if not active or active[0]:
                raise ValueError("NATIVE_CONSENT_REQUIRED: consent was revoked.")
            if conn.execute(
                "SELECT 1 FROM native_consent_changesets WHERE consent_id=? AND changeset_id=?",
                (record.consent_id, changeset_id),
            ).fetchone():
                return
            used = conn.execute(
                "SELECT COUNT(*) FROM native_consent_changesets WHERE consent_id=?",
                (record.consent_id,),
            ).fetchone()[0]
            if used > record.repair_budget:
                raise ValueError("NATIVE_REPAIR_BUDGET_EXCEEDED: renewed consent required.")
            conn.execute(
                "INSERT INTO native_consent_changesets VALUES (?,?)",
                (record.consent_id, changeset_id),
            )

    def revoke_native_consent(self, project_id: str, consent_id: str) -> None:
        # Revocation must remain available while a validation worker holds the writer lease.
        with self._get_connection() as conn:
            if (
                conn.execute(
                    "UPDATE native_consents SET revoked=1 WHERE project_id=? AND consent_id=?",
                    (project_id, consent_id),
                ).rowcount
                != 1
            ):
                raise ValueError("CONSENT_NOT_FOUND: select a consent owned by this project.")

    def save_browser_capture(self, capture: BrowserCapture, lease: WriterLease) -> None:
        if capture.project_id != lease.project_id:
            raise ValueError("PROJECT_MISMATCH: browser capture belongs to another project.")
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            conn.execute(
                "INSERT INTO browser_captures VALUES (?,?,?)",
                (capture.capture_id, capture.project_id, capture.model_dump_json()),
            )

    def browser_captures(self, project_id: str) -> tuple[BrowserCapture, ...]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT content_json FROM browser_captures WHERE project_id=? "
                "ORDER BY rowid DESC LIMIT 256",
                (project_id,),
            ).fetchall()
        return tuple(BrowserCapture.model_validate_json(row[0]) for row in rows)

    def get_browser_capture(self, project_id: str, capture_id: str) -> BrowserCapture:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content_json FROM browser_captures WHERE project_id=? AND capture_id=?",
                (project_id, capture_id),
            ).fetchone()
        if row is None:
            raise ValueError("BROWSER_CAPTURE_NOT_FOUND: project-scoped capture is unavailable.")
        return BrowserCapture.model_validate_json(row[0])

    def save_browser_review(
        self, project_id: str, review: BrowserReview, lease: WriterLease
    ) -> None:
        self.get_browser_capture(project_id, review.capture_id)
        if project_id != lease.project_id:
            raise ValueError("PROJECT_MISMATCH: browser review writer belongs to another project.")
        with self._get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._verify(conn, lease)
            conn.execute(
                "INSERT OR IGNORE INTO browser_reviews(capture_id,project_id,digest,content_json) "
                "VALUES (?,?,?,?)",
                (
                    review.capture_id,
                    project_id,
                    compute_canonical_digest(review.model_dump(mode="json")),
                    review.model_dump_json(),
                ),
            )

    def get_browser_review(self, project_id: str, capture_id: str) -> BrowserReview | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content_json FROM browser_reviews "
                "WHERE project_id=? AND capture_id=? ORDER BY sequence DESC LIMIT 1",
                (project_id, capture_id),
            ).fetchone()
        return BrowserReview.model_validate_json(row[0]) if row else None
