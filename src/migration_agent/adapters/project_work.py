"""Bounded read-only Git declarations projected onto existing workflow evidence."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.application.workbench import WorkNode
from migration_agent.domain.project_work import ProjectWorkDefinition, ProjectWorkItem
from migration_agent.ports.filesystem import InspectionPolicy

DEFINITION_PATH = ".agent/project-work.json"


@dataclass(frozen=True)
class ProjectWorkRead:
    definition: ProjectWorkDefinition | None = None
    warnings: tuple[str, ...] = ()


def read_project_work(root: Path) -> ProjectWorkRead:
    try:
        path = validate_repository_path(root, DEFINITION_PATH)
        if not path.exists():
            return ProjectWorkRead()
        content = read_repository_text(
            root, DEFINITION_PATH, policy=InspectionPolicy(max_text_file_bytes=512 * 1024)
        )
        return ProjectWorkRead(ProjectWorkDefinition.model_validate_json(content))
    except (ValueError, OSError, UnicodeError):
        return ProjectWorkRead(
            warnings=(
                "Project-work definition is invalid or unreadable. Its declarations were not used; "
                "existing canonical workflow records remain inspectable.",
            )
        )


def project_item_id(item: ProjectWorkItem, resolve_workflow: Callable[[str, str], str]) -> str:
    if item.workflow:
        return resolve_workflow(item.workflow.workflow_id, item.workflow.task_id)
    return "work-" + item.item_id


def project_item(
    read: ProjectWorkRead, ident: str, resolve_workflow: Callable[[str, str], str]
) -> ProjectWorkItem | None:
    if read.definition is None:
        return None
    return next(
        (
            item
            for item in read.definition.items
            if project_item_id(item, resolve_workflow) == ident
        ),
        None,
    )


def project_work_digest(read: ProjectWorkRead) -> str:
    content = read.definition.model_dump_json() if read.definition else "\n".join(read.warnings)
    return hashlib.sha256(content.encode()).hexdigest()


def attach_project_work(
    nodes: list[WorkNode], read: ProjectWorkRead, resolve_workflow: Callable[[str, str], str]
) -> list[WorkNode]:
    definition = read.definition
    if definition is None:
        return nodes
    indexed = {node.node_id: node for node in nodes}
    if definition.project_name:
        indexed["project"] = indexed["project"].model_copy(
            update={"label": definition.project_name}
        )
    identities = {
        item.item_id: project_item_id(item, resolve_workflow) for item in definition.items
    }
    items = sorted(definition.items, key=lambda item: (item.order, item.item_id))
    for item in items:
        ident = identities[item.item_id]
        original = indexed.get(ident)
        if original is None:
            original = WorkNode(
                node_id=ident,
                kind=item.kind,
                label=item.title,
                status="MISSING_WORKFLOW_EVIDENCE"
                if item.workflow
                else "UNKNOWN"
                if item.declared_status == "UNKNOWN"
                else "DECLARED_" + item.declared_status,
                needs_attention=item.workflow is not None or item.declared_status == "COMPLETE",
            )
        indexed[ident] = original.model_copy(
            update={
                "label": item.title,
                "parent_id": identities[item.parent_id] if item.parent_id else item.section,
                "dependencies": tuple(
                    dict.fromkeys(
                        (*original.dependencies, *(identities[d] for d in item.dependencies))
                    )
                ),
            }
        )
    declared = set(identities.values())
    return (
        [indexed[node.node_id] for node in nodes[:4]]
        + [indexed[identities[item.item_id]] for item in items]
        + [indexed[node.node_id] for node in nodes[4:] if node.node_id not in declared]
    )


def rollup_work(nodes: list[WorkNode]) -> list[WorkNode]:
    children: dict[str | None, list[WorkNode]] = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node)
    cache: dict[str, tuple[WorkNode, ...]] = {}

    def tasks(node: WorkNode, seen: frozenset[str] = frozenset()) -> tuple[WorkNode, ...]:
        if node.node_id in seen or len(seen) > 40:
            raise ValueError("TREE_INVALID: ownership is cyclic or too deep.")
        if node.node_id in cache:
            return cache[node.node_id]
        value = (
            (node,)
            if node.kind == "task"
            else tuple(
                task
                for child in children.get(node.node_id, [])
                for task in tasks(child, seen | {node.node_id})
            )
        )
        cache[node.node_id] = value
        return value

    result = []
    for node in nodes:
        scoped = (
            tuple(n for n in nodes if n.kind == "task")
            if node.node_id == "project"
            else (tasks(node) if node.kind == "group" else ())
        )
        state = node.status
        attention = node.needs_attention if node.kind == "task" else False
        if node.kind in {"group", "project"} and scoped:
            if all(n.status == "APPLY_COMPLETED" for n in scoped):
                state = "APPLY_COMPLETED"
            elif any(n.status == "RECOVERY_REQUIRED" for n in scoped):
                state = "RECOVERY_REQUIRED"
            elif any("FAILED" in n.status for n in scoped):
                state = "ATTENTION_REQUIRED"
            elif any(n.status == "BASE_CHANGED" for n in scoped):
                state = "BASE_CHANGED"
            elif any(n.status in {"VALIDATION_PASSED", "APPROVAL_RECORDED"} for n in scoped):
                state = "READY_TO_APPLY"
            else:
                state = "WORK_PENDING"
        tone = (
            "danger"
            if "RECOVERY" in state or "FAILED" in state or state == "ATTENTION_REQUIRED"
            else (
                "success"
                if state == "APPLY_COMPLETED"
                else "warning"
                if state
                in {
                    "BASE_CHANGED",
                    "MISSING_WORKFLOW_EVIDENCE",
                    "DECLARED_COMPLETE",
                    "APPROVAL_PENDING",
                    "VALIDATION_PASSED",
                    "READY_TO_APPLY",
                }
                else "neutral"
                if state in {"UNKNOWN", "PLANNED", "DECLARED_PLANNED"}
                else "info"
            )
        )
        result.append(
            node.model_copy(
                update={
                    "child_count": len(children.get(node.node_id, [])),
                    "task_count": len(scoped),
                    "complete_count": sum(n.status == "APPLY_COMPLETED" for n in scoped),
                    "status": state,
                    "status_tone": tone,
                    "needs_attention": attention,
                }
            )
        )
    return result
