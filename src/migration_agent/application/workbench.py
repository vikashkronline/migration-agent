"""Provider-neutral query and command boundary for the project control center."""

import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.changeset import DestinationBinding
from migration_agent.domain.inspection_access import (
    InspectionCapability,
    InspectionContext,
    authorize_inspection,
)
from migration_agent.domain.redaction import RedactionPolicy


class ViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkNode(ViewModel):
    node_id: str
    parent_id: str | None = None
    label: str
    kind: Literal["project", "group", "task", "reference"]
    status: str = "UNKNOWN"
    dependencies: tuple[str, ...] = ()
    child_count: int = 0
    complete_count: int = 0
    task_count: int = 0
    needs_attention: bool = False
    run_id: str | None = None
    status_tone: Literal["neutral", "info", "success", "warning", "danger"] = "neutral"


class WorkSnapshot(ViewModel):
    schema_version: Literal[1] = 1
    project_id: str
    revision: str
    cursor: int = 0
    actor: str
    assurance: str
    nodes: tuple[WorkNode, ...]
    warnings: tuple[str, ...] = ()


class NodePage(ViewModel):
    schema_version: Literal[1] = 1
    project_id: str
    revision: str
    cursor: int
    nodes: tuple[WorkNode, ...]
    ancestors: tuple[WorkNode, ...] = ()
    total: int
    next_offset: int | None = None
    warnings: tuple[str, ...] = ()


class WorkAction(ViewModel):
    kind: Literal["stage", "validate", "apply"]
    label: str
    reason: str
    available: bool = False


class WorkImage(ViewModel):
    index: int
    label: str
    digest: str


class ImageContent(ViewModel):
    mime_type: Literal["image/png"] = "image/png"
    data: str


class DiffLine(ViewModel):
    kind: Literal["context", "remove", "add"]
    old_line: int | None = None
    new_line: int | None = None
    text: str


class DiffHunk(ViewModel):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[DiffLine, ...]


class WorkFileDiff(ViewModel):
    project_id: str
    node_id: str
    revision: str
    changeset_digest: str
    base_revision: str
    path: str
    operation: Literal["CREATE", "MODIFY", "DELETE"]
    file_mode: str
    available: bool = True
    reason: str = ""
    hunks: tuple[DiffHunk, ...] = ()


class WorkDetail(ViewModel):
    schema_version: Literal[1] = 1
    project_id: str
    revision: str
    node: WorkNode
    summary: str
    run_id: str | None = None
    changeset_id: str | None = None
    changeset_digest: str | None = None
    base_revision: str | None = None
    policy_digest: str | None = None
    validation_digest: str | None = None
    evidence: tuple[tuple[str, str], ...] = ()
    files: tuple[str, ...] = ()
    diff: str = ""
    review_command: tuple[str, ...] = ()
    actions: tuple[WorkAction, ...] = ()
    activity: tuple[tuple[str, str], ...] = ()
    diagram: str = ""
    images: tuple[WorkImage, ...] = ()
    milestones: tuple[tuple[str, str], ...] = ()
    owner: str = ""
    acceptance: tuple[str, ...] = ()
    provenance: str = ""
    ask_command: tuple[str, ...] = ()
    recovery_note: str = ""
    destination: DestinationBinding | None = None


class WorkQuestion(ViewModel):
    project_id: str
    node_id: str
    revision: str
    question: str = Field(min_length=3, max_length=2048)


class WorkCitation(ViewModel):
    label: str
    text: str
    node_id: str


class WorkAnswer(ViewModel):
    project_id: str
    node_id: str
    revision: str
    mode: Literal["recorded_evidence"] = "recorded_evidence"
    answer: str
    citations: tuple[WorkCitation, ...] = ()


class WorkCommand(ViewModel):
    project_id: str
    node_id: str
    expected_revision: str
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    kind: Literal["stage", "validate", "apply"]
    changeset_id: str | None = None


class CommandReceipt(ViewModel):
    operation_id: str
    status: str
    message: str


