"""Guarded operation tools. Human approval is never exposed through MCP."""

import base64
import uuid

from mcp.server.mcpserver import MCPServer
from mcp.types import ImageContent
from pydantic import BaseModel, ConfigDict

from migration_agent.adapters.browser_validation import BrowserReviewRequest
from migration_agent.adapters.workflow_runtime import WorkflowRuntime
from migration_agent.domain.apply_approval import ReviewRequestPayload
from migration_agent.domain.browser_validation import BrowserReview
from migration_agent.domain.host_workflow import (
    ImplementationContext,
    ImplementationProposal,
    Lifecycle,
    Operation,
    OperationStatus,
)
from migration_agent.domain.workflow_access import (
    WorkflowCapability,
    WorkflowContext,
    authorize_workflow,
)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: Operation
    review: ReviewRequestPayload | None = None


def register_mutation_tools(
    server: MCPServer, runtime: WorkflowRuntime, context: WorkflowContext
) -> None:
    def permit(project_id: str, capability: WorkflowCapability) -> None:
        runtime.require_current_configuration()
        runtime.binding.validate_project_id(project_id)
        authorize_workflow(context, capability)
        runtime.authorization.require(str(capability))

    @server.tool(name="migration_step_stage")
    def stage(project_id: str, plan_id: str, step_id: str, request_id: str) -> Operation:
        """Stage a grounded plan step in isolation and return a durable handle."""
        permit(project_id, WorkflowCapability.STAGE)
        return runtime.dispatch("stage", plan_id, step_id, request_id)

    @server.tool(name="migration_submit_implementation")
    def implementation(
        project_id: str, request_id: str, proposal: ImplementationProposal
    ) -> Operation:
        """Submit grounded generated files for declared scope without granting approval."""
        permit(project_id, WorkflowCapability.STAGE)
        return runtime.apply_service.submit_implementation(request_id, proposal)

    @server.tool(name="migration_implementation_context")
    def implementation_context(
        project_id: str, plan_id: str, step_id: str
    ) -> ImplementationContext:
        """Read bounded grounded source and declared target base for host generation."""
        permit(project_id, WorkflowCapability.STAGE)
        lease = runtime.store.acquire_lease(project_id, "context-" + uuid.uuid4().hex)
        try:
            return runtime.apply_service.implementation_context(plan_id, step_id, lease)
        finally:
            runtime.store.release_lease(lease)

    @server.tool(name="migration_step_validate")
    def validate(
        project_id: str, plan_id: str, step_id: str, request_id: str, profile: str = "ALL"
    ) -> Operation:
        """Run configured staging checks; poll the durable operation handle."""
        permit(project_id, WorkflowCapability.VALIDATE)
        return runtime.dispatch("validate", plan_id, step_id, request_id, profile=profile)

    @server.tool(name="migration_request_approval")
    def request_review(
        project_id: str, plan_id: str, step_id: str, changeset_id: str, request_id: str
    ) -> ReviewResult:
        """Create an exact artifact review challenge for trusted CLI human confirmation."""
        permit(project_id, WorkflowCapability.APPROVAL_REQUEST)
        operation = runtime.dispatch(
            "review", plan_id, step_id, request_id, changeset_id, background=False
        )
        if operation.status != OperationStatus.SUCCEEDED:
            return ReviewResult(operation=operation)
        record = runtime.store.get_workflow(project_id, plan_id, step_id)
        if record.state != Lifecycle.APPROVAL_PENDING:
            return ReviewResult(operation=operation)
        lease = runtime.store.acquire_lease(project_id, f"review-view-{uuid.uuid4().hex}")
        try:
            return ReviewResult(
                operation=operation,
                review=runtime.apply_service.request_review(plan_id, step_id, changeset_id, lease),
            )
        finally:
            runtime.store.release_lease(lease)

    @server.tool(name="migration_step_apply")
    def apply(
        project_id: str, plan_id: str, step_id: str, changeset_id: str, request_id: str
    ) -> Operation:
        """Apply persisted human approval and PASSED validation under lock/fencing."""
        permit(project_id, WorkflowCapability.APPLY)
        return runtime.dispatch("apply", plan_id, step_id, request_id, changeset_id)

    @server.tool(name="migration_browser_review_request")
    def browser_request(project_id: str, plan_id: str, step_id: str) -> BrowserReviewRequest:
        """Get UI/UX specialist instructions, standards and verified screenshot references."""
        permit(project_id, WorkflowCapability.OPERATION_READ)
        record = runtime.store.get_workflow(project_id, plan_id, step_id)
        return runtime.browser_gate.request(record)

    @server.tool(name="migration_browser_screenshot")
    def browser_screenshot(
        project_id: str, capture_id: str, case_key: str, origin: str = "target"
    ) -> ImageContent:
        """Read one captured PNG for actual visual analysis; arbitrary files are never accepted."""
        permit(project_id, WorkflowCapability.OPERATION_READ)
        capture = runtime.store.get_browser_capture(project_id, capture_id)
        image = next(
            (
                image
                for image in capture.images
                if image.case_key == case_key and image.origin == origin
            ),
            None,
        )
        if image is None:
            raise ValueError("BROWSER_IMAGE_NOT_FOUND: select a captured case/origin.")
        data = runtime.browser_gate.image(capture, image)
        return ImageContent(
            type="image", mime_type="image/png", data=base64.b64encode(data).decode("ascii")
        )

    @server.tool(name="migration_browser_submit_review")
    def browser_submit(
        project_id: str, plan_id: str, step_id: str, request_id: str, review: BrowserReview
    ) -> Operation:
        """Record typed image-based review; rerun validation or repair before human approval."""
        permit(project_id, WorkflowCapability.VALIDATE)
        return runtime.submit_browser_review(plan_id, step_id, request_id, review)
