"""Unit tests for PlanningService coordinating domain, ports, and storage tiers."""

from pathlib import Path

import pytest

from migration_agent.adapters import (
    FakeAgentRuntime,
    GitGovernanceAdapter,
    SqliteCheckpointStore,
)
from migration_agent.application import PlanningService, RuleBasedPlanValidator
from migration_agent.domain import (
    AnalysisResult,
    AssuranceLevel,
    FileCategory,
    InventoryFile,
    PlanStatus,
    ProjectInventory,
    RepositoryDescriptor,
    verify_approval,
)


def _sample_inventory() -> ProjectInventory:
    from migration_agent.domain import ExclusionSummary

    return ProjectInventory(
        repository=RepositoryDescriptor(name="demo-repo", root=Path("/demo")),
        files=(
            InventoryFile(
                path="app/components/user-card.js",
                size_bytes=150,
                category=FileCategory.SOURCE,
                sha256="1" * 64,
            ),
            InventoryFile(
                path="package.json",
                size_bytes=200,
                category=FileCategory.MANIFEST,
                sha256="2" * 64,
            ),
        ),
        dependencies=(),
        package_boundaries=(),
        frameworks=(),
        exclusions=ExclusionSummary(),
        issues=(),
    )


def _sample_analysis(inventory: ProjectInventory) -> AnalysisResult:
    runtime = FakeAgentRuntime()

    class DummyFileReader:
        def read_file(self, path: str) -> str:
            return "content"

    from migration_agent.ports import AnalysisRequest

    return runtime.analyze(
        AnalysisRequest(inventory=inventory, model="fake-model"),
        DummyFileReader(),
    )


def test_planning_receives_only_accepted_external_decisions(tmp_path: Path) -> None:
    from migration_agent.adapters import GitKnowledgeAdapter
    from migration_agent.domain.knowledge import ArchitecturalDecisionRecord, DecisionStatus
    from migration_agent.ports import PlanningRequest

    requests: list[PlanningRequest] = []

    class CapturingRuntime(FakeAgentRuntime):
        def plan(self, request: PlanningRequest):
            requests.append(request)
            return super().plan(request)

    project = tmp_path / "governance"
    knowledge = GitKnowledgeAdapter()
    for decision_id, status in (
        ("ADR-003", DecisionStatus.ACCEPTED),
        ("ADR-002", DecisionStatus.SUPERSEDED),
        ("ADR-001", DecisionStatus.ACCEPTED),
        ("ADR-004", DecisionStatus.PROPOSED),
        ("ADR-005", DecisionStatus.REJECTED),
    ):
        knowledge.save_decision(
            str(project),
            ArchitecturalDecisionRecord(
                decision_id=decision_id,
                title="Target architecture",
                status=status,
                context="Migration baseline",
                decision="Use the confirmed target baseline.",
                consequences="Foundation must precede feature work.",
                decided_by="operator",
            ),
        )
    store = SqliteCheckpointStore(tmp_path / "state")
    service = PlanningService(
        runtime=CapturingRuntime(),
        checkpoint_store=store,
        audit_logger=store,
        governance=GitGovernanceAdapter(),
        knowledge=knowledge,
    )
    inventory = _sample_inventory()
    service.create_plan(inventory, _sample_analysis(inventory), str(project), model="offline")
    assert [d.decision_id for d in requests[0].accepted_decisions] == ["ADR-001", "ADR-003"]
    assert all(d.status == DecisionStatus.ACCEPTED for d in requests[0].accepted_decisions)
    assert requests[0].inventory.repository.root == inventory.repository.root


def test_planning_bounds_architecture_context_before_runtime(tmp_path: Path) -> None:
    from unittest.mock import Mock

    from migration_agent.adapters import GitKnowledgeAdapter
    from migration_agent.domain.knowledge import ArchitecturalDecisionRecord

    knowledge = GitKnowledgeAdapter()
    project = tmp_path / "project"
    knowledge.save_decision(
        str(project),
        ArchitecturalDecisionRecord(
            decision_id="ADR-001",
            title="Large decision",
            context="Migration",
            decision="x" * 65_537,
            consequences="Stop",
            decided_by="operator",
        ),
    )
    store = SqliteCheckpointStore(tmp_path / "state")
    runtime = Mock()
    service = PlanningService(
        runtime=runtime,
        checkpoint_store=store,
        audit_logger=store,
        governance=GitGovernanceAdapter(),
        knowledge=knowledge,
    )
    inventory = _sample_inventory()
    with pytest.raises(ValueError, match="ARCHITECTURE_CONTEXT_TOO_LARGE"):
        service.create_plan(inventory, _sample_analysis(inventory), str(project), model="offline")
    runtime.plan.assert_not_called()


def test_planning_service_create_and_lifecycle(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    checkpoint_store = SqliteCheckpointStore(state_dir)
    governance = GitGovernanceAdapter()
    runtime = FakeAgentRuntime()
    validator = RuleBasedPlanValidator()

    service = PlanningService(
        runtime=runtime,
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
        governance=governance,
        validator=validator,
    )

    inventory = _sample_inventory()
    analysis = _sample_analysis(inventory)

    # 1. Create plan
    plan, validation = service.create_plan(
        inventory=inventory,
        analysis=analysis,
        project_root=str(project_root),
        provider="fake",
        model="fake-model",
    )

    assert validation.is_valid is True
    assert plan.status == PlanStatus.NEEDS_APPROVAL
    assert len(plan.steps) >= 1
    assert plan.source_root == str(inventory.repository.root.resolve())
    assert plan.source_root != str(project_root)

    # Verify SQLite persistence
    stored_plan = checkpoint_store.get_plan(plan.plan_id)
    assert stored_plan is not None
    assert stored_plan.plan_id == plan.plan_id

    # Verify Git governance export
    exported_file = project_root / ".agent" / "plans" / f"{plan.plan_id}.json"
    assert exported_file.exists()

    # Verify audit event and checkpoints
    checkpoints = checkpoint_store.list_checkpoints(plan.run_id)
    assert len(checkpoints) >= 1
    assert checkpoints[0].checkpoint_type == "PLAN_GENERATED"

    # 2. Approve plan
    approved_plan = service.approve_plan(
        plan_id=plan.plan_id,
        actor="lead-developer",
        assurance_level=AssuranceLevel.MODE_B,
        project_root=str(project_root),
    )

    assert approved_plan.status == PlanStatus.APPROVED
    assert approved_plan.approval is not None
    assert approved_plan.approval.actor == "lead-developer"
    assert verify_approval(approved_plan) is True

    # 3. Reject plan flow test on a fresh plan
    plan2, _ = service.create_plan(
        inventory=inventory,
        analysis=analysis,
        project_root=str(project_root),
    )
    rejected_plan = service.reject_plan(
        plan_id=plan2.plan_id,
        reason="Architecture review requested modifications to step 2",
        actor="lead-architect",
        project_root=str(project_root),
    )
    assert rejected_plan.status == PlanStatus.REJECTED
    assert rejected_plan.rejection_reason == "Architecture review requested modifications to step 2"
