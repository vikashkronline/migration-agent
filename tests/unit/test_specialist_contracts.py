"""Unit tests for specialist subagent typed domain contracts."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from migration_agent.domain import (
    AnalysisFinding,
    ChangeSet,
    ExclusionSummary,
    FindingCategory,
    FindingSeverity,
    InventoryInterpretation,
    InventoryInterpretationRequest,
    MigrationAnalysisOutput,
    MigrationAnalystRequest,
    MigrationPlan,
    PlanCriticRequest,
    PlanCritique,
    PlanCritiquePoint,
    PlanStatus,
    ProjectInventory,
    RepairDiagnosis,
    RepairDiagnosticianRequest,
    RepositoryDescriptor,
    SpecialistEvaluationMetric,
    SpecialistRole,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
)


@pytest.fixture
def sample_inventory() -> ProjectInventory:
    return ProjectInventory(
        repository=RepositoryDescriptor(
            name="demo-app",
            root=Path("demo-app"),
        ),
        frameworks=(),
        dependencies=(),
        package_boundaries=(),
        files=(),
        exclusions=ExclusionSummary(),
        issues=(),
    )


def test_specialist_role_enums() -> None:
    assert SpecialistRole.INVENTORY_INTERPRETER.value == "inventory_interpreter"
    assert SpecialistRole.MIGRATION_ANALYST.value == "migration_analyst"
    assert SpecialistRole.PLAN_CRITIC.value == "plan_critic"
    assert SpecialistRole.REPAIR_DIAGNOSTICIAN.value == "repair_diagnostician"


def test_inventory_interpretation_contracts(sample_inventory: ProjectInventory) -> None:
    req = InventoryInterpretationRequest(
        inventory=sample_inventory,
        focus_frameworks=("ember", "angular"),
    )
    assert req.focus_frameworks == ("ember", "angular")

    resp = InventoryInterpretation(
        architectural_summary="Ember Classic architecture with isolated components.",
        framework_notes={"ember-classic": "Found 3 components"},
        key_risks=("Prototype pollution",),
        recommended_migration_strategy="Bottom-up component migration.",
    )
    assert resp.architectural_summary.startswith("Ember Classic")
    assert resp.framework_notes["ember-classic"] == "Found 3 components"
    assert resp.key_risks == ("Prototype pollution",)

    # Immutability check
    with pytest.raises(ValidationError):
        resp.architectural_summary = "Modified"  # type: ignore[misc]

    # Extra attributes forbidden
    with pytest.raises(ValidationError):
        InventoryInterpretation(
            architectural_summary="Summary",
            extra_field="disallowed",  # type: ignore[call-arg]
        )


def test_migration_analyst_contracts(sample_inventory: ProjectInventory) -> None:
    interpretation = InventoryInterpretation(
        architectural_summary="Summary",
    )
    req = MigrationAnalystRequest(
        inventory=sample_inventory,
        interpretation=interpretation,
        target_framework="angular",
        max_turns=12,
    )
    assert req.max_turns == 12

    finding = AnalysisFinding(
        id="finding-001",
        title="Custom Mixin Pattern",
        category=FindingCategory.ARCHITECTURE,
        severity=FindingSeverity.HIGH,
        confidence=0.92,
        description="Heavy mixin usage detected.",
    )
    resp = MigrationAnalysisOutput(
        summary="Deep code analysis complete.",
        findings=(finding,),
        assumptions=("Target is Angular 17+",),
        unsupported_constructs=("Classic Ember.Mixin",),
        questions=("Can mixin logic be replaced with composable functions?",),
    )
    assert len(resp.findings) == 1
    assert resp.findings[0].severity == FindingSeverity.HIGH


def test_plan_critic_contracts(sample_inventory: ProjectInventory) -> None:
    plan = MigrationPlan(
        plan_id="plan-123",
        source_root="/repo",
        run_id="run-123",
        status=PlanStatus.DRAFT,
        steps=[],
        policy_digest="digest-123",
    )
    req = PlanCriticRequest(
        plan=plan,
        inventory=sample_inventory,
    )
    assert req.plan.plan_id == "plan-123"

    point = PlanCritiquePoint(
        step_id="step-001",
        severity=FindingSeverity.MEDIUM,
        category="SCOPE",
        critique="Step modifies too many files at once.",
        recommendation="Split into two steps.",
    )
    critique = PlanCritique(
        overall_score=0.82,
        approval_recommended=True,
        critique_points=(point,),
        flagged_step_ids=("step-001",),
        summary="Plan is sound with minor scope warning.",
    )
    assert critique.overall_score == 0.82
    assert critique.approval_recommended is True
    assert len(critique.critique_points) == 1


def test_repair_diagnostician_contracts() -> None:
    failing_val = ValidationResult(
        command="npm test",
        profile=ValidationProfile.TEST,
        exit_code=1,
        status=ValidationStatus.FAILED,
        duration_ms=450,
        output_digest="digest-fail",
        diagnostics=("AssertionError: expected false to be true",),
        sanitized_output="AssertionError: expected false to be true",
    )
    changeset = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="base123",
        worktree_fingerprint="worktree123",
        changes=(),
    )
    req = RepairDiagnosticianRequest(
        failing_result=failing_val,
        current_changeset=changeset,
        allowed_scope=("src/app/component.ts",),
    )
    assert req.allowed_scope == ("src/app/component.ts",)

    diagnosis = RepairDiagnosis(
        root_cause_category="TEST_ASSERTION_FAILURE",
        actionable=True,
        confidence=0.88,
        suggested_file="src/app/component.ts",
        diagnostic_details="State toggle logic inverted.",
        suggested_fix_summary="Invert boolean flag in toggleActive method.",
    )
    assert diagnosis.actionable is True
    assert diagnosis.suggested_file == "src/app/component.ts"
    assert diagnosis.confidence == 0.88


def test_specialist_evaluation_metric() -> None:
    metric = SpecialistEvaluationMetric(
        baseline_f1=0.85,
        specialist_f1=0.95,
        turns_used=4,
        cost_usd=0.0125,
        plan_critique_score=0.92,
        repair_accuracy=1.0,
        improvement_detected=True,
    )
    assert metric.improvement_detected is True
    assert metric.specialist_f1 > metric.baseline_f1
