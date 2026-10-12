"""Canonical GUI queries, durable invalidation and exact command boundaries."""

from pathlib import Path
from time import perf_counter

import pytest
from access_fixture import WorkflowAuthorizationFixture
from pydantic import ValidationError

from migration_agent.adapters.workbench import CanonicalWorkbench, task_id
from migration_agent.application.workbench import WorkbenchService, WorkCommand
from migration_agent.config import Settings
from migration_agent.domain.host_workflow import Operation, OperationStatus
from migration_agent.domain.inspection_access import InspectionCapability, InspectionContext
from migration_agent.domain.planning import AssuranceLevel, MigrationPlan, MigrationStep
from migration_agent.domain.workflow_access import WorkflowCapability, WorkflowContext


def make_source(tmp_path: Path) -> CanonicalWorkbench:
    root = tmp_path / "project"
    root.mkdir()
    source = CanonicalWorkbench(
        root,
        Settings(state_dir=tmp_path / "state", staging_root=tmp_path / "stage"),
        WorkflowContext(
            actor="operator",
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(WorkflowCapability),
        ),
    )
    source.authorization = WorkflowAuthorizationFixture()
    return source


def service(source: CanonicalWorkbench) -> WorkbenchService:
    return WorkbenchService(
        source,
        InspectionContext(
            actor="operator",
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(InspectionCapability),
        ),
    )


def save_plan(
    source: CanonicalWorkbench, ident: str = "plan-1", title: str = "Inspect evidence"
) -> None:
    source.store.save_plan(
        MigrationPlan(
            plan_id=ident,
            run_id="run-1",
            source_root=str(source.binding.project_root),
            steps=[MigrationStep(step_id="step-1", title=title, description="Observed evidence")],
        )
    )


