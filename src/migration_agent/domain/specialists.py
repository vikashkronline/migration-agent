"""Domain models, typed contracts, and budget management for specialist subagents."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.analysis import (
    AnalysisFinding,
    AnalysisResult,
    FindingSeverity,
)
from migration_agent.domain.changeset import ChangeSet
from migration_agent.domain.inventory import ProjectInventory
from migration_agent.domain.planning import MigrationPlan
from migration_agent.domain.validation import RepairAttempt, ValidationResult


class SpecialistRole(StrEnum):
    """Canonical identifier for specialized subagent personas."""

    INVENTORY_INTERPRETER = "inventory_interpreter"
    MIGRATION_ANALYST = "migration_analyst"
    PLAN_CRITIC = "plan_critic"
    REPAIR_DIAGNOSTICIAN = "repair_diagnostician"


class BudgetExhaustedError(RuntimeError):
    """Raised when a subagent invocation exceeds configured turn, token, or cost budgets."""


class BudgetLimit(BaseModel):
    """Global and per-role turn and cost budget limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_total_turns: int = Field(default=30, ge=1)
    max_turns_per_role: dict[str, int] = Field(
        default_factory=lambda: {
            SpecialistRole.INVENTORY_INTERPRETER.value: 5,
            SpecialistRole.MIGRATION_ANALYST.value: 15,
            SpecialistRole.PLAN_CRITIC.value: 5,
            SpecialistRole.REPAIR_DIAGNOSTICIAN.value: 5,
        }
    )
    max_total_cost_usd: float = Field(default=2.0, ge=0.0)
    max_total_tokens: int = Field(default=150_000, ge=1)


class SubagentUsageRecord(BaseModel):
    """Execution telemetry recorded for a single subagent interaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: SpecialistRole
    turns_used: int = Field(ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    duration_ms: int = Field(default=0, ge=0)


class BudgetSummary(BaseModel):
    """Snapshot summary of aggregated subagent resource usage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_turns: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    total_cost_usd: float = Field(ge=0.0)
    is_exhausted: bool = False
    exhaustion_reason: str | None = None
    usage_by_role: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BudgetTracker:
    """Stateful tracker enforcing turn, token, and cost boundaries across specialist agents."""

    def __init__(self, limits: BudgetLimit | None = None) -> None:
        self.limits = limits or BudgetLimit()
        self._records: list[SubagentUsageRecord] = []
        self._total_turns = 0
        self._total_tokens = 0
        self._total_cost_usd = 0.0
        self._turns_by_role: dict[str, int] = {}
        self._is_exhausted = False
        self._exhaustion_reason: str | None = None

    def can_invoke(self, role: SpecialistRole, required_turns: int = 1) -> bool:
        """Check whether invoking the specified role would violate any budget limit."""
        if self._is_exhausted:
            return False

        if (self._total_turns + required_turns) > self.limits.max_total_turns:
            return False

        role_key = role.value
        current_role_turns = self._turns_by_role.get(role_key, 0)
        role_limit = self.limits.max_turns_per_role.get(role_key, self.limits.max_total_turns)
        if (current_role_turns + required_turns) > role_limit:
            return False

        if self._total_cost_usd >= self.limits.max_total_cost_usd:
            return False

        return self._total_tokens < self.limits.max_total_tokens

    def check_budget(self, role: SpecialistRole, required_turns: int = 1) -> None:
        """Assert budget sufficiency, raising BudgetExhaustedError if limits are breached."""
        if self._is_exhausted:
            raise BudgetExhaustedError(
                f"Budget already exhausted: {self._exhaustion_reason or 'limit exceeded'}."
            )

        if (self._total_turns + required_turns) > self.limits.max_total_turns:
            self._is_exhausted = True
            self._exhaustion_reason = (
                f"Total turn budget exceeded ({self._total_turns + required_turns} > "
                f"{self.limits.max_total_turns})"
            )
            raise BudgetExhaustedError(self._exhaustion_reason)

        role_key = role.value
        current_role_turns = self._turns_by_role.get(role_key, 0)
        role_limit = self.limits.max_turns_per_role.get(role_key, self.limits.max_total_turns)
        if (current_role_turns + required_turns) > role_limit:
            self._is_exhausted = True
            self._exhaustion_reason = (
                f"Role '{role_key}' turn budget exceeded "
                f"({current_role_turns + required_turns} > {role_limit})"
            )
            raise BudgetExhaustedError(self._exhaustion_reason)

        if self._total_cost_usd >= self.limits.max_total_cost_usd:
            self._is_exhausted = True
            self._exhaustion_reason = (
                f"Total cost budget exceeded (${self._total_cost_usd:.4f} >= "
                f"${self.limits.max_total_cost_usd:.2f})"
            )
            raise BudgetExhaustedError(self._exhaustion_reason)

        if self._total_tokens >= self.limits.max_total_tokens:
            self._is_exhausted = True
            self._exhaustion_reason = (
                f"Total token budget exceeded ({self._total_tokens} >= "
                f"{self.limits.max_total_tokens})"
            )
            raise BudgetExhaustedError(self._exhaustion_reason)

    def record_usage(self, record: SubagentUsageRecord) -> None:
        """Record usage from an executed subagent turn."""
        self._records.append(record)
        self._total_turns += record.turns_used
        total_tokens = record.prompt_tokens + record.completion_tokens
        self._total_tokens += total_tokens
        self._total_cost_usd += record.estimated_cost_usd

        role_key = record.role.value
        self._turns_by_role[role_key] = self._turns_by_role.get(role_key, 0) + record.turns_used

        if self._total_turns >= self.limits.max_total_turns:
            self._is_exhausted = True
            self._exhaustion_reason = (
                f"Total turn budget reached ({self._total_turns}/{self.limits.max_total_turns})"
            )
        elif self._total_cost_usd >= self.limits.max_total_cost_usd:
            self._is_exhausted = True
            self._exhaustion_reason = (
                f"Total cost budget reached (${self._total_cost_usd:.4f}/"
                f"${self.limits.max_total_cost_usd:.2f})"
            )
        elif self._total_tokens >= self.limits.max_total_tokens:
            self._is_exhausted = True
            self._exhaustion_reason = (
                f"Total token budget reached ({self._total_tokens}/{self.limits.max_total_tokens})"
            )

    def get_summary(self) -> BudgetSummary:
        """Generate a snapshot summary of current budget consumption."""
        role_breakdown: dict[str, dict[str, Any]] = {}
        for role_key, turns in self._turns_by_role.items():
            role_records = [r for r in self._records if r.role.value == role_key]
            tokens = sum(r.prompt_tokens + r.completion_tokens for r in role_records)
            cost = sum(r.estimated_cost_usd for r in role_records)
            duration = sum(r.duration_ms for r in role_records)
            role_breakdown[role_key] = {
                "turns_used": turns,
                "total_tokens": tokens,
                "estimated_cost_usd": round(cost, 6),
                "total_duration_ms": duration,
            }

        return BudgetSummary(
            total_turns=self._total_turns,
            total_tokens=self._total_tokens,
            total_cost_usd=round(self._total_cost_usd, 6),
            is_exhausted=self._is_exhausted,
            exhaustion_reason=self._exhaustion_reason,
            usage_by_role=role_breakdown,
        )

    @property
    def is_exhausted(self) -> bool:
        """Check whether budget exhaustion has occurred."""
        return self._is_exhausted


