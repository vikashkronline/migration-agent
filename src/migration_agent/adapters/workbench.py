"""Canonical workflow projection adapter; no repository mutation on inspection."""

import base64
import hashlib
import os
import stat
import threading
from pathlib import Path
from typing import Literal, cast

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.project_work import (
    ProjectWorkRead,
    attach_project_work,
    project_item,
    project_work_digest,
    read_project_work,
    rollup_work,
)
from migration_agent.adapters.validation_backend import safe_path
from migration_agent.adapters.workbench_diff import project_file_diff
from migration_agent.adapters.workflow_runtime import WorkflowRuntime
from migration_agent.adapters.workflow_store import SqliteWorkflowStore
from migration_agent.application.workbench import (
    CommandReceipt,
    ImageContent,
    WorkAction,
    WorkCommand,
    WorkDetail,
    WorkEvents,
    WorkFileDiff,
    WorkImage,
    WorkNode,
    WorkSnapshot,
)
from migration_agent.config import Settings
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import (
    FileOperation,
    compute_changeset_digest,
    compute_file_sha256,
)
from migration_agent.domain.host_workflow import Lifecycle, Operation, WorkflowRecord
from migration_agent.domain.planning import AssuranceLevel, MigrationPlan
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.workflow_access import (
    WorkflowCapability,
    WorkflowContext,
    authorize_workflow,
)
from migration_agent.ports.access import AuthorizationPort
from migration_agent.ports.filesystem import InspectionPolicy


def task_id(plan: str, step: str) -> str:
    return "task-" + hashlib.sha256(f"{plan}\0{step}".encode()).hexdigest()[:32]


