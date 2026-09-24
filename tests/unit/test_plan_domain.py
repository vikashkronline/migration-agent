"""Unit tests for migration plan domain models, digests, and approval invalidation."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from migration_agent.domain import (
    ApprovalSignature,
    AssuranceLevel,
    EvidenceReference,
    EvidenceStatus,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    StepRisk,
    compute_plan_digest,
    verify_approval,
)


def _sample_step(step_id: str = "step-001") -> MigrationStep:
    return MigrationStep(
        step_id=step_id,
        title="Migrate UserCard Component",
        description="Convert classic Ember component to modern Angular standalone component.",
        dependencies=[],
        scope="component",
        risk=StepRisk.MEDIUM,
        confidence=0.95,
        evidence=[
            EvidenceReference(
                path="app/components/user-card.js",
                description="Classic component definition",
                line_number=1,
                sample="Component.extend({",
                status=EvidenceStatus.VALID,
            )
        ],
        expected_files=["src/app/components/user-card.component.ts"],
        validation_strategy=["ng test --no-watch", "ng build"],
        rollback_note="Delete generated Angular component files.",
        acceptance_criteria=["Component compiles", "Tests pass"],
        unresolved_questions=[],
    )


def test_migration_step_is_frozen() -> None:
    step = _sample_step()
    with pytest.raises(ValidationError):
        step.title = "New Title"  # type: ignore[misc]


def test_migration_plan_is_frozen() -> None:
    plan = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-456",
        status=PlanStatus.DRAFT,
        steps=[_sample_step()],
        policy_digest="sha256:abcd",
    )
    with pytest.raises(ValidationError):
        plan.status = PlanStatus.APPROVED  # type: ignore[misc]


def test_compute_plan_digest_consistency() -> None:
    step = _sample_step()
    plan1 = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-456",
        status=PlanStatus.DRAFT,
        steps=[step],
        policy_digest="sha256:1111",
        created_at=datetime(2026, 9, 25, 0, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 9, 25, 0, 0, 0, tzinfo=UTC),
    )
    # Plan with different timestamps and status still produces identical content digest
    plan2 = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-456",
        status=PlanStatus.NEEDS_APPROVAL,
        steps=[step],
        policy_digest="sha256:1111",
        created_at=datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC),
    )
    assert compute_plan_digest(plan1) == compute_plan_digest(plan2)


def test_compute_plan_digest_changes_on_step_mutation() -> None:
    step1 = _sample_step("step-001")
    step2 = _sample_step("step-001").model_copy(
        update={"expected_files": ["src/app/components/user-card.component.ts", "extra.ts"]}
    )

    plan1 = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-456",
        status=PlanStatus.DRAFT,
        steps=[step1],
        policy_digest="sha256:1111",
    )
    plan2 = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-456",
        status=PlanStatus.DRAFT,
        steps=[step2],
        policy_digest="sha256:1111",
    )
    assert compute_plan_digest(plan1) != compute_plan_digest(plan2)


def test_verify_approval_success() -> None:
    step = _sample_step()
    policy_digest = "sha256:policy123"
    preliminary_plan = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-456",
        status=PlanStatus.NEEDS_APPROVAL,
        steps=[step],
        policy_digest=policy_digest,
    )
    plan_digest = compute_plan_digest(preliminary_plan)

    signature = ApprovalSignature(
        actor="lead-architect",
        plan_digest=plan_digest,
        policy_digest=policy_digest,
        signature="sig:lead-architect:valid",
        assurance_level=AssuranceLevel.MODE_B,
    )

    approved_plan = preliminary_plan.model_copy(
        update={"status": PlanStatus.APPROVED, "approval": signature}
    )

    assert verify_approval(approved_plan) is True
    assert verify_approval(approved_plan, active_policy_digest=policy_digest) is True


def test_verify_approval_invalidated_by_step_tampering() -> None:
    step = _sample_step()
    policy_digest = "sha256:policy123"
    plan = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-456",
        status=PlanStatus.NEEDS_APPROVAL,
        steps=[step],
        policy_digest=policy_digest,
    )
    plan_digest = compute_plan_digest(plan)

    signature = ApprovalSignature(
        actor="lead-architect",
        plan_digest=plan_digest,
        policy_digest=policy_digest,
        signature="sig:valid",
        assurance_level=AssuranceLevel.MODE_B,
    )

    approved_plan = plan.model_copy(update={"status": PlanStatus.APPROVED, "approval": signature})
    assert verify_approval(approved_plan) is True

    # Tamper with plan content by adding a step or altering a step
    tampered_step = step.model_copy(update={"validation_strategy": ["echo bypass"]})
    tampered_plan = approved_plan.model_copy(update={"steps": [tampered_step]})

    # Tampered plan digest will no longer match the approval signature!
    assert verify_approval(tampered_plan) is False


def test_verify_approval_invalidated_by_policy_change() -> None:
    step = _sample_step()
    initial_policy_digest = "sha256:initial"
    plan = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-456",
        status=PlanStatus.APPROVED,
        steps=[step],
        policy_digest=initial_policy_digest,
        approval=ApprovalSignature(
            actor="admin",
            plan_digest=compute_plan_digest(
                MigrationPlan(
                    plan_id="plan-123",
                    source_root="/repo",
                    run_id="run-456",
                    steps=[step],
                    policy_digest=initial_policy_digest,
                )
            ),
            policy_digest=initial_policy_digest,
            signature="sig:admin",
            assurance_level=AssuranceLevel.MODE_A,
        ),
    )

    # When active policy in repository changes to something new:
    new_policy_digest = "sha256:changed_policy"
    assert verify_approval(plan, active_policy_digest=new_policy_digest) is False
