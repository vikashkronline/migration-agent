"""Domain entities for migration plans, step execution, and approval signatures."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.analysis import EvidenceReference
from migration_agent.domain.canonical import compute_canonical_digest


class PlanStatus(StrEnum):
    """Lifecycle state of a migration plan."""

    DRAFT = "DRAFT"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class StepRisk(StrEnum):
    """Risk classification for an individual migration step."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AssuranceLevel(StrEnum):
    """Assurance level for actor identity and approvals per ADR-2."""

    MODE_A = "MODE_A"  # Cryptographically verified (SSH/GPG)
    MODE_B = "MODE_B"  # Local trusted session
    MODE_C = "MODE_C"  # Unauthenticated / inspection only


class MigrationStep(BaseModel):
    """Immutable, typed migration step representing one discrete transformation unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    scope: str = Field(default="component", min_length=1)
    risk: StepRisk = StepRisk.MEDIUM
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    expected_files: list[str] = Field(default_factory=list)
    validation_strategy: list[str] = Field(default_factory=list)
    rollback_note: str = Field(default="")
    acceptance_criteria: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)


class ApprovalSignature(BaseModel):
    """ADR-2 Cryptographic approval record binding actor, plan digest, and policy digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: str = Field(min_length=1)
    plan_digest: str = Field(min_length=1)
    policy_digest: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    signature: str = Field(min_length=1)
    assurance_level: AssuranceLevel = AssuranceLevel.MODE_B


class MigrationPlan(BaseModel):
    """Complete, ordered migration plan governing code transformation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(min_length=1)
    source_root: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: PlanStatus = PlanStatus.DRAFT
    steps: list[MigrationStep] = Field(default_factory=list)
    approval: ApprovalSignature | None = None
    policy_digest: str = Field(default="")
    rejection_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def canonical_step_payload(step: MigrationStep) -> dict[str, Any]:
    """Extract deterministic, canonical payload of a step for digest computation."""
    return {
        "step_id": step.step_id,
        "title": step.title,
        "description": step.description,
        "dependencies": sorted(step.dependencies),
        "scope": step.scope,
        "risk": step.risk.value,
        "confidence": round(step.confidence, 4),
        "evidence": [
            {
                "path": ev.path,
                "line_number": ev.line_number,
                "sample": ev.sample,
                "status": ev.status.value,
            }
            for ev in sorted(step.evidence, key=lambda e: (e.path, e.line_number or 0))
        ],
        "expected_files": sorted(step.expected_files),
        "validation_strategy": sorted(step.validation_strategy),
        "rollback_note": step.rollback_note,
        "acceptance_criteria": sorted(step.acceptance_criteria),
        "unresolved_questions": sorted(step.unresolved_questions),
    }


def compute_plan_digest(plan: MigrationPlan) -> str:
    """Calculate the RFC 8785 canonical content digest of a migration plan.

    Excludes volatile timestamps, status, rejection reason, and the approval signature
    itself, binding solely to plan ID, source root, run ID, policy digest, and steps.
    Any modification to the steps or plan intent invalidates matching approvals.
    """
    canonical_payload = {
        "plan_id": plan.plan_id,
        "source_root": plan.source_root,
        "run_id": plan.run_id,
        "policy_digest": plan.policy_digest,
        "steps": [canonical_step_payload(step) for step in plan.steps],
    }
    return compute_canonical_digest(canonical_payload)


def verify_approval(
    plan: MigrationPlan,
    active_policy_digest: str | None = None,
) -> bool:
    """Verify that a plan's approval signature is cryptographically valid and bound.

    Checks:
    1. Plan is in APPROVED status with non-null approval.
    2. Approval's plan_digest matches current computed RFC 8785 plan digest.
    3. If active_policy_digest is supplied, approval's policy_digest matches it.
    """
    if plan.status != PlanStatus.APPROVED or plan.approval is None:
        return False

    current_digest = compute_plan_digest(plan)
    if plan.approval.plan_digest != current_digest:
        return False

    if active_policy_digest is not None:
        return plan.approval.policy_digest == active_policy_digest

    return True
