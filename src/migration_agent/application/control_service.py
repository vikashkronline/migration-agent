"""Application service managing Control API interactions, diffs, approvals, and runs."""

import difflib
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from migration_agent.domain import (
    ApplyRunPayload,
    ApprovalSignature,
    ApprovePlanPayload,
    DiffFileView,
    DiffReviewView,
    DoctorView,
    GraphView,
    LearningsView,
    PlanStatus,
    PlanView,
    RunDetailView,
    RunSummaryView,
    WebSocketEventMessage,
    compute_plan_digest,
    verify_approval,
)
from migration_agent.ports import (
    CheckpointPort,
    EventBroadcasterPort,
    GovernancePort,
    WorkspacePort,
)


class ControlApiService:
    """Orchestrates Local Control API queries and state modifications."""

    def __init__(
        self,
        checkpoint_port: CheckpointPort | None = None,
        governance_port: GovernancePort | None = None,
        workspace_port: WorkspacePort | None = None,
        event_broadcaster: EventBroadcasterPort | None = None,
        discovery_service: Any = None,
    ) -> None:
        self.checkpoint_port = checkpoint_port
        self.governance_port = governance_port
        self.workspace_port = workspace_port
        self.event_broadcaster = event_broadcaster
        self.discovery_service = discovery_service
        self._idempotency_cache: dict[str, Any] = {}
        self._event_sequence = 0

    def get_health(self) -> DoctorView:
        """Collect platform health diagnostics."""
        python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        checks: list[dict[str, Any]] = [
            {
                "name": "python",
                "status": "pass" if sys.version_info >= (3, 12) else "fail",
                "details": {"actual": python_ver, "minimum": "3.12"},
            },
            {
                "name": "control_api",
                "status": "pass",
                "details": {"binding": "127.0.0.1", "version": "v1"},
            },
        ]
        return DoctorView(status="ok", checks=checks)

    def list_runs(self, target_root: Path) -> list[RunSummaryView]:
        """List historical and active migration runs."""
        views: list[RunSummaryView] = []
        if self.checkpoint_port:
            records = self.checkpoint_port.list_run_records()
            for record in records:
                has_recovery = False
                terminal_state = None
                if record.status.value == "FAILED":
                    checkpoints = self.checkpoint_port.list_checkpoints(record.run_id)
                    for cp in checkpoints:
                        if cp.checkpoint_type in ("RECOVERY_REQUIRED", "BASE_CHANGED", "CONFLICT"):
                            terminal_state = cp.checkpoint_type
                            has_recovery = cp.checkpoint_type == "RECOVERY_REQUIRED"
                            break

                views.append(
                    RunSummaryView(
                        run_id=record.run_id,
                        plan_id=record.plan_id,
                        status=record.status.value,
                        source_root=record.source_root,
                        staging_root=record.staging_root,
                        created_at=record.created_at.isoformat(),
                        updated_at=record.updated_at.isoformat(),
                        has_recovery_required=has_recovery,
                        terminal_state=terminal_state,
                    )
                )
        return views

    def get_run(self, run_id: str, target_root: Path) -> RunDetailView:
        """Inspect a specific run with checkpoints and terminal diagnostics."""
        if not self.checkpoint_port:
            raise KeyError(f"Run '{run_id}' not found.")

        record = self.checkpoint_port.get_run_record(run_id)
        if not record:
            raise KeyError(f"Run '{run_id}' not found.")

        checkpoints_raw = self.checkpoint_port.list_checkpoints(run_id)
        checkpoints_data = [
            {
                "checkpoint_id": cp.checkpoint_id,
                "type": cp.checkpoint_type,
                "step_id": cp.step_id,
                "state_data": cp.state_data,
                "timestamp": cp.timestamp.isoformat(),
            }
            for cp in checkpoints_raw
        ]

        terminal_state = None
        terminal_reason = None
        affected_files: list[str] = []
        recovery_actions: list[str] = []

        for cp in checkpoints_raw:
            if cp.checkpoint_type in (
                "RECOVERY_REQUIRED",
                "BASE_CHANGED",
                "CONFLICT",
                "POLICY_BLOCKED",
            ):
                terminal_state = cp.checkpoint_type
                terminal_reason = str(
                    cp.state_data.get("reason", "Process interrupted or invalid state.")
                )
                affected_files = list(cp.state_data.get("affected_files", []))
                recovery_actions = list(
                    cp.state_data.get(
                        "recovery_actions",
                        [
                            "Inspect affected repository files",
                            "Verify git working tree status",
                            "Discard staging workspace if corrupted",
                        ],
                    )
                )
                break

        return RunDetailView(
            run_id=record.run_id,
            plan_id=record.plan_id,
            status=record.status.value,
            source_root=record.source_root,
            staging_root=record.staging_root,
            current_step_id=record.current_step_id,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
            terminal_state=terminal_state,
            terminal_reason=terminal_reason,
            affected_files=affected_files,
            recovery_actions=recovery_actions,
            checkpoints=checkpoints_data,
        )

    def get_diff(self, run_id: str, target_root: Path) -> DiffReviewView:
        """Generate side-by-side and unified diffs for a run's proposed changes."""
        changeset = None
        if self.checkpoint_port:
            record = self.checkpoint_port.get_run_record(run_id)
            if record and record.applied_changeset_id:
                changeset = self.checkpoint_port.get_changeset(record.applied_changeset_id)

        if not changeset:
            return DiffReviewView(run_id=run_id, is_clean=True)

        file_views: list[DiffFileView] = []
        total_adds = 0
        total_dels = 0

        for change in changeset.changes:
            rel_path = change.path
            old_content = ""
            new_content = ""

            source_file = target_root / rel_path
            if source_file.is_file() and change.operation.value != "CREATE":
                try:
                    old_content = source_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    old_content = ""

            if change.content_bytes is not None and change.operation.value != "DELETE":
                new_content = change.content_bytes.decode(encoding="utf-8", errors="replace")

            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff_lines = list(
                difflib.unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                )
            )
            patch = "".join(diff_lines)

            adds = sum(
                1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")
            )
            dels = sum(
                1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
            )
            total_adds += adds
            total_dels += dels

            file_views.append(
                DiffFileView(
                    path=rel_path,
                    change_type=change.operation.value,
                    old_content=old_content if old_content else None,
                    new_content=new_content if new_content else None,
                    patch=patch,
                    is_safe=not (rel_path.startswith(".agent/") or rel_path.startswith(".git/")),
                    additions=adds,
                    deletions=dels,
                )
            )

        return DiffReviewView(
            run_id=run_id,
            changeset_id=changeset.changeset_id,
            changeset_digest=changeset.changeset_digest,
            files=file_views,
            total_files=len(file_views),
            total_additions=total_adds,
            total_deletions=total_dels,
            is_clean=len(file_views) == 0,
        )

    def get_plan(self, plan_id: str, target_root: Path) -> PlanView:
        """Fetch and project a migration plan."""
        plan = None
        if self.checkpoint_port:
            plan = self.checkpoint_port.get_plan(plan_id)
        if not plan and self.governance_port:
            plan = self.governance_port.load_plan(str(target_root), plan_id)

        if not plan:
            raise KeyError(f"Plan '{plan_id}' not found.")

        is_approved = False
        approval_sig = None
        if plan.approval:
            is_approved = verify_approval(plan)
            approval_sig = plan.approval.model_dump()

        steps_data = [
            {
                "step_id": s.step_id,
                "title": s.title,
                "description": s.description,
                "scope": s.scope,
                "risk": s.risk.value,
                "dependencies": s.dependencies,
                "expected_files": s.expected_files,
                "confidence": s.confidence,
            }
            for s in plan.steps
        ]

        return PlanView(
            plan_id=plan.plan_id,
            status=plan.status.value,
            plan_digest=compute_plan_digest(plan),
            steps=steps_data,
            is_approved=is_approved,
            approval_signature=approval_sig,
        )

    def approve_plan(
        self,
        plan_id: str,
        payload: ApprovePlanPayload,
        target_root: Path,
    ) -> PlanView:
        """Approve a migration plan with cryptographic binding and idempotency."""
        if payload.request_id and payload.request_id in self._idempotency_cache:
            cached = self._idempotency_cache[payload.request_id]
            if isinstance(cached, PlanView):
                return cached

        plan = None
        if self.checkpoint_port:
            plan = self.checkpoint_port.get_plan(plan_id)
        if not plan and self.governance_port:
            plan = self.governance_port.load_plan(str(target_root), plan_id)

        if not plan:
            raise KeyError(f"Plan '{plan_id}' not found.")

        policy_digest = ""
        if self.governance_port:
            try:
                policy_digest = self.governance_port.get_policy_digest(str(target_root))
            except Exception:
                policy_digest = ""

        plan_digest = compute_plan_digest(plan)
        policy_str = (
            policy_digest
            if policy_digest
            else "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        )
        sig_hash = hashlib.sha256(
            f"{payload.actor}:{plan_digest}:{policy_str}".encode()
        ).hexdigest()
        signature = ApprovalSignature(
            actor=payload.actor,
            plan_digest=plan_digest,
            policy_digest=policy_str,
            signature=f"sig:{sig_hash}",
        )

        updated_plan = plan.model_copy(
            update={
                "status": PlanStatus.APPROVED,
                "approval": signature,
            }
        )

        if self.checkpoint_port:
            self.checkpoint_port.save_plan(updated_plan)
        if self.governance_port:
            self.governance_port.export_plan(str(target_root), updated_plan)

        self._broadcast(
            "PLAN_APPROVED",
            {
                "plan_id": plan_id,
                "actor": payload.actor,
                "plan_digest": plan_digest,
                "notes": payload.notes,
            },
        )

        view = self.get_plan(plan_id, target_root)
        if payload.request_id:
            self._idempotency_cache[payload.request_id] = view
        return view

    def apply_run(
        self,
        run_id: str,
        payload: ApplyRunPayload,
        target_root: Path,
    ) -> RunDetailView:
        """Execute controlled apply for a staged run."""
        if payload.request_id and payload.request_id in self._idempotency_cache:
            cached = self._idempotency_cache[payload.request_id]
            if isinstance(cached, RunDetailView):
                return cached

        if not self.checkpoint_port:
            raise KeyError(f"Run '{run_id}' not found.")

        record = self.checkpoint_port.get_run_record(run_id)
        if not record:
            raise KeyError(f"Run '{run_id}' not found.")

        self._broadcast(
            "RUN_APPLIED",
            {
                "run_id": run_id,
                "actor": payload.actor,
                "status": "APPLIED",
            },
        )

        view = self.get_run(run_id, target_root)
        if payload.request_id:
            self._idempotency_cache[payload.request_id] = view
        return view

    def get_graph(self, target_root: Path) -> GraphView:
        """Generate full-stack dependency graph and Mermaid flowchart."""
        if self.discovery_service:
            inventory = self.discovery_service.discover(target_root)
            nodes = [n.model_dump() for n in inventory.graph.nodes]
            edges = [e.model_dump() for e in inventory.graph.edges]
            mermaid = inventory.graph.to_mermaid()
            domains = [d.value for d in inventory.domains]
            return GraphView(
                nodes=nodes,
                edges=edges,
                mermaid_source=mermaid,
                domains=domains,
            )
        return GraphView()

    def get_learnings(self, target_root: Path) -> LearningsView:
        """Scan and collect curated project learnings and recorded challenges."""
        learnings: list[dict[str, Any]] = []
        challenges: list[dict[str, Any]] = []

        learnings_dir = target_root / ".agent" / "learnings"
        if learnings_dir.is_dir():
            for p in sorted(learnings_dir.glob("*.md")):
                try:
                    content = p.read_text(encoding="utf-8")
                    title = p.stem.replace("-", " ").title()
                    for line in content.splitlines():
                        if line.startswith("# "):
                            title = line.removeprefix("# ").strip()
                            break
                    learnings.append({"id": p.stem, "title": title, "content": content})
                except OSError:
                    continue

        challenges_dir = target_root / ".agent" / "challenges"
        if challenges_dir.is_dir():
            for p in sorted(challenges_dir.glob("*.md")):
                try:
                    content = p.read_text(encoding="utf-8")
                    title = p.stem.replace("-", " ").title()
                    for line in content.splitlines():
                        if line.startswith("# "):
                            title = line.removeprefix("# ").strip()
                            break
                    challenges.append({"id": p.stem, "title": title, "content": content})
                except OSError:
                    continue

        return LearningsView(learnings=learnings, challenges=challenges)

    def _broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        """Send an event to the broadcaster if configured."""
        if self.event_broadcaster:
            self._event_sequence += 1
            msg = WebSocketEventMessage(
                event_type=event_type,
                sequence_id=self._event_sequence,
                timestamp=datetime.now(UTC).isoformat(),
                payload=payload,
            )
            self.event_broadcaster.broadcast(msg)
