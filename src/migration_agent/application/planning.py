"""Application service for migration planning, validation, approvals, and state persistence."""

import uuid
from datetime import UTC, datetime

from migration_agent.application.validator import PlanValidationResult, RuleBasedPlanValidator
from migration_agent.domain import (
    AnalysisResult,
    ApprovalSignature,
    AssuranceLevel,
    MigrationPlan,
    PlanStatus,
    ProjectInventory,
    compute_plan_digest,
)
from migration_agent.ports import (
    AgentRuntimePort,
    AuditEvent,
    AuditLogPort,
    CheckpointPort,
    GovernancePort,
    OperationalCheckpoint,
    PlanningRequest,
)


class PlanningService:
    """Orchestrates migration plan generation, DAG validation, and storage tiering."""

    def __init__(
        self,
        runtime: AgentRuntimePort,
        checkpoint_store: CheckpointPort,
        audit_logger: AuditLogPort,
        governance: GovernancePort,
        validator: RuleBasedPlanValidator | None = None,
    ) -> None:
        self.runtime = runtime
        self.checkpoint_store = checkpoint_store
        self.audit_logger = audit_logger
        self.governance = governance
        self.validator = validator or RuleBasedPlanValidator()

    def create_plan(
        self,
        inventory: ProjectInventory,
        analysis: AnalysisResult,
        project_root: str,
        run_id: str | None = None,
        provider: str = "gemini",
        model: str = "gemini-2.5-pro",
        max_turns: int = 10,
        dry_run: bool = True,
    ) -> tuple[MigrationPlan, PlanValidationResult]:
        """Generate, validate, and persist a new migration plan."""
        self.governance.ensure_governance_layout(project_root)
        policy_digest = self.governance.get_policy_digest(project_root)

        # Generate candidate steps from agent runtime
        raw_steps = self.runtime.plan(
            PlanningRequest(
                inventory=inventory,
                analysis=analysis,
                provider=provider,
                model=model,
                max_turns=max_turns,
                dry_run=dry_run,
            )
        )

        # Attempt topological sort on valid steps
        try:
            sorted_steps = self.validator.topological_sort(raw_steps)
        except ValueError:
            sorted_steps = raw_steps

        active_run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"

        preliminary_plan = MigrationPlan(
            plan_id=plan_id,
            source_root=project_root,
            run_id=active_run_id,
            status=PlanStatus.DRAFT,
            steps=sorted_steps,
            policy_digest=policy_digest,
        )

        validation = self.validator.validate(preliminary_plan, inventory)

        initial_status = PlanStatus.NEEDS_APPROVAL if validation.is_valid else PlanStatus.DRAFT

        plan = MigrationPlan(
            plan_id=preliminary_plan.plan_id,
            source_root=preliminary_plan.source_root,
            run_id=preliminary_plan.run_id,
            status=initial_status,
            steps=preliminary_plan.steps,
            policy_digest=preliminary_plan.policy_digest,
            created_at=preliminary_plan.created_at,
            updated_at=datetime.now(UTC),
        )

        # Persist across Tier 1 (Git .agent/), Tier 2 (SQLite), and Tier 3 (JSONL)
        self.checkpoint_store.save_plan(plan)
        self.governance.export_plan(project_root, plan)

        self.audit_logger.record_event(
            AuditEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                run_id=plan.run_id,
                event_type="PLAN_CREATED",
                actor="agent",
                payload={
                    "plan_id": plan.plan_id,
                    "status": plan.status.value,
                    "step_count": len(plan.steps),
                    "plan_digest": compute_plan_digest(plan),
                    "policy_digest": plan.policy_digest,
                    "is_valid": validation.is_valid,
                    "errors": validation.errors,
                    "warnings": validation.warnings,
                },
            )
        )

        self.checkpoint_store.save_checkpoint(
            OperationalCheckpoint(
                checkpoint_id=f"chk-{uuid.uuid4().hex[:8]}",
                run_id=plan.run_id,
                checkpoint_type="PLAN_GENERATED",
                state_data={
                    "plan_id": plan.plan_id,
                    "status": plan.status.value,
                    "step_count": len(plan.steps),
                },
            )
        )

        return plan, validation

    def approve_plan(
        self,
        plan_id: str,
        actor: str,
        assurance_level: AssuranceLevel = AssuranceLevel.MODE_B,
        project_root: str | None = None,
    ) -> MigrationPlan:
        """Sign and approve a migration plan with cryptographic digest binding."""
        plan = self.get_plan(plan_id, project_root=project_root)
        if plan is None:
            raise ValueError(f"Plan '{plan_id}' not found.")

        current_digest = compute_plan_digest(plan)
        target_root = project_root or plan.source_root
        active_policy_digest = self.governance.get_policy_digest(target_root)

        signature = ApprovalSignature(
            actor=actor,
            plan_digest=current_digest,
            policy_digest=active_policy_digest,
            signature=f"sig:{actor}:{current_digest[7:19]}",
            assurance_level=assurance_level,
        )

        approved_plan = MigrationPlan(
            plan_id=plan.plan_id,
            source_root=plan.source_root,
            run_id=plan.run_id,
            status=PlanStatus.APPROVED,
            steps=plan.steps,
            approval=signature,
            policy_digest=active_policy_digest,
            rejection_reason=None,
            created_at=plan.created_at,
            updated_at=datetime.now(UTC),
        )

        self.checkpoint_store.save_plan(approved_plan)
        self.checkpoint_store.save_approval(plan_id, signature)
        self.governance.export_plan(target_root, approved_plan)

        self.audit_logger.record_event(
            AuditEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                run_id=approved_plan.run_id,
                event_type="PLAN_APPROVED",
                actor=actor,
                payload={
                    "plan_id": approved_plan.plan_id,
                    "plan_digest": current_digest,
                    "policy_digest": active_policy_digest,
                    "assurance_level": assurance_level.value,
                },
            )
        )

        self.checkpoint_store.save_checkpoint(
            OperationalCheckpoint(
                checkpoint_id=f"chk-{uuid.uuid4().hex[:8]}",
                run_id=approved_plan.run_id,
                checkpoint_type="PLAN_APPROVED",
                state_data={
                    "plan_id": approved_plan.plan_id,
                    "actor": actor,
                    "plan_digest": current_digest,
                },
            )
        )

        return approved_plan

    def reject_plan(
        self,
        plan_id: str,
        reason: str,
        actor: str = "user",
        project_root: str | None = None,
    ) -> MigrationPlan:
        """Reject a migration plan and record the human rejection reason."""
        plan = self.get_plan(plan_id, project_root=project_root)
        if plan is None:
            raise ValueError(f"Plan '{plan_id}' not found.")

        target_root = project_root or plan.source_root
        rejected_plan = MigrationPlan(
            plan_id=plan.plan_id,
            source_root=plan.source_root,
            run_id=plan.run_id,
            status=PlanStatus.REJECTED,
            steps=plan.steps,
            approval=None,
            policy_digest=plan.policy_digest,
            rejection_reason=reason,
            created_at=plan.created_at,
            updated_at=datetime.now(UTC),
        )

        self.checkpoint_store.save_plan(rejected_plan)
        self.governance.export_plan(target_root, rejected_plan)

        self.audit_logger.record_event(
            AuditEvent(
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                run_id=rejected_plan.run_id,
                event_type="PLAN_REJECTED",
                actor=actor,
                payload={
                    "plan_id": rejected_plan.plan_id,
                    "rejection_reason": reason,
                },
            )
        )

        self.checkpoint_store.save_checkpoint(
            OperationalCheckpoint(
                checkpoint_id=f"chk-{uuid.uuid4().hex[:8]}",
                run_id=rejected_plan.run_id,
                checkpoint_type="PLAN_REJECTED",
                state_data={
                    "plan_id": rejected_plan.plan_id,
                    "actor": actor,
                    "reason": reason,
                },
            )
        )

        return rejected_plan

    def get_plan(
        self,
        plan_id: str,
        project_root: str | None = None,
    ) -> MigrationPlan | None:
        """Fetch plan from canonical SQLite database, falling back to Git governance."""
        plan = self.checkpoint_store.get_plan(plan_id)
        if plan is not None:
            return plan

        if project_root:
            return self.governance.load_plan(project_root, plan_id)

        return None
