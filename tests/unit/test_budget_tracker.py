"""Unit tests for specialist subagent turn and cost budget tracker."""

import pytest

from migration_agent.domain import (
    BudgetExhaustedError,
    BudgetLimit,
    BudgetTracker,
    SpecialistRole,
    SubagentUsageRecord,
)


def test_budget_tracker_initial_state() -> None:
    tracker = BudgetTracker()
    assert tracker.can_invoke(SpecialistRole.INVENTORY_INTERPRETER)
    assert not tracker.is_exhausted
    summary = tracker.get_summary()
    assert summary.total_turns == 0
    assert summary.total_cost_usd == 0.0
    assert summary.total_tokens == 0


def test_budget_tracker_records_usage_and_accumulates() -> None:
    tracker = BudgetTracker()
    record = SubagentUsageRecord(
        role=SpecialistRole.INVENTORY_INTERPRETER,
        turns_used=2,
        prompt_tokens=400,
        completion_tokens=200,
        estimated_cost_usd=0.005,
        duration_ms=120,
    )
    tracker.record_usage(record)

    summary = tracker.get_summary()
    assert summary.total_turns == 2
    assert summary.total_tokens == 600
    assert summary.total_cost_usd == 0.005
    assert not tracker.is_exhausted
    assert "inventory_interpreter" in summary.usage_by_role
    role_info = summary.usage_by_role["inventory_interpreter"]
    assert role_info["turns_used"] == 2
    assert role_info["total_tokens"] == 600


def test_budget_tracker_per_role_turn_limit() -> None:
    limits = BudgetLimit(
        max_total_turns=10,
        max_turns_per_role={"inventory_interpreter": 2, "plan_critic": 5},
    )
    tracker = BudgetTracker(limits)

    tracker.record_usage(
        SubagentUsageRecord(
            role=SpecialistRole.INVENTORY_INTERPRETER,
            turns_used=2,
            prompt_tokens=100,
            completion_tokens=50,
            estimated_cost_usd=0.001,
            duration_ms=50,
        )
    )

    # Role limit reached for inventory_interpreter
    assert not tracker.can_invoke(SpecialistRole.INVENTORY_INTERPRETER)
    with pytest.raises(BudgetExhaustedError, match="turn budget exceeded"):
        tracker.check_budget(SpecialistRole.INVENTORY_INTERPRETER)

    # But plan_critic is still within budget!
    # Wait, once check_budget raises, it marks exhausted? Let's check:
    # In check_budget: `self._is_exhausted = True`. So check_budget locks exhaustion.
    # To check availability without raising, can_invoke is used.


def test_budget_tracker_can_invoke_checks_other_roles() -> None:
    limits = BudgetLimit(
        max_total_turns=10,
        max_turns_per_role={"inventory_interpreter": 1, "plan_critic": 3},
    )
    tracker = BudgetTracker(limits)
    tracker.record_usage(
        SubagentUsageRecord(
            role=SpecialistRole.INVENTORY_INTERPRETER,
            turns_used=1,
            prompt_tokens=100,
            completion_tokens=50,
            estimated_cost_usd=0.001,
            duration_ms=50,
        )
    )

    assert not tracker.can_invoke(SpecialistRole.INVENTORY_INTERPRETER)
    assert tracker.can_invoke(SpecialistRole.PLAN_CRITIC)


def test_budget_tracker_total_cost_limit_enforced() -> None:
    limits = BudgetLimit(
        max_total_cost_usd=0.010,
    )
    tracker = BudgetTracker(limits)
    tracker.record_usage(
        SubagentUsageRecord(
            role=SpecialistRole.MIGRATION_ANALYST,
            turns_used=1,
            prompt_tokens=2000,
            completion_tokens=1000,
            estimated_cost_usd=0.015,  # Exceeds max_total_cost_usd
            duration_ms=200,
        )
    )

    assert tracker.is_exhausted
    assert not tracker.can_invoke(SpecialistRole.PLAN_CRITIC)
    with pytest.raises(BudgetExhaustedError, match="cost budget"):
        tracker.check_budget(SpecialistRole.PLAN_CRITIC)


def test_budget_tracker_total_token_limit_enforced() -> None:
    limits = BudgetLimit(
        max_total_tokens=1000,
    )
    tracker = BudgetTracker(limits)
    tracker.record_usage(
        SubagentUsageRecord(
            role=SpecialistRole.MIGRATION_ANALYST,
            turns_used=1,
            prompt_tokens=600,
            completion_tokens=500,  # 1100 tokens > 1000
            estimated_cost_usd=0.002,
            duration_ms=100,
        )
    )

    assert tracker.is_exhausted
    assert not tracker.can_invoke(SpecialistRole.PLAN_CRITIC)