class CanonicalWorkbench:
    def __init__(
        self,
        root: Path,
        settings: Settings,
        context: WorkflowContext,
        authorization: AuthorizationPort | None = None,
    ) -> None:
        self.binding = ProjectBinding(root)
        self.settings = settings
        self.context = context
        self.authorization = authorization or ProjectAuthorization(root, settings)
        self.state_dir = self.binding.validate_storage_roots(
            settings.resolve_state_dir(), settings.resolve_staging_root()
        )
        self.store = SqliteWorkflowStore(self.state_dir)
        self.redactor = RedactionPolicy()
        self.runtime: WorkflowRuntime | None = None
        self._runtime_lock = threading.Lock()
        with self.store._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS workbench_journal (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT, scope_root TEXT, entity_id TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS workbench_plan_insert AFTER INSERT ON plans BEGIN
                    INSERT INTO workbench_journal(scope_root,entity_id)
                    VALUES(NEW.source_root,NEW.plan_id); END;
                CREATE TRIGGER IF NOT EXISTS workbench_plan_update AFTER UPDATE ON plans BEGIN
                    INSERT INTO workbench_journal(scope_root,entity_id)
                    VALUES(NEW.source_root,NEW.plan_id); END;
                CREATE TRIGGER IF NOT EXISTS workbench_workflow_insert
                AFTER INSERT ON host_workflows BEGIN
                    INSERT INTO workbench_journal(project_id,entity_id)
                    VALUES(NEW.project_id,NEW.step_id); END;
                CREATE TRIGGER IF NOT EXISTS workbench_workflow_update
                AFTER UPDATE ON host_workflows BEGIN
                    INSERT INTO workbench_journal(project_id,entity_id)
                    VALUES(NEW.project_id,NEW.step_id); END;
                CREATE TRIGGER IF NOT EXISTS workbench_operation_insert
                AFTER INSERT ON operations BEGIN
                    INSERT INTO workbench_journal(project_id,entity_id)
                    VALUES(NEW.project_id,NEW.operation_id); END;
                CREATE TRIGGER IF NOT EXISTS workbench_operation_update
                AFTER UPDATE ON operations BEGIN
                    INSERT INTO workbench_journal(project_id,entity_id)
                    VALUES(NEW.project_id,NEW.operation_id); END;
            """)

    def _read(self) -> tuple[list[MigrationPlan], dict[str, WorkflowRecord], int]:
        self.authorization.require("plan.read")
        self.authorization.require("run.read")
        with self.store._get_connection() as conn:
            conn.execute("BEGIN")
            plans = [
                MigrationPlan.model_validate_json(row[0])
                for row in conn.execute(
                    "SELECT content_json FROM plans WHERE source_root=? ORDER BY plan_id",
                    (str(self.binding.project_root),),
                )
            ]
            records = [
                WorkflowRecord.model_validate_json(row[0])
                for row in conn.execute(
                    "SELECT content_json FROM host_workflows WHERE project_id=? "
                    "ORDER BY plan_id,step_id",
                    (self.binding.project_id,),
                )
            ]
            cursor = int(
                conn.execute(
                    "SELECT COALESCE(MAX(sequence),0) FROM workbench_journal "
                    "WHERE project_id=? OR scope_root=?",
                    (self.binding.project_id, str(self.binding.project_root)),
                ).fetchone()[0]
            )
        for plan in plans:
            self.binding.validate_record_root(plan.source_root)
        for record in records:
            self.binding.validate_record_root(record.source_root)
        return plans, {task_id(r.plan_id, r.step_id): r for r in records}, cursor

    def _snapshot(
        self,
        plans: list[MigrationPlan],
        records: dict[str, WorkflowRecord],
        cursor: int,
        project_work: ProjectWorkRead | None = None,
    ) -> WorkSnapshot:
        access = self.authorization.require("project.read")
        nodes = [
            WorkNode(
                node_id="project",
                label=self.redactor.redact_text(self.binding.project_root.name),
                kind="project",
                status="INITIALIZED" if access.access_digest else "INSPECTION_ONLY",
            ),
            WorkNode(node_id="foundation", label="1. Foundation & readiness", kind="group"),
            WorkNode(node_id="work", label="2. Workflows & tasks", kind="group"),
            WorkNode(node_id="knowledge", label="3. Architecture & knowledge", kind="group"),
        ]
        references = self._references()
        for ident, (relative, _) in references.items():
            nodes.append(
                WorkNode(
                    node_id=ident,
                    parent_id="knowledge",
                    label=relative,
                    kind="reference",
                    status="OBSERVED",
                )
            )
        for plan in plans:
            parent = "plan-" + hashlib.sha256(plan.plan_id.encode()).hexdigest()[:32]
            nodes.append(
                WorkNode(node_id=parent, parent_id="work", label=plan.plan_id, kind="group")
            )
            for step in plan.steps:
                ident = task_id(plan.plan_id, step.step_id)
                record = records.get(ident)
                nodes.append(
                    WorkNode(
                        node_id=ident,
                        parent_id=parent,
                        label=self.redactor.redact_text(step.title)[:200],
                        kind="task",
                        status=record.state.value if record else "PLANNED",
                        run_id=record.run_id if record else plan.run_id,
                        needs_attention=bool(
                            record
                            and record.state
                            in {
                                Lifecycle.VALIDATION_FAILED,
                                Lifecycle.VALIDATION_PASSED,
                                Lifecycle.APPROVAL_PENDING,
                                Lifecycle.BASE_CHANGED,
                                Lifecycle.RECOVERY_REQUIRED,
                            }
                        ),
                        dependencies=tuple(task_id(plan.plan_id, d) for d in step.dependencies),
                    )
                )
        project_work = project_work or read_project_work(self.binding.project_root)
        nodes = rollup_work(attach_project_work(nodes, project_work, task_id))
        revision = compute_canonical_digest(
            {
                "access_digest": self.authorization.require("project.read").access_digest,
                "nodes": [n.model_dump() for n in nodes],
                "cursor": cursor,
                "project_work": project_work_digest(project_work),
                "references": {
                    key: hashlib.sha256(text.encode()).hexdigest()
                    for key, (_, text) in references.items()
                },
            }
        )
        return WorkSnapshot(
            project_id=self.binding.project_id,
            revision=revision,
            cursor=cursor,
            actor=self.context.actor,
            assurance=self.context.assurance.value,
            nodes=tuple(nodes),
            warnings=project_work.warnings,
        )

    def snapshot(self) -> WorkSnapshot:
        self.authorization.require("project.read")
        return self._snapshot(*self._read())

    def detail(self, node_id: str, revision: str) -> WorkDetail:
        self.authorization.require("changeset.read")
        plans, records, cursor = self._read()
        project_work = read_project_work(self.binding.project_root)
        snap = self._snapshot(plans, records, cursor, project_work)
        if snap.revision != revision:
            raise ValueError("SNAPSHOT_STALE")
        node = next((n for n in snap.nodes if n.node_id == node_id), None)
        if node is None:
            raise KeyError("NODE_NOT_FOUND")
        declaration = project_item(project_work, node_id, task_id)
        basic = WorkDetail(
            project_id=snap.project_id,
            revision=revision,
            node=node,
            summary="No verified project-readiness evidence is recorded for this group.",
            owner=declaration.owner if declaration else "",
            acceptance=declaration.acceptance if declaration else (),
            provenance=(
                "Git project-work declaration; verified progress comes only "
                "from linked canonical workflow evidence."
            )
            if declaration
            else "Canonical project/workflow evidence.",
            ask_command=(
                "agent",
                "ask",
                "--path",
                str(self.binding.project_root),
                "--entity",
                node_id,
            ),
        )
        if declaration is not None:
            basic = basic.model_copy(
                update={
                    "summary": declaration.summary
                    or "Declared project work. Inspect linked tasks for workflow evidence."
                }
            )
        if node_id == "project" and project_work.definition and project_work.definition.objective:
            basic = basic.model_copy(update={"summary": project_work.definition.objective})
        if node.kind == "reference":
            authorize_workflow(self.context, WorkflowCapability.EVIDENCE_READ)
            reference = self._references().get(node_id)
            if reference is None or self.snapshot().revision != revision:
                raise ValueError("SNAPSHOT_STALE")
            relative, text = reference
            diagram = (
                text
                if relative.endswith(".mmd")
                else (
                    text.split("```mermaid", 1)[1].split("```", 1)[0]
                    if "```mermaid" in text
                    else ""
                )
            )
            return basic.model_copy(
                update={"summary": text[:32768], "files": (relative,), "diagram": diagram[:16384]}
            )
        if node.kind != "task":
            if declaration is not None or (node_id == "project" and project_work.definition):
                return basic
            summary_text = basic.summary
            if node.node_id == "project":
                summary_text = (
                    "Project opened; no migration plan saved in this store. "
                    "Begin with discovery (agent inventory), analysis (agent analyze), "
                    "and planning (agent plan create)."
                    if not node.task_count
                    else (
                        "Recorded workflow tasks; completion means "
                        "guarded apply postconditions passed."
                    )
                )
            elif node.node_id == "work":
                summary_text = (
                    "Workflows & tasks: no migration plans or task workflows recorded yet. "
                    "Generate a migration plan with 'agent plan create' to populate "
                    "actionable tasks."
                    if not node.task_count
                    else (
                        "Recorded workflow tasks; completion means "
                        "guarded apply postconditions passed."
                    )
                )
            elif node.node_id == "foundation":
                summary_text = (
                    "No verified project-readiness evidence is recorded for this group. "
                    "Foundation & readiness: baseline platform readiness. "
                    "No custom preparatory tasks or prerequisites are declared in this group. "
                    "Inspect Platform Health in the header for system prerequisites, "
                    "or declare custom foundation tasks in .agent/project-work.json."
                    if not node.task_count
                    else (
                        "Recorded foundation tasks; completion means "
                        "preparatory infrastructure prerequisites passed."
                    )
                )
            elif node.node_id == "knowledge":
                summary_text = (
                    "Observed references only; existence does not prove acceptance "
                    "or implementation. Up to 100 eligible bounded references are shown."
                )
            return basic.model_copy(update={"summary": summary_text})
        scope = next(
            ((p, s) for p in plans for s in p.steps if task_id(p.plan_id, s.step_id) == node_id),
            None,
        )
        if scope is None:
            if declaration is None:
                raise KeyError("NODE_NOT_FOUND")
            return basic.model_copy(
                update={
                    "summary": basic.summary
                    + (
                        "\nNo linked canonical workflow evidence is available; "
                        "declared status is not verified completion."
                    )
                }
            )
        plan, step = scope
        authorize_workflow(self.context, WorkflowCapability.EVIDENCE_READ)
        authorize_workflow(self.context, WorkflowCapability.OPERATION_READ)
        activity = self._activity(plan.plan_id, step.step_id)
        if self.snapshot().revision != revision:
            raise ValueError("SNAPSHOT_STALE")
        record = records.get(node_id)
        if record is None:
            needs_implementation = step.scope == "implementation"
            return basic.model_copy(
                update={
                    "summary": self.redactor.redact_text(step.description)[:4096]
                    + (
                        "\nUse migration_implementation_context and "
                        "migration_submit_implementation "
                        "in your connected host, or the CLI implementation-context and "
                        "submit-implementation commands. The declared target files must be "
                        "generated and submitted before staging."
                        if needs_implementation
                        else ""
                    ),
                    "actions": (
                        WorkAction(
                            kind="stage",
                            label="Stage proposal",
                            reason="Submit a grounded implementation through CLI/MCP first."
                            if needs_implementation
                            else "Core checks plan, dependencies and source state.",
                            available=WorkflowCapability.STAGE in self.context.capabilities
                            and self.context.assurance != AssuranceLevel.MODE_C
                            and not needs_implementation,
                        ),
                    ),
                    "milestones": (("Plan", "RECORDED"), ("Artifact", "NOT_STAGED")),
                    "activity": activity,
                }
            )
        command: tuple[str, ...] = (
            "agent",
            "approve",
            record.step_id,
            "--project-root",
            str(self.binding.project_root),
            "--plan",
            record.plan_id,
            "--state-dir",
            str(self.state_dir),
            "--staging-root",
            str(self.settings.resolve_staging_root()),
        )
        if self.settings.trust_root is not None:
            command += ("--trust-root", str(self.settings.trust_root))
        files: tuple[str, ...] = ()
        diff = ""
        if record.changeset_id:
            changeset = self.store.get_changeset(record.changeset_id)
            if (
                changeset
                and changeset.changeset_digest == record.changeset_digest
                and changeset.plan_id == record.plan_id
                and changeset.step_id == record.step_id
            ):
                files = tuple(
                    c.path
                    for c in changeset.changes
                    if not self.redactor.is_sensitive_path(Path(c.path))
                )
                diff = self.redactor.redact_text(
                    "\n".join(
                        f"{c.operation.value} {c.path}\n"
                        + (c.content_bytes or b"").decode("utf-8", errors="replace")
                        for c in changeset.changes
                        if c.path in files
                    )
                )[:32768]
        unapplied_deps: list[str] = []
        for dep in step.dependencies:
            try:
                dep_rec = self.store.get_workflow(self.binding.project_id, plan.plan_id, dep)
                if dep_rec.state != Lifecycle.APPLY_COMPLETED:
                    unapplied_deps.append(dep)
            except (ValueError, KeyError):
                unapplied_deps.append(dep)

        missing_generation = (
            step.scope == "implementation"
            and record.state == Lifecycle.PLAN_SAVED
            and record.changeset_id is None
        )
        stage_dependencies = bool(self.settings.final_target_root and unapplied_deps)
        actions = tuple(
            WorkAction(
                kind=cast(Literal["stage", "validate", "apply"], kind),
                label=label,
                available=cap in self.context.capabilities
                and self._permitted(str(cap))
                and record.state in states
                and self.context.assurance != AssuranceLevel.MODE_C
                and not (kind == "validate" and unapplied_deps)
                and not (kind == "stage" and (missing_generation or stage_dependencies)),
                reason=(
                    "Launcher capability or assurance does not permit this action."
                    if cap not in self.context.capabilities
                    or self.context.assurance == AssuranceLevel.MODE_C
                    else self._permission_reason(str(cap))
                    if not self._permitted(str(cap))
                    else f"Blocked: prerequisite '{unapplied_deps[0]}' must be applied first."
                    if (kind == "validate" or (kind == "stage" and stage_dependencies))
                    and unapplied_deps
                    and record.state in states
                    else "Generate and submit the declared target files using "
                    "implementation-context/submit-implementation in CLI or the connected MCP host."
                    if kind == "stage" and missing_generation
                    else "Unavailable in " + record.state.value + ". Inspect checks and activity."
                    if record.state not in states
                    else "Core rechecks policy, artifact, consent and source state."
                ),
            )
            for kind, label, cap, states in (
                (
                    "stage",
                    "Stage proposal",
                    WorkflowCapability.STAGE,
                    {Lifecycle.PLAN_SAVED, Lifecycle.REPAIRING},
                ),
                (
                    "validate",
                    "Run required validation",
                    WorkflowCapability.VALIDATE,
                    {Lifecycle.STAGE_VERIFIED, Lifecycle.VALIDATION_FAILED},
                ),
                (
                    "apply",
                    "Apply approved exact artifact",
                    WorkflowCapability.APPLY,
                    {Lifecycle.APPROVAL_RECORDED},
                ),
            )
        )
        evidence = tuple((v.profile.value, v.status.value) for v in record.validation_results)
        if not evidence and record.state == Lifecycle.VALIDATION_FAILED:
            evidence = (
                (
                    "Execution gate / Policy",
                    record.recovery_note or "Validation blocked or failed by execution policy",
                ),
            )
        if record.browser_evidence:
            evidence += (
                ("Browser evidence", record.browser_evidence.status),
                ("Optional E2E", record.browser_evidence.e2e_status),
            )
        images = (
            tuple(
                WorkImage(
                    index=i,
                    label=self.redactor.redact_text(img.case_key + " / " + img.origin),
                    digest=img.sha256,
                )
                for i, img in enumerate(record.browser_evidence.capture.images)
            )
            if record.browser_evidence
            else ()
        )
        return WorkDetail(
            project_id=snap.project_id,
            revision=revision,
            node=node,
            summary=self.redactor.redact_text(step.description + "\n" + record.recovery_note)[
                :4096
            ],
            run_id=record.run_id,
            changeset_id=record.changeset_id,
            changeset_digest=record.changeset_digest,
            base_revision=record.base_revision,
            policy_digest=record.policy_digest,
            validation_digest=record.validation_digest,
            destination=record.destination,
            evidence=evidence,
            files=files,
            diff=diff,
            review_command=command,
            actions=actions,
            activity=activity,
            images=images,
            owner=basic.owner,
            acceptance=basic.acceptance,
            provenance=basic.provenance,
            ask_command=(
                *basic.ask_command,
                "--artifact",
                record.changeset_id or "",
                "--run-id",
                record.run_id,
            ),
            milestones=(
                ("Plan", "RECORDED"),
                ("Artifact", "BOUND" if record.changeset_digest else "NOT_STAGED"),
                ("Validation", "RECORDED" if record.validation_digest else "NOT_VERIFIED"),
                (
                    "Human decision",
                    "APPROVAL_RECORDED"
                    if record.state
                    in {
                        Lifecycle.APPROVAL_RECORDED,
                        Lifecycle.APPLY_INTENT,
                        Lifecycle.APPLY_COMPLETED,
                    }
                    else "CURRENT_APPROVAL_UNCONFIRMED",
                ),
                ("Apply result", record.state.value),
            ),
            recovery_note=record.recovery_note,
        )

    def _permitted(self, capability: str) -> bool:
        try:
            self.authorization.require(capability)
            return True
        except ValueError:
            return False

    def _permission_reason(self, capability: str) -> str:
        try:
            self.authorization.require(capability)
            return "ALLOWED"
        except ValueError as error:
            return self.redactor.redact_text(str(error))[:200]

    def _activity(self, plan: str, step: str) -> tuple[tuple[str, str], ...]:
        with self.store._get_connection() as conn:
            operations = [
                Operation.model_validate_json(row[0])
                for row in conn.execute(
                    "SELECT content_json FROM operations WHERE project_id=? "
                    "AND json_extract(content_json,'$.plan_id')=? "
                    "AND json_extract(content_json,'$.step_id')=? "
                    "ORDER BY updated_at DESC,operation_id LIMIT 20",
                    (self.binding.project_id, plan, step),
                )
            ]
        return tuple(
            (
                o.kind + " / " + o.status.value,
                self.redactor.redact_text(o.message + "\n" + o.output_tail)[:4096],
            )
            for o in operations
        )

    def file_diff(self, node_id: str, revision: str, digest: str, index: int) -> WorkFileDiff:
        self.authorization.require("evidence.read")
        detail = self.detail(node_id, revision)
        authorize_workflow(self.context, WorkflowCapability.EVIDENCE_READ)
        _, records, _ = self._read()
        record = records.get(node_id)
        changeset = self.store.get_changeset(record.changeset_id or "") if record else None
        if (
            record is None
            or changeset is None
            or digest != record.changeset_digest
            or digest != changeset.changeset_digest
            or digest != compute_changeset_digest(changeset)
            or changeset.plan_id != record.plan_id
            or changeset.step_id != record.step_id
            or changeset.base_revision != record.base_revision
            or changeset.worktree_fingerprint != record.worktree_fingerprint
        ):
            raise ValueError("ARTIFACT_STALE: exact artifact bindings failed.")
        if not 0 <= index < len(detail.files):
            raise ValueError("DIFF_INDEX_INVALID")
        selected = [change for change in changeset.changes if change.path == detail.files[index]]
        if len(selected) != 1:
            raise ValueError("DIFF_SCOPE_INVALID")
        change = selected[0]
        if (
            change.operation != FileOperation.DELETE
            and compute_file_sha256(change.content_bytes or b"") != change.content_digest
        ):
            raise ValueError("ARTIFACT_STALE: proposed content digest differs.")
        result = project_file_diff(
            self.binding.project_root, self.binding.project_id, node_id, revision, changeset, change
        )
        if self.snapshot().revision != revision:
            raise ValueError("SNAPSHOT_STALE: artifact changed during review loading.")
        return result

    def events(self, cursor: int) -> WorkEvents:
        self.authorization.require("project.read")
        current = self.snapshot().cursor
        with self.store._get_connection() as conn:
            rows = conn.execute(
                "SELECT sequence FROM workbench_journal WHERE sequence>? "
                "AND (project_id=? OR scope_root=?) ORDER BY sequence LIMIT 101",
                (cursor, self.binding.project_id, str(self.binding.project_root)),
            ).fetchall()
        return WorkEvents(
            project_id=self.binding.project_id,
            cursor=int(rows[99][0]) if len(rows) > 100 else current,
            changed=bool(rows) or cursor > current,
            more=len(rows) > 100,
        )

    def dispatch(self, command: WorkCommand) -> CommandReceipt:
        self.binding.validate_project_id(command.project_id)
        caps = {
            "stage": WorkflowCapability.STAGE,
            "validate": WorkflowCapability.VALIDATE,
            "apply": WorkflowCapability.APPLY,
        }
        authorize_workflow(self.context, caps[command.kind])
        self.authorization.require(str(caps[command.kind]))
        detail = self.detail(command.node_id, command.expected_revision)
        if not any(a.kind == command.kind and a.available for a in detail.actions):
            raise ValueError("ACTION_UNAVAILABLE: inspect current workflow state.")
        plans, records, _ = self._read()
        record = records.get(command.node_id)
        plan, step = next(
            (p, s)
            for p in plans
            for s in p.steps
            if task_id(p.plan_id, s.step_id) == command.node_id
        )
        if command.kind == "apply" and (
            record is None or command.changeset_id != record.changeset_id
        ):
            raise ValueError("CHANGESET_MISMATCH")
        with self._runtime_lock:
            if self.runtime is not None and not self.runtime.configuration_is_current():
                if self.store.list_active_operations(self.binding.project_id):
                    raise ValueError(
                        "CONFIGURATION_BUSY: finish or cancel active work "
                        "before using changed settings."
                    )
                self.runtime.close()
                self.runtime = None
            if self.runtime is None:
                self.runtime = WorkflowRuntime(
                    self.binding, self.settings, authorization=self.authorization
                )
            operation = self.runtime.dispatch(
                command.kind, plan.plan_id, step.step_id, command.request_id, command.changeset_id
            )
        return CommandReceipt(
            operation_id=operation.operation_id,
            status=operation.status.value,
            message=self.redactor.redact_text(operation.message)[:512],
        )

    def receipt(self, command: WorkCommand) -> CommandReceipt | None:
        caps = {
            "stage": WorkflowCapability.STAGE,
            "validate": WorkflowCapability.VALIDATE,
            "apply": WorkflowCapability.APPLY,
        }
        authorize_workflow(self.context, caps[command.kind])
        access = self.authorization.require(str(caps[command.kind]))
        with self.store._get_connection() as conn:
            row = conn.execute(
                "SELECT content_json FROM operations WHERE project_id=? AND request_id=?",
                (command.project_id, command.request_id),
            ).fetchone()
        if row is None:
            return None
        operation = Operation.model_validate_json(row[0])
        if (
            operation.kind != command.kind
            or operation.principal_id != access.principal_id
            or operation.access_digest != access.access_digest
            or operation.actor != self.context.actor
            or task_id(operation.plan_id or "", operation.step_id or "") != command.node_id
            or operation.changeset_id != command.changeset_id
        ):
            raise ValueError("REQUEST_REUSE_REJECTED: request identity has different scope.")
        return CommandReceipt(
            operation_id=operation.operation_id,
            status=operation.status.value,
            message=self.redactor.redact_text(operation.message)[:512],
        )

    def close(self) -> None:
        if self.runtime:
            self.runtime.close()

    def _references(self) -> dict[str, tuple[str, str]]:
        references: dict[str, tuple[str, str]] = {}
        policy = InspectionPolicy(max_text_file_bytes=65536)
        reference_root = self.binding.project_root
        if (
            isinstance(self.authorization, ProjectAuthorization)
            and self.authorization.require("project.read").access_digest
        ):
            reference_root = Path(self.authorization.service().store.binding.governance_root)
        for folder in (
            ".agent/decisions",
            ".agent/learnings",
            ".agent/challenges",
            ".agent/solutions",
            "docs/architecture",
        ):
            try:
                directory = validate_repository_path(reference_root, folder)
                candidates = sorted(directory.iterdir(), key=lambda p: p.name)
            except (OSError, ValueError):
                continue
            for candidate in candidates:
                if len(references) >= 100:
                    return references
                if candidate.suffix not in {".md", ".mmd"}:
                    continue
                relative = candidate.relative_to(reference_root).as_posix()
                try:
                    text = read_repository_text(reference_root, relative, policy=policy)
                except (OSError, ValueError, UnicodeError):
                    continue
                ident = "ref-" + hashlib.sha256(relative.encode()).hexdigest()[:32]
                references[ident] = (relative, text)

        return references

    def image(self, node_id: str, revision: str, index: int) -> ImageContent:
        self.authorization.require("evidence.read")
        authorize_workflow(self.context, WorkflowCapability.EVIDENCE_READ)
        detail = self.detail(node_id, revision)
        _, records, _ = self._read()
        record = records.get(node_id)
        if record is None or record.browser_evidence is None:
            raise ValueError("IMAGE_UNAVAILABLE")
        capture = record.browser_evidence.capture
        if (
            capture.project_id != self.binding.project_id
            or capture.plan_id != record.plan_id
            or capture.step_id != record.step_id
            or capture.changeset_digest != detail.changeset_digest
            or not capture.cleanup_verified
            or not 0 <= index < len(capture.images)
        ):
            raise ValueError("IMAGE_SCOPE_INVALID")
        image = capture.images[index]
        root = safe_path(self.state_dir / "browser" / self.binding.project_id / capture.capture_id)
        target = safe_path(root / image.filename)
        before = target.stat()
        if target.parent != root or target.suffix != ".png" or not stat.S_ISREG(before.st_mode):
            raise ValueError("IMAGE_PATH_INVALID")
        if not 24 <= before.st_size <= 5 * 1024 * 1024:
            raise ValueError("IMAGE_SIZE_INVALID")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(target, flags), "rb") as handle:
            opened = os.fstat(handle.fileno())
            safe_path(target)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise ValueError("IMAGE_CHANGED")
            data = handle.read(5 * 1024 * 1024 + 1)
            after = os.fstat(handle.fileno())
        if (
            after.st_mtime_ns != before.st_mtime_ns
            or after.st_size != before.st_size
            or data[:8] != b"\x89PNG\r\n\x1a\n"
            or hashlib.sha256(data).hexdigest() != image.sha256
            or self.snapshot().revision != revision
        ):
            raise ValueError("IMAGE_CHANGED")
        return ImageContent(data=base64.b64encode(data).decode("ascii"))