class WorkEvents(ViewModel):
    schema_version: Literal[1] = 1
    project_id: str
    cursor: int
    changed: bool
    more: bool = False


class WorkSourcePort(Protocol):
    def snapshot(self) -> WorkSnapshot: ...
    def detail(self, node_id: str, revision: str) -> WorkDetail: ...
    def events(self, cursor: int) -> WorkEvents: ...
    def dispatch(self, command: WorkCommand) -> CommandReceipt: ...
    def receipt(self, command: WorkCommand) -> CommandReceipt | None: ...
    def image(self, node_id: str, revision: str, index: int) -> ImageContent: ...
    def file_diff(self, node_id: str, revision: str, digest: str, index: int) -> WorkFileDiff: ...


class WorkbenchService:
    def __init__(self, source: WorkSourcePort, context: InspectionContext) -> None:
        self.source = source
        self.context = context

    def snapshot(self, project_id: str | None = None) -> WorkSnapshot:
        authorize_inspection(self.context, InspectionCapability.PROJECT_READ)
        authorize_inspection(self.context, InspectionCapability.PLAN_READ)
        authorize_inspection(self.context, InspectionCapability.RUN_READ)
        snapshot = self.source.snapshot()
        if project_id is not None and project_id != snapshot.project_id:
            raise ValueError("PROJECT_MISMATCH: project is not bound to this session.")
        return snapshot

    def page(
        self,
        project_id: str,
        parent: str | None,
        query: str = "",
        offset: int = 0,
        limit: int = 100,
        attention: bool = False,
        kind: str | None = None,
    ) -> NodePage:
        if offset < 0 or not 1 <= limit <= 100 or len(query) > 128:
            raise ValueError("QUERY_INVALID: bounded paging and search required.")
        if kind is not None and kind not in {"project", "group", "task", "reference"}:
            raise ValueError("QUERY_INVALID: unsupported node kind.")
        snap = self.snapshot(project_id)
        indexed = {n.node_id: n for n in snap.nodes}
        if parent and parent not in indexed:
            raise KeyError("NODE_NOT_FOUND")
        items = []
        for node in snap.nodes:
            if kind is not None and node.kind != kind:
                continue
            if query and query.casefold() not in node.label.casefold():
                continue
            if attention:
                if not node.needs_attention:
                    continue
            elif not query and kind is None and node.parent_id != parent:
                continue
            items.append(node)
        page = items[offset : offset + limit]
        ancestors: dict[str, WorkNode] = {}
        for node in page:
            seen = {node.node_id}
            current = node.parent_id
            while current:
                if current in seen or current not in indexed:
                    raise ValueError("TREE_INVALID: missing or cyclic ownership.")
                seen.add(current)
                ancestor = indexed[current]
                ancestors[current] = ancestor
                current = ancestor.parent_id
        return NodePage(
            project_id=project_id,
            revision=snap.revision,
            cursor=snap.cursor,
            nodes=tuple(page),
            ancestors=tuple(ancestors.values()),
            total=len(items),
            next_offset=offset + limit if offset + limit < len(items) else None,
            warnings=snap.warnings,
        )

    def detail(self, project_id: str, node_id: str, revision: str) -> WorkDetail:
        snap = self.snapshot(project_id)
        if snap.revision != revision:
            raise ValueError("SNAPSHOT_STALE: refresh before inspecting current evidence.")
        if node_id not in {n.node_id for n in snap.nodes}:
            raise KeyError("NODE_NOT_FOUND")
        authorize_inspection(self.context, InspectionCapability.CHANGESET_READ)
        return self.source.detail(node_id, revision)

    def events(self, project_id: str, cursor: int, revision: str = "") -> WorkEvents:
        snapshot = self.snapshot(project_id)
        if cursor < 0:
            raise ValueError("CURSOR_INVALID")
        events = self.source.events(cursor)
        return events.model_copy(
            update={"changed": events.changed or bool(revision and revision != snapshot.revision)}
        )

    def file_diff(
        self, project_id: str, node_id: str, revision: str, digest: str, index: int
    ) -> WorkFileDiff:
        detail = self.detail(project_id, node_id, revision)
        if not digest or digest != detail.changeset_digest:
            raise ValueError("ARTIFACT_STALE: select the exact current artifact.")
        if not 0 <= index < len(detail.files):
            raise ValueError("DIFF_INDEX_INVALID: select a declared file.")
        result = self.source.file_diff(node_id, revision, digest, index)
        if (
            result.project_id != project_id
            or result.node_id != node_id
            or result.revision != revision
            or result.changeset_digest != digest
            or result.path != detail.files[index]
        ):
            raise ValueError("DIFF_SCOPE_INVALID: diff does not match selected evidence.")
        self.detail(project_id, node_id, revision)
        return result

    def dispatch(self, command: WorkCommand) -> CommandReceipt:
        snap = self.snapshot(command.project_id)
        prior = self.source.receipt(command)
        if prior is not None:
            return prior
        if snap.revision != command.expected_revision:
            raise ValueError("SNAPSHOT_STALE: command requires a current snapshot.")
        if command.node_id not in {n.node_id for n in snap.nodes}:
            raise KeyError("NODE_NOT_FOUND")
        return self.source.dispatch(command)

    def image(self, project_id: str, node_id: str, revision: str, index: int) -> ImageContent:
        self.detail(project_id, node_id, revision)
        if not 0 <= index < 128:
            raise ValueError("IMAGE_INVALID")
        return self.source.image(node_id, revision, index)

    def answer(self, question: WorkQuestion) -> WorkAnswer:
        if RedactionPolicy().contains_secret(question.question):
            raise ValueError("QUESTION_REJECTED: credential-shaped content is not accepted.")
        detail = self.detail(question.project_id, question.node_id, question.revision)
        status_fact = detail.node.status
        if status_fact == "UNKNOWN" and detail.node.kind == "group" and detail.node.task_count == 0:
            status_fact = "UNKNOWN (Unconfigured: no custom tasks declared in this group)"
        facts = [
            ("Status", status_fact),
            ("Scope", detail.summary),
            ("Run", detail.run_id or "Not started"),
            ("Artifact", detail.changeset_digest or "Not staged"),
            ("Policy", detail.policy_digest or "Not recorded"),
            ("Owner", detail.owner or "Not declared"),
            ("Validation", detail.validation_digest or "Not verified"),
            *detail.evidence,
            *detail.milestones,
            *(
                (
                    action.label,
                    ("Available: " if action.available else "Unavailable: ") + action.reason,
                )
                for action in detail.actions
            ),
            *(("Acceptance", value) for value in detail.acceptance),
            *(("Dependency", dependency) for dependency in detail.node.dependencies),
        ]
        terms = {
            token
            for token in re.findall(r"[\w-]+", question.question.casefold())
            if len(token) > 2
            and token
            not in {
                "what",
                "which",
                "the",
                "are",
                "this",
                "that",
                "how",
                "why",
                "does",
                "can",
                "for",
                "with",
                "and",
                "current",
                "please",
                "have",
                "show",
            }
        }
        scored = [
            (sum(term in (label + " " + value).casefold() for term in terms), label, value)
            for label, value in facts
        ]
        citations = tuple(
            WorkCitation(label=label, text=value[:2048], node_id=detail.node.node_id)
            for score, label, value in sorted(scored, key=lambda fact: -fact[0])[:6]
            if score
        )
        self.detail(question.project_id, question.node_id, question.revision)
        return WorkAnswer(
            project_id=detail.project_id,
            node_id=detail.node.node_id,
            revision=detail.revision,
            answer=(
                "Matching recorded facts are listed below. "
                "These excerpts are not model-generated conclusions."
            )
            if citations
            else (
                "No recorded evidence answers this question. Inspect the item "
                "or use the provider-assisted CLI handoff for reasoning."
            ),
            citations=citations,
        )
