"""Generic project declarations cannot manufacture trusted workflow completion."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_workbench import make_source, save_plan, service

from migration_agent.adapters.workbench import task_id
from migration_agent.application.workbench import WorkCommand, WorkQuestion
from migration_agent.domain.project_work import ProjectWorkDefinition


def write_definition(root: Path, items: list[dict], **extra) -> Path:
    path = root / ".agent" / "project-work.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "items": items, **extra}), encoding="utf-8")
    return path


def test_declared_foundation_and_nested_modules_link_existing_evidence_once(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    save_plan(source)
    definition = write_definition(
        source.binding.project_root,
        [
            {
                "item_id": "setup",
                "section": "foundation",
                "kind": "group",
                "title": "Setup & toolchain",
            },
            {
                "item_id": "linked",
                "parent_id": "setup",
                "kind": "task",
                "title": "Toolchain evidence",
                "workflow": {"workflow_id": "plan-1", "task_id": "step-1"},
                "owner": "Team",
                "acceptance": ["Check supported toolchain"],
            },
            {"item_id": "accounts", "kind": "group", "title": "Accounts module"},
            {
                "item_id": "profile",
                "parent_id": "accounts",
                "kind": "group",
                "title": "Profile feature",
            },
            {
                "item_id": "design",
                "parent_id": "profile",
                "kind": "task",
                "title": "Design",
                "declared_status": "COMPLETE",
                "dependencies": ["linked"],
            },
        ],
        project_name="Generic platform",
        objective="Deliver documented capabilities",
    )
    before = definition.read_bytes()
    snap = source.snapshot()
    nodes = {node.node_id: node for node in snap.nodes}
    assert nodes["project"].label == "Generic platform"
    assert nodes["project"].task_count == 2 and nodes["project"].complete_count == 0
    assert nodes["foundation"].task_count == 1
    assert nodes["work-accounts"].task_count == 1
    assert nodes["work-design"].status == "DECLARED_COMPLETE"
    assert nodes[task_id("plan-1", "step-1")].parent_id == "work-setup"
    assert len([node for node in snap.nodes if node.node_id == task_id("plan-1", "step-1")]) == 1
    detail = service(source).detail(snap.project_id, task_id("plan-1", "step-1"), snap.revision)
    assert detail.owner == "Team" and detail.acceptance == ("Check supported toolchain",)
    assert "Git project-work declaration" in detail.provenance
    assert definition.read_bytes() == before


@pytest.mark.parametrize(
    "items",
    [
        [
            {"item_id": "same", "kind": "group", "title": "A"},
            {"item_id": "same", "kind": "group", "title": "B"},
        ],
        [
            {"item_id": "a", "kind": "group", "title": "A", "parent_id": "b"},
            {"item_id": "b", "kind": "group", "title": "B", "parent_id": "a"},
        ],
        [
            {"item_id": "a", "kind": "task", "title": "A", "dependencies": ["b"]},
            {"item_id": "b", "kind": "task", "title": "B", "dependencies": ["a"]},
        ],
        [{"item_id": "a", "kind": "task", "title": "A", "dependencies": ["missing"]}],
        [
            {
                "item_id": "a",
                "kind": "task",
                "title": "A",
                "workflow": {"workflow_id": "p", "task_id": "s"},
            },
            {
                "item_id": "b",
                "kind": "task",
                "title": "B",
                "workflow": {"workflow_id": "p", "task_id": "s"},
            },
        ],
    ],
)
def test_invalid_project_graphs_are_rejected(items: list[dict]) -> None:
    with pytest.raises(ValidationError):
        ProjectWorkDefinition.model_validate({"items": items})


def test_invalid_definition_is_explicit_and_cannot_hide_canonical_work(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    save_plan(source)
    write_definition(
        source.binding.project_root,
        [{"item_id": "bad", "kind": "task", "title": "Bad", "parent_id": "missing"}],
    )
    snap = source.snapshot()
    assert snap.warnings and any(node.node_id == task_id("plan-1", "step-1") for node in snap.nodes)
    assert service(source).page(snap.project_id, None).warnings == snap.warnings


def test_missing_workflow_binding_is_stable_and_not_executable(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    path = write_definition(
        source.binding.project_root,
        [
            {
                "item_id": "scope",
                "kind": "task",
                "title": "Bound task",
                "workflow": {"workflow_id": "plan-1", "task_id": "step-1"},
            }
        ],
    )
    api = service(source)
    snap = api.snapshot()
    ident = task_id("plan-1", "step-1")
    assert (
        api.detail(snap.project_id, ident, snap.revision).node.status == "MISSING_WORKFLOW_EVIDENCE"
    )
    with pytest.raises(ValueError, match="ACTION_UNAVAILABLE"):
        api.dispatch(
            WorkCommand(
                project_id=snap.project_id,
                node_id=ident,
                expected_revision=snap.revision,
                request_id="no-evidence",
                kind="apply",
            )
        )
    save_plan(source)
    assert source.snapshot().revision != snap.revision
    assert api.detail(snap.project_id, ident, source.snapshot().revision).node.status == "PLANNED"
    path.write_text(json.dumps({"items": []}), encoding="utf-8")
    assert api.events(snap.project_id, source.snapshot().cursor, snap.revision).changed


def test_recorded_context_answers_are_scoped_cited_and_truthful(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    save_plan(source)
    api = service(source)
    snap = api.snapshot()
    question = WorkQuestion(
        project_id=snap.project_id,
        node_id=task_id("plan-1", "step-1"),
        revision=snap.revision,
        question="What is the current status?",
    )
    answer = api.answer(question)
    assert answer.mode == "recorded_evidence"
    assert any(
        citation.label == "Status" and citation.text == "PLANNED" for citation in answer.citations
    )
    assert (
        api.answer(
            question.model_copy(update={"question": "unrecorded zebrafish behavior"})
        ).citations
        == ()
    )
    with pytest.raises(ValueError, match="PROJECT_MISMATCH"):
        api.answer(question.model_copy(update={"project_id": "foreign"}))
    save_plan(source, ident="another")
    with pytest.raises(ValueError, match="STALE"):
        api.answer(question)


def test_credentials_and_extra_authority_fields_are_not_accepted(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    api = service(source)
    snap = api.snapshot()
    question = WorkQuestion(
        project_id=snap.project_id,
        node_id="project",
        revision=snap.revision,
        question="status for sk-" + "A" * 48,
    )
    with pytest.raises(ValueError, match="QUESTION_REJECTED"):
        api.answer(question)
    with pytest.raises(ValidationError):
        WorkQuestion.model_validate({**question.model_dump(), "actor": "admin"})
    path = write_definition(source.binding.project_root, [], objective="sk-" + "A" * 48)
    current = api.snapshot()
    assert current.warnings and "A" * 48 not in current.model_dump_json()
    assert path.exists()


def test_rollup_work_surfaces_attention_required_and_needs_attention() -> None:
    from migration_agent.adapters.project_work import rollup_work
    from migration_agent.application.workbench import WorkNode

    nodes = [
        WorkNode(node_id="project", kind="project", label="Project", status="UNKNOWN"),
        WorkNode(
            node_id="group-1",
            parent_id="project",
            kind="group",
            label="Group 1",
            status="WORK_PENDING",
        ),
        WorkNode(
            node_id="task-1",
            parent_id="group-1",
            kind="task",
            label="Task 1",
            status="VALIDATION_FAILED",
            needs_attention=True,
        ),
        WorkNode(
            node_id="task-2",
            parent_id="group-1",
            kind="task",
            label="Task 2",
            status="PLANNED",
            needs_attention=False,
        ),
    ]
    rolled = {n.node_id: n for n in rollup_work(nodes)}
    assert rolled["group-1"].status == "ATTENTION_REQUIRED"
    assert rolled["group-1"].status_tone == "danger"
    assert rolled["group-1"].needs_attention is False

    assert rolled["project"].status == "ATTENTION_REQUIRED"
    assert rolled["project"].status_tone == "danger"
    assert rolled["project"].needs_attention is False
    assert rolled["task-1"].needs_attention is True


def test_detail_surfaces_recovery_note_and_policy_evidence_on_failed_validation(
    tmp_path: Path,
) -> None:
    from migration_agent.domain.host_workflow import Lifecycle, WorkflowRecord

    source = make_source(tmp_path)
    save_plan(source)
    lease = source.store.acquire_lease(source.binding.project_id, "test", ttl=30)
    try:
        r0 = source.store.save_workflow(
            WorkflowRecord(
                project_id=source.binding.project_id,
                source_root=str(source.binding.project_root),
                run_id="run-1",
                plan_id="plan-1",
                step_id="step-1",
                state=Lifecycle.PLAN_SAVED,
                base_revision="base",
                root_commit="root",
                worktree_fingerprint="fp",
                policy_digest="policy",
            ),
            lease,
        )
        r1 = source.store.save_workflow(
            r0.model_copy(update={"state": Lifecycle.STAGE_VERIFIED, "version": r0.version}),
            lease,
        )
        r2 = source.store.save_workflow(
            r1.model_copy(update={"state": Lifecycle.VALIDATION_RUNNING, "version": r1.version}),
            lease,
        )
        source.store.save_workflow(
            r2.model_copy(
                update={
                    "state": Lifecycle.VALIDATION_FAILED,
                    "version": r2.version,
                    "recovery_note": "ISOLATION_REQUIRED: native execution blocked",
                }
            ),
            lease,
        )
    finally:
        source.store.release_lease(lease)

    api = service(source)
    snap = api.snapshot()
    detail = api.detail(snap.project_id, task_id("plan-1", "step-1"), snap.revision)
    assert detail.recovery_note == "ISOLATION_REQUIRED: native execution blocked"
    assert detail.evidence == (
        ("Execution gate / Policy", "ISOLATION_REQUIRED: native execution blocked"),
    )
    validate_action = next(a for a in detail.actions if a.kind == "validate")
    assert validate_action.available is True
