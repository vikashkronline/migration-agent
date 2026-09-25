"""Application coordinator and deterministic aggregators for specialist subagents."""

import time
import uuid

from migration_agent.domain import (
    FindingSeverity,
    InventoryInterpretation,
    InventoryInterpretationRequest,
    MigrationAnalysisOutput,
    MigrationAnalystRequest,
    MigrationPlan,
    PlanCriticRequest,
    PlanCritique,
    RepairDiagnosis,
    RepairDiagnosticianRequest,
    SpecialistRole,
    StepRisk,
    SubagentUsageRecord,
)
from migration_agent.domain.specialists import BudgetTracker
from migration_agent.ports import (
    AuditEvent,
    AuditLogPort,
    FileReaderPort,
    SpecialistRuntimePort,
)


class SpecialistCoordinator:
    """Coordinates invocation of specialized subagents under unified turn and cost budgets."""

    def __init__(
        self,
        runtime: SpecialistRuntimePort,
        audit_logger: AuditLogPort | None = None,
        budget_tracker: BudgetTracker | None = None,
    ) -> None:
        self.runtime = runtime
        self.audit_logger = audit_logger
        self.budget_tracker = budget_tracker or BudgetTracker()

    def interpret_inventory(
        self,
        request: InventoryInterpretationRequest,
        run_id: str = "run-specialist",
    ) -> InventoryInterpretation | None:
        """Execute the Inventory Interpreter subagent within budget constraints."""
        role = SpecialistRole.INVENTORY_INTERPRETER
        if not self.budget_tracker.can_invoke(role):
            self._record_budget_exceeded(run_id, role)
            return None

        start_time = time.monotonic()
        self._record_event(
            run_id,
            "SPECIALIST_INVOKED",
            {"role": role.value, "repository": request.inventory.repository.name},
        )

        try:
            result = self.runtime.interpret_inventory(request)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self.budget_tracker.record_usage(
                SubagentUsageRecord(
                    role=role,
                    turns_used=1,
                    prompt_tokens=400,
                    completion_tokens=250,
                    estimated_cost_usd=0.003,
                    duration_ms=duration_ms,
                )
            )
            self._record_event(
                run_id,
                "SPECIALIST_COMPLETED",
                {
                    "role": role.value,
                    "duration_ms": duration_ms,
                    "risks_identified": len(result.key_risks),
                },
            )
            return result
        except Exception as exc:
            self._record_event(
                run_id,
                "SPECIALIST_FAILED",
                {"role": role.value, "error": str(exc)},
            )
            raise

    def analyze_migration(
        self,
        request: MigrationAnalystRequest,
        file_reader: FileReaderPort,
        run_id: str = "run-specialist",
    ) -> MigrationAnalysisOutput | None:
        """Execute the Migration Analyst subagent within budget constraints."""
        role = SpecialistRole.MIGRATION_ANALYST
        if not self.budget_tracker.can_invoke(role):
            self._record_budget_exceeded(run_id, role)
            return None

        start_time = time.monotonic()
        self._record_event(
            run_id,
            "SPECIALIST_INVOKED",
            {"role": role.value, "repository": request.inventory.repository.name},
        )

        try:
            result = self.runtime.analyze_migration(request, file_reader)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self.budget_tracker.record_usage(
                SubagentUsageRecord(
                    role=role,
                    turns_used=1,
                    prompt_tokens=1200,
                    completion_tokens=600,
                    estimated_cost_usd=0.008,
                    duration_ms=duration_ms,
                )
            )
            self._record_event(
                run_id,
                "SPECIALIST_COMPLETED",
                {
                    "role": role.value,
                    "duration_ms": duration_ms,
                    "findings_count": len(result.findings),
                },
            )
            return result
        except Exception as exc:
            self._record_event(
                run_id,
                "SPECIALIST_FAILED",
                {"role": role.value, "error": str(exc)},
            )
            raise

    def criticize_plan(
        self,
        request: PlanCriticRequest,
        run_id: str = "run-specialist",
    ) -> PlanCritique | None:
        """Execute the Plan Critic subagent within budget constraints."""
        role = SpecialistRole.PLAN_CRITIC
        if not self.budget_tracker.can_invoke(role):
            self._record_budget_exceeded(run_id, role)
            return None

        start_time = time.monotonic()
        self._record_event(
            run_id,
            "SPECIALIST_INVOKED",
            {"role": role.value, "plan_id": request.plan.plan_id},
        )

        try:
            result = self.runtime.criticize_plan(request)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self.budget_tracker.record_usage(
                SubagentUsageRecord(
                    role=role,
                    turns_used=1,
                    prompt_tokens=800,
                    completion_tokens=300,
                    estimated_cost_usd=0.005,
                    duration_ms=duration_ms,
                )
            )
            self._record_event(
                run_id,
                "SPECIALIST_COMPLETED",
                {
                    "role": role.value,
                    "duration_ms": duration_ms,
                    "overall_score": result.overall_score,
                    "approval_recommended": result.approval_recommended,
                },
            )
            return result
        except Exception as exc:
            self._record_event(
                run_id,
                "SPECIALIST_FAILED",
                {"role": role.value, "error": str(exc)},
            )
            raise

    def diagnose_repair(
        self,
        request: RepairDiagnosticianRequest,
        run_id: str = "run-specialist",
    ) -> RepairDiagnosis | None:
        """Execute the Repair Diagnostician subagent within budget constraints."""
        role = SpecialistRole.REPAIR_DIAGNOSTICIAN
        if not self.budget_tracker.can_invoke(role):
            self._record_budget_exceeded(run_id, role)
            return None

        start_time = time.monotonic()
        self._record_event(
            run_id,
            "SPECIALIST_INVOKED",
            {"role": role.value, "command": request.failing_result.command},
        )

        try:
            result = self.runtime.diagnose_repair(request)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self.budget_tracker.record_usage(
                SubagentUsageRecord(
                    role=role,
                    turns_used=1,
                    prompt_tokens=600,
                    completion_tokens=200,
                    estimated_cost_usd=0.004,
                    duration_ms=duration_ms,
                )
            )
            self._record_event(
                run_id,
                "SPECIALIST_COMPLETED",
                {
                    "role": role.value,
                    "duration_ms": duration_ms,
                    "actionable": result.actionable,
                    "suggested_file": result.suggested_file,
                },
            )
            return result
        except Exception as exc:
            self._record_event(
                run_id,
                "SPECIALIST_FAILED",
                {"role": role.value, "error": str(exc)},
            )
            raise

    def _record_event(self, run_id: str, event_type: str, payload: dict[str, object]) -> None:
        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-sp-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type=event_type,
                    actor="specialist_coordinator",
                    payload=payload,
                )
            )

    def _record_budget_exceeded(self, run_id: str, role: SpecialistRole) -> None:
        summary = self.budget_tracker.get_summary()
        self._record_event(
            run_id,
            "SPECIALIST_BUDGET_EXCEEDED",
            {
                "role": role.value,
                "total_turns": summary.total_turns,
                "total_cost_usd": summary.total_cost_usd,
                "reason": summary.exhaustion_reason or "limit reached",
            },
        )


