"""Capabilities granted by a trusted local launcher for host workflows."""

from enum import StrEnum

from pydantic import ConfigDict

from migration_agent.domain.host_workflow import WorkflowModel
from migration_agent.domain.planning import AssuranceLevel


class WorkflowCapability(StrEnum):
    EVIDENCE_READ = "evidence.read"
    ANALYSIS_SUBMIT = "analysis.submit"
    PLAN_SUBMIT = "plan.submit"
    REPAIR_SUBMIT = "repair.submit"
    OPERATION_READ = "operation.read"
    OPERATION_CANCEL = "operation.cancel"
    STAGE = "changeset.stage"
    VALIDATE = "validation.run"
    APPROVAL_REQUEST = "approval.request"
    APPLY = "changeset.apply"


class WorkflowContext(WorkflowModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    actor: str
    assurance: AssuranceLevel
    capabilities: frozenset[WorkflowCapability]


def authorize_workflow(context: WorkflowContext, capability: WorkflowCapability) -> None:
    if capability not in context.capabilities:
        raise ValueError("CAPABILITY_DENIED: workflow capability is not granted.")
    if context.assurance == AssuranceLevel.MODE_C:
        raise ValueError("ASSURANCE_REQUIRED: a trusted local workflow session is required.")
