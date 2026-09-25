"""Unit tests for Plan Critic subagent and DeterministicPlanCriticAggregator."""

from pathlib import Path

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.application.planning import PlanningService
from migration_agent.application.specialists import DeterministicPlanCriticAggregator
from migration_agent.application.validator import RuleBasedPlanValidator
from migration_agent.domain import (
    AnalysisResult,
    ExclusionSummary,
    FindingSeverity,
    MigrationPlan,
    MigrationStep,
    PlanCritique,
    PlanCritiquePoint,
    PlanStatus,
    ProjectInventory,
    RepositoryDescriptor,
    StepRisk,
)


def create_sample_plan(steps: list[MigrationStep]) -> MigrationPlan:
    return MigrationPlan(
        plan_id="plan-sample",
        source_root="sample-repo",
        run_id="run-sample",
        status=PlanStatus.DRAFT,
        steps=steps,
        policy_digest="digest-123",
    )


def test_plan_critic_aggregator_clean_plan() -> None:
    step = MigrationStep(
        step_id="step-001",
        title="Migrate button component",
        description="Extract and translate button.",
        dependencies=[],
        scope="component",
        risk=StepRisk.LOW,
        expected_files=["app/components/my-button.js"],
    )
    plan = create_sample_plan([step])
    critique = PlanCritique(
        overall_score=0.95,
        approval_recommended=True,
        critique_points=(
            PlanCritiquePoint(
                step_id=None,
                severity=FindingSeverity.INFO,
                category="GENERAL",
                critique="Plan structure is clean.",
            ),
        ),
        flagged_step_ids=(),
        summary="No issues found.",
    )

    updated_plan, approval, notes = DeterministicPlanCriticAggregator.aggregate_critique(
        plan, critique
    )
    assert approval is True
    assert updated_plan.steps[0].risk == StepRisk.LOW
    assert len(notes) == 2


def test_plan_critic_aggregator_escalates_step_risk() -> None:
    step1 = MigrationStep(
        step_id="step-001",
        title="Migrate user card",
        description="Extract user card.",
        dependencies=[],
        scope="component",
        risk=StepRisk.LOW,
        expected_files=["app/components/user-card.js"],
    )
    plan = create_sample_plan([step1])
    critique = PlanCritique(
        overall_score=0.60,
        approval_recommended=False,
        critique_points=(
            PlanCritiquePoint(
                step_id="step-001",
                severity=FindingSeverity.HIGH,
                category="DEPENDENCY",
                critique="Step references unmigrated store service.",
                recommendation="Migrate store service first.",
            ),
        ),
        flagged_step_ids=("step-001",),
        summary="Critical prerequisite missing.",
    )

    updated_plan, approval, _notes = DeterministicPlanCriticAggregator.aggregate_critique(
        plan, critique
    )
    assert approval is False
    # Step risk must be elevated to HIGH deterministically
    assert updated_plan.steps[0].risk == StepRisk.HIGH
    assert len(updated_plan.steps) == 1  # DAG topology strictly preserved


def test_planning_service_with_plan_critic(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    runtime = FakeAgentRuntime()
    governance = GitGovernanceAdapter()
    validator = RuleBasedPlanValidator()

    planning_service = PlanningService(
        runtime=runtime,
        checkpoint_store=store,
        audit_logger=store,
        governance=governance,
        validator=validator,
        specialist_runtime=runtime,
    )

    inventory = ProjectInventory(
        repository=RepositoryDescriptor(
            name="demo-repo",
            root=tmp_path,
        ),
        frameworks=(),
        dependencies=(),
        package_boundaries=(),
        files=(),
        exclusions=ExclusionSummary(),
        issues=(),
    )
    analysis = AnalysisResult(
        repository=inventory.repository,
        provider="fake",
        model="fake-model",
        is_dry_run=True,
        summary="Analysis complete.",
        findings=(),
    )

    plan, validation = planning_service.create_plan(
        inventory=inventory,
        analysis=analysis,
        project_root=str(tmp_path),
        enable_critic=True,
    )

    assert plan is not None
    assert len(runtime.recorded_critique_requests) == 1
    # Check that critic warnings were appended to validation warnings
    assert any("Plan critic evaluated" in w or "GENERAL" in w for w in validation.warnings)