def test_empty_project_never_fabricates_readiness(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    before = list(source.binding.project_root.rglob("*"))
    snap = service(source).snapshot()
    assert snap.nodes[0].status == "INITIALIZED"
    assert all(n.task_count == 0 for n in snap.nodes)
    assert all(n.status == "UNKNOWN" for n in snap.nodes[1:])
    assert list(source.binding.project_root.rglob("*")) == before
    assert source.store.db_path.parent != source.binding.project_root


def test_canonical_cross_process_writes_invalidate_snapshot(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    api = service(source)
    previous = api.snapshot()
    save_plan(source)
    current = api.snapshot()
    assert current.cursor > previous.cursor
    assert current.revision != previous.revision
    assert source.events(previous.cursor).changed
    reopened = CanonicalWorkbench(source.binding.project_root, source.settings, source.context)
    reopened.authorization = source.authorization
    assert reopened.snapshot().cursor == current.cursor
    assert reopened.snapshot().revision == current.revision
    with pytest.raises(ValueError, match="STALE"):
        api.detail(current.project_id, "project", previous.revision)


def test_foreign_plans_and_project_queries_are_rejected(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    source.store.save_plan(MigrationPlan(plan_id="other", run_id="other", source_root=str(foreign)))
    assert not any(n.kind == "task" for n in source.snapshot().nodes)
    with pytest.raises(ValueError, match="PROJECT_MISMATCH"):
        service(source).page("other-project", None)


def test_search_returns_ancestors_and_bounded_pages(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    save_plan(source)
    api = service(source)
    snap = api.snapshot()
    result = api.page(snap.project_id, None, "Inspect")
    assert len(result.nodes) == 1
    assert {n.node_id for n in result.ancestors} >= {"work"}
    assert result.nodes[0].status == "PLANNED"
    with pytest.raises(ValueError, match="QUERY_INVALID"):
        api.page(snap.project_id, None, limit=101)
    with pytest.raises(KeyError):
        api.page(snap.project_id, "missing")


def test_actor_and_approval_cannot_be_supplied_by_browser(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    save_plan(source)
    snap = source.snapshot()
    payload = dict(
        project_id=snap.project_id,
        node_id=task_id("plan-1", "step-1"),
        expected_revision=snap.revision,
        request_id="request-1",
        kind="apply",
    )
    with pytest.raises(ValidationError):
        WorkCommand(**payload, actor="admin")
    with pytest.raises(ValidationError):
        WorkCommand(**{**payload, "kind": "approve"})
    with pytest.raises(ValueError, match="ACTION_UNAVAILABLE"):
        service(source).dispatch(WorkCommand(**payload))


def test_inspection_capabilities_are_not_session_authentication(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    denied = WorkbenchService(
        source,
        InspectionContext(
            actor="visitor",
            assurance=AssuranceLevel.MODE_C,
            capabilities=frozenset(),
        ),
    )
    with pytest.raises(ValueError, match="CAPABILITY_DENIED"):
        denied.snapshot()


def test_retry_returns_durable_receipt_without_reexecuting(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    save_plan(source)
    snap = source.snapshot()
    operation = Operation(
        operation_id="op-1",
        project_id=snap.project_id,
        request_id="r-1",
        kind="stage",
        actor="operator",
        plan_id="plan-1",
        principal_id="fixture",
        access_digest="sha256:" + "f" * 64,
        step_id="step-1",
        payload_digest="fixture",
        status=OperationStatus.SUCCEEDED,
    )
    source.store.claim_request(operation)
    command = WorkCommand(
        project_id=snap.project_id,
        node_id=task_id("plan-1", "step-1"),
        expected_revision=snap.revision,
        request_id="r-1",
        kind="stage",
    )
    receipt = service(source).dispatch(command)
    assert receipt.operation_id == "op-1"
    assert source.runtime is None
    with pytest.raises(ValueError, match="REQUEST_REUSE_REJECTED"):
        service(source).dispatch(command.model_copy(update={"kind": "apply"}))


def test_reference_provenance_and_live_invalidation(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    directory = source.binding.project_root / "docs" / "architecture"
    directory.mkdir(parents=True)
    document = directory / "overview.md"
    document.write_text("# Boundaries\n```mermaid\nflowchart LR\n A-->B\n```", encoding="utf-8")
    api = service(source)
    snap = api.snapshot()
    reference = next(n for n in snap.nodes if n.kind == "reference")
    assert reference.status == "OBSERVED"
    assert "flowchart" in api.detail(snap.project_id, reference.node_id, snap.revision).diagram
    document.write_text("# Changed boundaries", encoding="utf-8")
    assert api.events(snap.project_id, snap.cursor, snap.revision).changed
    with pytest.raises(ValueError, match="STALE"):
        api.detail(snap.project_id, reference.node_id, snap.revision)


def test_unscoped_image_rejected_without_opening_paths(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    save_plan(source)
    snap = source.snapshot()
    with pytest.raises(ValueError, match="IMAGE_UNAVAILABLE"):
        service(source).image(snap.project_id, task_id("plan-1", "step-1"), snap.revision, 0)


def test_large_projection_is_paged_with_truthful_unloaded_rollups(
    tmp_path: Path, record_property
) -> None:
    source = make_source(tmp_path)
    for plan_index in range(10):
        source.store.save_plan(
            MigrationPlan(
                plan_id=f"p-{plan_index:02}",
                run_id=f"r-{plan_index}",
                source_root=str(source.binding.project_root),
                steps=[
                    MigrationStep(
                        step_id=f"s-{i:03}",
                        title=f"Generic documentation task {plan_index:02}-{i:03}",
                        description="Verify documentation evidence",
                    )
                    for i in range(100)
                ],
            )
        )
    api = service(source)
    start = perf_counter()
    snapshot = api.snapshot()
    result = api.page(snapshot.project_id, None, "documentation")
    record_property("thousand_task_snapshot_and_search_seconds", perf_counter() - start)
    assert snapshot.nodes[0].task_count == 1000
    assert snapshot.nodes[0].complete_count == 0
    assert len(result.nodes) == 100 and result.total == 1000 and result.next_offset == 100
    assert all(node.status == "PLANNED" for node in result.nodes)
    assert not api.page(snapshot.project_id, None, attention=True).nodes
    last = api.page(snapshot.project_id, None, "documentation", offset=900)
    assert len(last.nodes) == 100 and last.next_offset is None
    assert not {n.node_id for n in last.nodes} & {n.node_id for n in result.nodes}


def test_detail_actions_block_validation_when_prerequisites_unapplied(tmp_path: Path) -> None:
    from migration_agent.domain.host_workflow import Lifecycle, WorkflowRecord
    from migration_agent.domain.planning import MigrationStep

    source = make_source(tmp_path)
    source.store.save_plan(
        MigrationPlan(
            plan_id="plan-1",
            run_id="run-1",
            source_root=str(source.binding.project_root),
            steps=[
                MigrationStep(step_id="step-1", title="Step 1", description="Prereq step"),
                MigrationStep(
                    step_id="step-2",
                    title="Step 2",
                    description="Dependent step",
                    dependencies=["step-1"],
                ),
            ],
        )
    )
    lease = source.store.acquire_lease(source.binding.project_id, "test", ttl=30)
    try:
        r0 = source.store.save_workflow(
            WorkflowRecord(
                project_id=source.binding.project_id,
                source_root=str(source.binding.project_root),
                run_id="run-1",
                plan_id="plan-1",
                step_id="step-2",
                state=Lifecycle.PLAN_SAVED,
                base_revision="base",
                root_commit="root",
                worktree_fingerprint="fp",
                policy_digest="policy",
            ),
            lease,
        )
        source.store.save_workflow(
            r0.model_copy(update={"state": Lifecycle.STAGE_VERIFIED, "version": r0.version}),
            lease,
        )
    finally:
        source.store.release_lease(lease)

    api = service(source)
    snap = api.snapshot()
    detail = api.detail(snap.project_id, task_id("plan-1", "step-2"), snap.revision)
    val_action = next(a for a in detail.actions if a.kind == "validate")
    assert val_action.available is False
    assert "Blocked: prerequisite 'step-1' must be applied first" in val_action.reason
