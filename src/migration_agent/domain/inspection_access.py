"""Capabilities and trusted execution context for repository inspection."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.planning import AssuranceLevel


class InspectionCapability(StrEnum):
    DIAGNOSTICS = "system.diagnostics"
    PROJECT_READ = "project.read"
    RUN_READ = "run.read"
    PLAN_READ = "plan.read"
    CHANGESET_READ = "changeset.read"


class InspectionContext(BaseModel):
    """Resolved by a trusted local launcher, never by tool arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: str = Field(min_length=1)
    assurance: AssuranceLevel
    capabilities: frozenset[InspectionCapability]


def authorize_inspection(context: InspectionContext, capability: InspectionCapability) -> None:
    """Enforce the inspection-only capability and minimum-assurance policy."""
    if capability not in context.capabilities:
        raise ValueError("CAPABILITY_DENIED: inspection capability is not granted.")
    public = {InspectionCapability.DIAGNOSTICS, InspectionCapability.PROJECT_READ}
    if capability not in public and context.assurance == AssuranceLevel.MODE_C:
        raise ValueError("ASSURANCE_REQUIRED: trusted local inspection session required.")
