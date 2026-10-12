"""GUI dispatch shares the exact apply service; fixture approval is not an HTTP tool."""

import base64
import hashlib
import time

import pytest
from test_shared_apply import HumanFixture, validated
from test_shared_apply import workflow as workflow

from migration_agent.adapters.project_work import ProjectWorkRead, attach_project_work, rollup_work
from migration_agent.adapters.workbench import CanonicalWorkbench, task_id
from migration_agent.application.workbench import WorkbenchService, WorkCommand
from migration_agent.domain.browser_validation import (
    BrowserCapture,
    BrowserEvidence,
    BrowserImage,
    Viewport,
)
from migration_agent.domain.host_workflow import OperationStatus
from migration_agent.domain.inspection_access import InspectionCapability, InspectionContext
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.project_work import ProjectWorkDefinition
from migration_agent.domain.workflow_access import WorkflowCapability, WorkflowContext


def test_gui_exact_apply_and_retry_use_shared_guarded_service(workflow) -> None:
    runtime, plan, step = workflow
    record = validated(workflow)
    before_approval = CanonicalWorkbench(
        runtime.binding.project_root,
        runtime.settings,
        WorkflowContext(
            actor=runtime.proposals.actor,
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(WorkflowCapability),
        ),
    )
    assert service_attention(before_approval) == {task_id(plan, step)}
    runtime.apply_service.approve(plan, step, HumanFixture())
    source = CanonicalWorkbench(
        runtime.binding.project_root,
        runtime.settings,
        WorkflowContext(
            actor=runtime.proposals.actor,
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(WorkflowCapability),
        ),
    )
    source.runtime = runtime
    source.authorization = runtime.authorization
    api = WorkbenchService(
        source,
        InspectionContext(
            actor=runtime.proposals.actor,
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(InspectionCapability),
        ),
    )
    snap = api.snapshot()
    detail = api.detail(snap.project_id, task_id(plan, step), snap.revision)
    assert dict(detail.milestones)["Human decision"] == "APPROVAL_RECORDED"
    assert "--trust-root" in detail.review_command
    command = WorkCommand(
        project_id=snap.project_id,
        node_id=task_id(plan, step),
        expected_revision=snap.revision,
        request_id="gui-exact-apply",
        kind="apply",
        changeset_id=record.changeset_id,
    )
    first = api.dispatch(command)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        operation = runtime.store.get_operation(snap.project_id, first.operation_id)
        if operation.status not in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
            break
        time.sleep(0.02)
    assert operation.status == OperationStatus.SUCCEEDED, operation.message
    assert api.snapshot().nodes[0].complete_count == 1
    assert next(n for n in api.snapshot().nodes if n.node_id == "work").status == "APPLY_COMPLETED"
    definition = ProjectWorkDefinition.model_validate(
        {
            "items": [
                {"item_id": "module", "kind": "group", "title": "Generic module"},
                {"item_id": "feature", "parent_id": "module", "kind": "group", "title": "Feature"},
                {
                    "item_id": "task",
                    "parent_id": "feature",
                    "kind": "task",
                    "title": "Evidence-linked task",
                    "workflow": {"workflow_id": plan, "task_id": step},
                },
            ]
        }
    )
    projected = rollup_work(
        attach_project_work(list(api.snapshot().nodes), ProjectWorkRead(definition), task_id)
    )
    assert next(node for node in projected if node.node_id == "work-module").complete_count == 1
    assert next(node for node in projected if node.node_id == "work-feature").complete_count == 1
    again = api.dispatch(command)
    assert again.operation_id == first.operation_id
    with pytest.raises(ValueError, match="ACTION_UNAVAILABLE"):
        api.dispatch(
            command.model_copy(
                update={"request_id": "new-request", "expected_revision": api.snapshot().revision}
            )
        )


def service_attention(source: CanonicalWorkbench) -> set[str]:
    api = WorkbenchService(
        source,
        InspectionContext(
            actor=source.context.actor,
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(InspectionCapability),
        ),
    )
    return {n.node_id for n in api.page(source.binding.project_id, None, attention=True).nodes}


def test_gui_image_checks_capture_scope_and_exact_bytes(workflow) -> None:
    runtime, plan, step = workflow
    record = validated(workflow)
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII="
    )
    capture = BrowserCapture(
        capture_id="browser-" + "a" * 32,
        project_id=record.project_id,
        plan_id=plan,
        step_id=step,
        changeset_digest=record.changeset_digest,
        source_revision=record.base_revision,
        config_digest="fixture",
        build_digest="fixture",
        tool_digest="fixture",
        browser_version="fixture",
        cleanup_verified=True,
        images=(
            BrowserImage(
                case_key="fixture",
                origin="target",
                filename="capture.png",
                sha256=hashlib.sha256(data).hexdigest(),
                viewport=Viewport(id="fixture", width=240, height=240),
            ),
        ),
    )
    root = runtime.settings.resolve_state_dir() / "browser" / record.project_id / capture.capture_id
    root.mkdir(parents=True)
    image = root / "capture.png"
    image.write_bytes(data)
    lease = runtime.store.acquire_lease(record.project_id, "image-fixture", ttl=900)
    try:
        record = runtime.store.save_workflow(
            record.model_copy(
                update={
                    "browser_evidence": BrowserEvidence(status="REVIEW_REQUIRED", capture=capture)
                }
            ),
            lease,
        )
    finally:
        runtime.store.release_lease(lease)
    source = CanonicalWorkbench(
        runtime.binding.project_root,
        runtime.settings,
        WorkflowContext(
            actor=runtime.proposals.actor,
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(WorkflowCapability),
        ),
    )
    snapshot = source.snapshot()
    ident = task_id(plan, step)
    assert base64.b64decode(source.image(ident, snapshot.revision, 0).data) == data
    image.write_bytes(data[:-1] + b"x")
    with pytest.raises(ValueError, match="IMAGE_CHANGED"):
        source.image(ident, snapshot.revision, 0)
    image.write_bytes(data)
    lease = runtime.store.acquire_lease(record.project_id, "foreign-fixture", ttl=900)
    try:
        runtime.store.save_workflow(
            record.model_copy(
                update={
                    "browser_evidence": BrowserEvidence(
                        status="REVIEW_REQUIRED",
                        capture=capture.model_copy(update={"project_id": "foreign"}),
                    )
                }
            ),
            lease,
        )
    finally:
        runtime.store.release_lease(lease)
    with pytest.raises(ValueError, match="IMAGE_SCOPE_INVALID"):
        source.image(ident, source.snapshot().revision, 0)
