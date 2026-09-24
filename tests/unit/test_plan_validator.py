"""Unit tests for rule-based migration plan validation and DAG cycle detection."""

from pathlib import Path

import pytest

from migration_agent.application.validator import RuleBasedPlanValidator
from migration_agent.domain import (
    EvidenceReference,
    EvidenceStatus,
    FileCategory,
    InventoryFile,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    ProjectInventory,
    RepositoryDescriptor,
    StepRisk,
)


def _make_step(
    step_id: str,
    dependencies: list[str] | None = None,
    validation: list[str] | None = None,
    expected_files: list[str] | None = None,
    evidence: list[EvidenceReference] | None = None,
) -> MigrationStep:
    return MigrationStep(
        step_id=step_id,
        title=f"Step {step_id}",
        description=f"Description for {step_id}",
        dependencies=dependencies or [],
        scope="component",
        risk=StepRisk.LOW,
        confidence=1.0,
        evidence=evidence or [],
        expected_files=expected_files or ["out.ts"],
        validation_strategy=validation if validation is not None else ["npm test"],
        rollback_note="revert",
        acceptance_criteria=["done"],
        unresolved_questions=[],
    )


def test_validator_passes_valid_plan() -> None:
    validator = RuleBasedPlanValidator()
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[
            _make_step("step-001"),
            _make_step("step-002", dependencies=["step-001"]),
        ],
    )
    result = validator.validate(plan)
    assert result.is_valid is True
    assert result.errors == []


def test_validator_fails_empty_steps() -> None:
    validator = RuleBasedPlanValidator()
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[],
    )
    result = validator.validate(plan)
    assert result.is_valid is False
    assert any("at least one step" in err for err in result.errors)


def test_validator_detects_duplicate_step_ids() -> None:
    validator = RuleBasedPlanValidator()
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[
            _make_step("step-001"),
            _make_step("step-001"),
        ],
    )
    result = validator.validate(plan)
    assert result.is_valid is False
    assert any("Duplicate step ID 'step-001'" in err for err in result.errors)


def test_validator_detects_self_dependency() -> None:
    validator = RuleBasedPlanValidator()
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[_make_step("step-001", dependencies=["step-001"])],
    )
    result = validator.validate(plan)
    assert result.is_valid is False
    assert any("cannot depend on itself" in err for err in result.errors)


def test_validator_detects_unknown_dependency() -> None:
    validator = RuleBasedPlanValidator()
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[_make_step("step-001", dependencies=["step-nonexistent"])],
    )
    result = validator.validate(plan)
    assert result.is_valid is False
    assert any("non-existent step 'step-nonexistent'" in err for err in result.errors)


def test_validator_detects_two_step_cycle() -> None:
    validator = RuleBasedPlanValidator()
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[
            _make_step("step-001", dependencies=["step-002"]),
            _make_step("step-002", dependencies=["step-001"]),
        ],
    )
    result = validator.validate(plan)
    assert result.is_valid is False
    assert any("Dependency cycle detected" in err for err in result.errors)


def test_validator_detects_three_step_cycle() -> None:
    validator = RuleBasedPlanValidator()
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[
            _make_step("step-A", dependencies=["step-C"]),
            _make_step("step-B", dependencies=["step-A"]),
            _make_step("step-C", dependencies=["step-B"]),
        ],
    )
    result = validator.validate(plan)
    assert result.is_valid is False
    assert any("Dependency cycle detected" in err for err in result.errors)


def test_validator_detects_missing_validation_strategy() -> None:
    validator = RuleBasedPlanValidator()
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[_make_step("step-001", validation=[])],
    )
    result = validator.validate(plan)
    assert result.is_valid is False
    assert any("no validation strategy defined" in err for err in result.errors)


def test_validator_detects_exceeded_file_limit() -> None:
    validator = RuleBasedPlanValidator(max_step_files=2)
    plan = MigrationPlan(
        plan_id="p1",
        source_root="/repo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[_make_step("step-001", expected_files=["a.ts", "b.ts", "c.ts"])],
    )
    result = validator.validate(plan)
    assert result.is_valid is False
    assert any("exceeds maximum expected files (3 > 2)" in err for err in result.errors)


def test_validator_checks_evidence_against_inventory() -> None:
    validator = RuleBasedPlanValidator()
    from migration_agent.domain import ExclusionSummary

    inventory = ProjectInventory(
        repository=RepositoryDescriptor(name="demo", root=Path("/demo")),
        files=(
            InventoryFile(
                path="app/real.js",
                size_bytes=100,
                category=FileCategory.SOURCE,
                sha256="0" * 64,
            ),
        ),
        dependencies=(),
        package_boundaries=(),
        frameworks=(),
        exclusions=ExclusionSummary(),
        issues=(),
    )

    valid_ev = EvidenceReference(
        path="app/real.js",
        description="real",
        status=EvidenceStatus.VALID,
    )
    invalid_ev = EvidenceReference(
        path="app/ghost.js",
        description="ghost",
        status=EvidenceStatus.VALID,
    )

    plan_valid = MigrationPlan(
        plan_id="p1",
        source_root="/demo",
        run_id="r1",
        status=PlanStatus.DRAFT,
        steps=[_make_step("step-001", evidence=[valid_ev])],
    )
    res_valid = validator.validate(plan_valid, inventory)
    assert res_valid.is_valid is True

    plan_invalid = MigrationPlan(
        plan_id="p2",
        source_root="/demo",
        run_id="r2",
        status=PlanStatus.DRAFT,
        steps=[_make_step("step-002", evidence=[invalid_ev])],
    )
    res_invalid = validator.validate(plan_invalid, inventory)
    assert res_invalid.is_valid is False
    assert any(
        "invalid or missing evidence path 'app/ghost.js'" in err for err in res_invalid.errors
    )


def test_topological_sort_orders_dependencies_first() -> None:
    validator = RuleBasedPlanValidator()
    step1 = _make_step("step-001")
    step2 = _make_step("step-002", dependencies=["step-001"])
    step3 = _make_step("step-003", dependencies=["step-002"])

    # Pass in shuffled order
    sorted_steps = validator.topological_sort([step3, step1, step2])
    assert [s.step_id for s in sorted_steps] == ["step-001", "step-002", "step-003"]


def test_topological_sort_raises_on_cycle() -> None:
    validator = RuleBasedPlanValidator()
    step1 = _make_step("step-001", dependencies=["step-002"])
    step2 = _make_step("step-002", dependencies=["step-001"])

    with pytest.raises(ValueError, match="Dependency cycle detected"):
        validator.topological_sort([step1, step2])