# ---------------------------------------------------------------------------
# Inter-Agent Contracts: Inventory Interpreter
# ---------------------------------------------------------------------------


class InventoryInterpretationRequest(BaseModel):
    """Input payload for the Inventory Interpreter subagent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inventory: ProjectInventory
    focus_frameworks: tuple[str, ...] = Field(default_factory=tuple)


class InventoryInterpretation(BaseModel):
    """Synthesized domain insights emitted by the Inventory Interpreter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    architectural_summary: str
    framework_notes: dict[str, str] = Field(default_factory=dict)
    key_risks: tuple[str, ...] = Field(default_factory=tuple)
    recommended_migration_strategy: str = ""


# ---------------------------------------------------------------------------
# Inter-Agent Contracts: Migration Analyst
# ---------------------------------------------------------------------------


class MigrationAnalystRequest(BaseModel):
    """Input payload for the Migration Analyst subagent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inventory: ProjectInventory
    interpretation: InventoryInterpretation | None = None
    target_framework: str = "angular"
    max_turns: int = Field(default=15, ge=1)


class MigrationAnalysisOutput(BaseModel):
    """Structured analysis findings emitted by the Migration Analyst."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str
    findings: tuple[AnalysisFinding, ...] = Field(default_factory=tuple)
    assumptions: tuple[str, ...] = Field(default_factory=tuple)
    unsupported_constructs: tuple[str, ...] = Field(default_factory=tuple)
    questions: tuple[str, ...] = Field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Inter-Agent Contracts: Plan Critic
# ---------------------------------------------------------------------------


class PlanCriticRequest(BaseModel):
    """Input payload for the Plan Critic subagent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan: MigrationPlan
    inventory: ProjectInventory
    analysis: AnalysisResult | None = None


class PlanCritiquePoint(BaseModel):
    """Individual critique item evaluating a migration plan step or global strategy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str | None = None
    severity: FindingSeverity
    category: str
    critique: str
    recommendation: str = ""


class PlanCritique(BaseModel):
    """Structured plan audit emitted by the Plan Critic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_score: float = Field(ge=0.0, le=1.0)
    approval_recommended: bool
    critique_points: tuple[PlanCritiquePoint, ...] = Field(default_factory=tuple)
    flagged_step_ids: tuple[str, ...] = Field(default_factory=tuple)
    summary: str = ""


# ---------------------------------------------------------------------------
# Inter-Agent Contracts: Repair Diagnostician
# ---------------------------------------------------------------------------


class RepairDiagnosticianRequest(BaseModel):
    """Input payload for the Repair Diagnostician subagent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    failing_result: ValidationResult
    current_changeset: ChangeSet
    allowed_scope: tuple[str, ...]
    previous_attempts: tuple[RepairAttempt, ...] = Field(default_factory=tuple)


class RepairDiagnosis(BaseModel):
    """Diagnostic root cause and targeted guidance emitted by Repair Diagnostician."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    root_cause_category: str
    actionable: bool
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_file: str | None = None
    diagnostic_details: str = ""
    suggested_fix_summary: str = ""


# ---------------------------------------------------------------------------
# Specialist Evaluation Metrics
# ---------------------------------------------------------------------------


class SpecialistEvaluationMetric(BaseModel):
    """Comparative evaluation metrics measuring specialist value against baseline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_f1: float = Field(ge=0.0, le=1.0)
    specialist_f1: float = Field(ge=0.0, le=1.0)
    turns_used: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    plan_critique_score: float | None = None
    repair_accuracy: float | None = None
    improvement_detected: bool = False
