"""Unit tests for Git-native governance adapter (.agent/ layout, policies, exports)."""

from pathlib import Path

from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.domain import (
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    StepRisk,
)


def _make_plan(plan_id: str = "plan-gov") -> MigrationPlan:
    step = MigrationStep(
        step_id="step-001",
        title="Test step",
        description="Description",
        dependencies=[],
        scope="component",
        risk=StepRisk.LOW,
        confidence=1.0,
        evidence=[],
        expected_files=["a.ts"],
        validation_strategy=["test"],
        rollback_note="",
        acceptance_criteria=[],
        unresolved_questions=[],
    )
    return MigrationPlan(
        plan_id=plan_id,
        source_root="/repo",
        run_id="run-gov",
        status=PlanStatus.NEEDS_APPROVAL,
        steps=[step],
        policy_digest="sha256:pol",
    )


def test_git_governance_layout_initialization(tmp_path: Path) -> None:
    adapter = GitGovernanceAdapter()
    adapter.ensure_governance_layout(str(tmp_path), project_id="custom-project")

    manifest_file = tmp_path / ".agent" / "manifest.json"
    policy_file = tmp_path / ".agent" / "policy.json"
    plans_dir = tmp_path / ".agent" / "plans"

    assert manifest_file.exists()
    assert policy_file.exists()
    assert plans_dir.is_dir()
    assert '"project_id": "custom-project"' in manifest_file.read_text(encoding="utf-8")


def test_git_governance_policy_and_digest(tmp_path: Path) -> None:
    adapter = GitGovernanceAdapter()
    adapter.ensure_governance_layout(str(tmp_path))

    policy = adapter.get_policy(str(tmp_path))
    assert policy.schema_version == 1
    assert policy.default_mode == "MODE_B"

    digest = adapter.get_policy_digest(str(tmp_path))
    assert digest.startswith("sha256:")
    assert len(digest) == 71


def test_git_governance_export_and_load_plan(tmp_path: Path) -> None:
    adapter = GitGovernanceAdapter()
    plan = _make_plan("plan-007")

    export_path = adapter.export_plan(str(tmp_path), plan)
    assert Path(export_path).exists()
    assert export_path.endswith("plan-007.json")

    loaded_plan = adapter.load_plan(str(tmp_path), "plan-007")
    assert loaded_plan is not None
    assert loaded_plan.plan_id == "plan-007"
    assert loaded_plan.status == PlanStatus.NEEDS_APPROVAL
    assert len(loaded_plan.steps) == 1

    assert adapter.load_plan(str(tmp_path), "plan-missing") is None
