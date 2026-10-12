"""Host proposal and operation tool registration, with launcher-owned authorization."""

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.application.host_proposals import HostProposalService, opaque_id
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.host_workflow import (
    AnalysisProposal,
    EvidenceCitation,
    EvidenceExcerpt,
    Operation,
    OperationView,
    PlanProposal,
    RepairProposal,
    StepStatus,
    WorkflowRecord,
    workflow_diagnostic_digest,
)
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.workflow_access import (
    WorkflowCapability,
    WorkflowContext,
    authorize_workflow,
)


def register_host_tools(
    server: MCPServer,
    binding: ProjectBinding,
    service: HostProposalService,
    context: WorkflowContext,
) -> None:
    def permit(project_id: str, capability: WorkflowCapability) -> None:
        try:
            binding.validate_project_id(project_id)
            authorize_workflow(context, capability)
            service.authorization.require(str(capability))
        except ValueError as error:
            raise ToolError(RedactionPolicy().redact_text(str(error))[:512]) from None

    @server.tool(name="migration_evidence_read")
    def evidence_read(
        project_id: str, evidence_refs: list[EvidenceCitation], lines: int = 100
    ) -> list[EvidenceExcerpt]:
        """Read bounded source evidence, verifying inventory digests and cited symbols."""
        permit(project_id, WorkflowCapability.EVIDENCE_READ)
        try:
            return list(service.read_evidence(tuple(evidence_refs), lines))
        except ValueError as error:
            raise ToolError(str(error)) from None

    @server.tool(name="migration_submit_analysis")
    def submit_analysis(
        project_id: str, request_id: str, analysis_payload: AnalysisProposal
    ) -> Operation:
        """Validate host analysis against source evidence and save outside the repository."""
        permit(project_id, WorkflowCapability.ANALYSIS_SUBMIT)
        return service.submit_analysis(request_id, analysis_payload)

    @server.tool(name="migration_submit_plan_proposal")
    def submit_plan(project_id: str, request_id: str, plan_payload: PlanProposal) -> Operation:
        """Validate grounded scope, policy, evidence, and DAG before minting a plan."""
        permit(project_id, WorkflowCapability.PLAN_SUBMIT)
        return service.submit_plan(request_id, plan_payload)

    @server.tool(name="migration_submit_repair_proposal")
    def submit_repair(
        project_id: str, request_id: str, repair_payload: RepairProposal
    ) -> Operation:
        """Validate repair scope and recorded diagnostics; invalidate earlier approval."""
        permit(project_id, WorkflowCapability.REPAIR_SUBMIT)
        return service.submit_repair(request_id, repair_payload)

    @server.tool(name="migration_operation_status")
    def operation_status(project_id: str, operation_id: str) -> OperationView:
        """Return a durable, project-scoped operation handle and bounded result."""
        permit(project_id, WorkflowCapability.OPERATION_READ)
        operation = service.store.get_operation(project_id, opaque_id(operation_id))
        records = [
            record
            for record in service.store.list_workflows(project_id)
            if record.plan_id == operation.plan_id
        ]

        def execution_status(record: WorkflowRecord) -> tuple[str, str | None]:
            if not record.validation_digest:
                return "unsupported", None
            from typing import cast

            from migration_agent.ports.apply_approval import ApprovalStorePort

            execution = cast(ApprovalStorePort, service.store).get_validation_execution(
                record.validation_digest
            )
            if execution.provenance is None:
                return "unsupported", None
            return execution.provenance.backend.value, execution.provenance.consent_id

        return OperationView(
            operation=operation,
            repository=service.evidence.repository_state(),
            steps=tuple(
                StepStatus(
                    step_id=record.step_id,
                    state=record.state,
                    transferable=record.transferable,
                    changeset_id=record.changeset_id,
                    changeset_digest=record.changeset_digest,
                    validation_digest=record.validation_digest,
                    validation_backend=execution_status(record)[0],
                    native_consent_id=execution_status(record)[1],
                    diagnostic_digest=workflow_diagnostic_digest(record),
                    browser_status=record.browser_evidence.status
                    if record.browser_evidence
                    else "NOT_RUN",
                    browser_capture_id=record.browser_evidence.capture.capture_id
                    if record.browser_evidence
                    else None,
                    e2e_status=record.browser_evidence.e2e_status
                    if record.browser_evidence
                    else "NOT_RUN",
                    diagnostics=tuple(
                        diagnostic[:512]
                        for result in record.validation_results
                        for diagnostic in result.diagnostics
                    )[:10],
                )
                for record in records
            ),
        )

    @server.tool(name="migration_operation_cancel")
    def operation_cancel(project_id: str, operation_id: str, request_id: str) -> Operation:
        """Request cancellation at a safe boundary; apply cannot cancel while writing."""
        permit(project_id, WorkflowCapability.OPERATION_CANCEL)
        target = opaque_id(operation_id)
        opaque_id(request_id)
        import uuid

        from migration_agent.domain.host_workflow import OperationStatus

        operation, claimed = service.store.claim_request(
            Operation(
                operation_id=f"op-{uuid.uuid4().hex}",
                project_id=project_id,
                request_id=request_id,
                kind="cancel",
                actor=context.actor,
                payload_digest=compute_canonical_digest(target),
            )
        )
        if claimed:
            result = service.store.cancel_operation(project_id, target)
            operation = operation.model_copy(
                update={"status": OperationStatus.SUCCEEDED, "message": result.status.value}
            )
            service.store.save_operation(operation)
        return operation