class DeterministicPlanCriticAggregator:
    """Applies plan critic audits to migration plans without altering DAG topology."""

    @staticmethod
    def aggregate_critique(
        plan: MigrationPlan,
        critique: PlanCritique,
    ) -> tuple[MigrationPlan, bool, list[str]]:
        """Evaluate plan critique points, deterministically escalating step risks where appropriate.

        Returns:
            Tuple of (updated_plan, approval_recommended, list_of_critique_notes).
        """
        notes: list[str] = [critique.summary] if critique.summary else []
        high_risk_step_ids = set(critique.flagged_step_ids)

        for point in critique.critique_points:
            notes.append(f"[{point.severity.value.upper()}] {point.category}: {point.critique}")
            if point.step_id and point.severity in (FindingSeverity.HIGH, FindingSeverity.CRITICAL):
                high_risk_step_ids.add(point.step_id)

        # Update step risks deterministically
        updated_steps = []
        any_modified = False
        for step in plan.steps:
            if step.step_id in high_risk_step_ids and step.risk != StepRisk.HIGH:
                updated_steps.append(step.model_copy(update={"risk": StepRisk.HIGH}))
                any_modified = True
            else:
                updated_steps.append(step)

        updated_plan = plan.model_copy(update={"steps": updated_steps}) if any_modified else plan
        effective_approval = critique.approval_recommended and critique.overall_score >= 0.70
        return updated_plan, effective_approval, notes


class DeterministicRepairDiagnosticianAggregator:
    """Enforces Invariant 26 allowed_scope boundaries on repair diagnostician outputs."""

    @staticmethod
    def aggregate_diagnosis(
        diagnosis: RepairDiagnosis,
        allowed_scope: tuple[str, ...],
    ) -> tuple[bool, str | None, str]:
        """Validate diagnosis against allowed_scope.

        Returns:
            Tuple of (is_actionable, verified_suggested_file, diagnostic_details).
        """
        if not diagnosis.actionable or not diagnosis.suggested_file:
            return False, None, diagnosis.diagnostic_details

        # Invariant 26 Scope Enforcement
        if diagnosis.suggested_file not in allowed_scope:
            rejected_msg = (
                f"Diagnostic recommendation rejected: suggested file '{diagnosis.suggested_file}' "
                f"is outside approved scope ({list(allowed_scope)})."
            )
            return False, None, rejected_msg

        return True, diagnosis.suggested_file, diagnosis.suggested_fix_summary
