"""Unit tests for StackAnalysisService and StackRecommendationService."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from migration_agent.adapters.stack_catalog import get_default_target_preset
from migration_agent.application.stack_service import (
    StackAnalysisService,
    StackRecommendationService,
)
from migration_agent.domain.inventory import (
    Dependency,
    DependencyScope,
    ExclusionSummary,
    FileCategory,
    FrameworkEvidence,
    FrameworkFingerprint,
    InspectedTextFile,
    PackageBoundary,
    ProjectInventory,
    RepositoryDescriptor,
    RepositorySnapshot,
)
from migration_agent.domain.knowledge import (
    ArchitecturalDecisionRecord,
    DecisionStatus,
    EpistemicStatus,
)
from migration_agent.domain.stack import (
    LibraryCategory,
    ReplacementStrategy,
    StackAnalysisResult,
)
from migration_agent.ports.knowledge import KnowledgePort


class InMemoryKnowledgeAdapter(KnowledgePort):
    """In-memory implementation of KnowledgePort for testing."""

    def __init__(self) -> None:
        self.decisions: dict[str, ArchitecturalDecisionRecord] = {}

    def save_challenge(self, project_root: str, challenge: Any) -> str:
        raise NotImplementedError

    def get_challenge(self, project_root: str, challenge_id: str) -> Any | None:
        raise NotImplementedError

    def list_challenges(self, project_root: str) -> list[Any]:
        return []

    def save_solution(self, project_root: str, solution: Any) -> str:
        raise NotImplementedError

    def get_solution(self, project_root: str, solution_id: str) -> Any | None:
        raise NotImplementedError

    def list_solutions(self, project_root: str) -> list[Any]:
        return []

    def save_learning(self, project_root: str, learning: Any) -> str:
        raise NotImplementedError

    def get_learning(self, project_root: str, learning_id: str) -> Any | None:
        raise NotImplementedError

    def list_learnings(self, project_root: str) -> list[Any]:
        return []

    def save_decision(self, project_root: str, decision: ArchitecturalDecisionRecord) -> str:
        self.decisions[decision.decision_id] = decision
        return f"{project_root}/.agent/decisions/{decision.decision_id}.md"

    def get_decision(
        self, project_root: str, decision_id: str
    ) -> ArchitecturalDecisionRecord | None:
        return self.decisions.get(decision_id)

    def list_decisions(self, project_root: str) -> list[ArchitecturalDecisionRecord]:
        return sorted(self.decisions.values(), key=lambda d: d.decision_id)


def test_analyze_inventory_extracts_dependencies_and_unmapped() -> None:
    inventory = ProjectInventory(
        schema_version=1,
        repository=RepositoryDescriptor(name="test-repo", root=Path("c:/test-repo")),
        files=(),
        dependencies=(
            Dependency(
                name="ember-source",
                version_spec="~3.28.0",
                scope=DependencyScope.RUNTIME,
                manifest_path="package.json",
            ),
            Dependency(
                name="ember-cli",
                version_spec="~3.28.0",
                scope=DependencyScope.DEVELOPMENT,
                manifest_path="package.json",
            ),
            Dependency(
                name="ember-concurrency",
                version_spec="^2.0.0",
                scope=DependencyScope.RUNTIME,
                manifest_path="package.json",
            ),
            Dependency(
                name="custom-legacy-widget",
                version_spec="1.0.0",
                scope=DependencyScope.RUNTIME,
                manifest_path="package.json",
            ),
        ),
        package_boundaries=(
            PackageBoundary(
                path="package.json",
                manifest_path="package.json",
                declared_workspace=False,
            ),
        ),
        frameworks=(
            FrameworkFingerprint(
                framework_id="ember-classic",
                confidence=0.95,
                evidence=(
                    FrameworkEvidence(
                        path="package.json",
                        kind="manifest",
                        description="ember-source present",
                        weight=0.9,
                    ),
                ),
            ),
        ),
        exclusions=ExclusionSummary(),
        issues=(),
    )

    service = StackAnalysisService()
    result = service.analyze_inventory(inventory)

    assert result.source_framework == "ember-classic"
    assert len(result.dependencies) == 4

    dep_map = {d.name: d for d in result.dependencies}
    assert dep_map["ember-source"].category == LibraryCategory.FRAMEWORK
    assert not dep_map["ember-source"].is_dev
    assert dep_map["ember-cli"].is_dev

    # Verify unmapped dependencies
    assert len(result.unmapped_dependencies) == 1
    assert result.unmapped_dependencies[0].name == "custom-legacy-widget"


def test_analyze_source_gathers_usage_evidence() -> None:
    inspector = MagicMock()
    inspector.inspect.return_value = RepositorySnapshot(
        repository=RepositoryDescriptor(name="test-repo", root=Path("c:/test-repo")),
        files=(
            InspectedTextFile(
                path="package.json",
                category=FileCategory.MANIFEST,
                size_bytes=100,
                sha256="a" * 64,
                content='{"dependencies": {"moment": "^2.29.0", "ember-source": "~3.28.0"}}',
            ),
            InspectedTextFile(
                path="app/components/user-card.js",
                category=FileCategory.SOURCE,
                size_bytes=80,
                sha256="b" * 64,
                content="import moment from 'moment';\nexport default Component.extend({});",
            ),
            InspectedTextFile(
                path="app/templates/user-card.hbs",
                category=FileCategory.TEMPLATE,
                size_bytes=50,
                sha256="c" * 64,
                content="<p>{{moment-format date}}</p>",
            ),
        ),
        exclusions=ExclusionSummary(),
    )

    service = StackAnalysisService(inspector=inspector)
    result = service.analyze_source(Path("c:/test-repo"))

    assert result.source_framework == "ember-classic"
    dep_map = {d.name: d for d in result.dependencies}
    assert "moment" in dep_map
    assert "app/components/user-card.js" in dep_map["moment"].usage_evidence


def test_synthesize_draft_and_custom_mappings() -> None:
    inventory = ProjectInventory(
        schema_version=1,
        repository=RepositoryDescriptor(name="test-repo", root=Path("c:/test-repo")),
        files=(),
        dependencies=(
            Dependency(
                name="ember-source",
                version_spec="~3.28.0",
                scope=DependencyScope.RUNTIME,
                manifest_path="package.json",
            ),
            Dependency(
                name="custom-legacy-lib",
                version_spec="1.0.0",
                scope=DependencyScope.RUNTIME,
                manifest_path="package.json",
            ),
        ),
        package_boundaries=(),
        frameworks=(),
        exclusions=ExclusionSummary(),
        issues=(),
    )

    analysis_service = StackAnalysisService()
    analysis = analysis_service.analyze_inventory(inventory)

    rec_service = StackRecommendationService()
    draft = rec_service.synthesize_draft(
        analysis,
        project_id="test-proj",
        custom_mappings={"custom-legacy-lib": ReplacementStrategy.REMOVE},
    )

    assert draft.project_id == "test-proj"
    assert draft.content_digest.startswith("sha256:")

    mapping_map = {m.legacy_name: m for m in draft.mappings}
    assert mapping_map["ember-source"].strategy == ReplacementStrategy.REPLACE
    assert mapping_map["custom-legacy-lib"].strategy == ReplacementStrategy.REMOVE
    assert draft.unmapped_count == 0


def test_generate_foundation_adrs_fresh_project() -> None:
    knowledge = InMemoryKnowledgeAdapter()
    rec_service = StackRecommendationService(knowledge_port=knowledge)

    preset = get_default_target_preset()
    draft = rec_service.synthesize_draft(
        StackAnalysisResult(
            source_framework="ember-classic",
            dependencies=(),
            existing_adrs=(),
            detected_presets=(preset,),
            unmapped_dependencies=(),
        ),
        project_id="test-proj",
    )

    adrs = rec_service.generate_foundation_adrs(draft, governance_root="c:/governance")
    assert len(adrs) == 3
    assert adrs[0].decision_id == "ADR-001"
    assert adrs[1].decision_id == "ADR-002"
    assert adrs[2].decision_id == "ADR-003"
    assert all(a.status == DecisionStatus.PROPOSED for a in adrs)

    # Accept ADRs
    written = rec_service.accept_foundation_adrs(adrs, governance_root="c:/governance")
    assert len(written) == 3

    saved = knowledge.list_decisions("c:/governance")
    assert len(saved) == 3
    assert all(a.status == DecisionStatus.ACCEPTED for a in saved)


def test_generate_foundation_adrs_collision_and_supersession() -> None:
    knowledge = InMemoryKnowledgeAdapter()
    rec_service = StackRecommendationService(knowledge_port=knowledge)

    # Pre-populate an existing ADR-001 for a different target framework
    old_adr1 = ArchitecturalDecisionRecord(
        decision_id="ADR-001",
        title="Framework Architecture: Vue 3",
        status=DecisionStatus.ACCEPTED,
        context="Old decision selecting Vue.",
        decision="Adopt Vue 3.",
        consequences="Vue 3 architecture.",
        decided_by="Previous Maintainer",
        decided_at=datetime.now(UTC),
        epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
        metadata={"scope": "target_framework", "preset_id": "vue-3-legacy"},
    )
    knowledge.save_decision("c:/governance", old_adr1)

    preset = get_default_target_preset()
    draft = rec_service.synthesize_draft(
        StackAnalysisResult(
            source_framework="ember-classic",
            dependencies=(),
            existing_adrs=(),
            detected_presets=(preset,),
            unmapped_dependencies=(),
        ),
        project_id="test-proj",
    )

    # Generating ADRs should detect conflict on target_framework scope
    adrs = rec_service.generate_foundation_adrs(draft, governance_root="c:/governance")

    # Framework decision should have next available ID (ADR-002) and supersedes ADR-001
    fw_adr = next(a for a in adrs if a.metadata.get("scope") == "target_framework")
    assert fw_adr.decision_id == "ADR-002"
    assert fw_adr.metadata.get("supersedes") == ["ADR-001"]

    # Accept the new ADRs
    rec_service.accept_foundation_adrs(adrs, governance_root="c:/governance")

    # Historical signed bytes stay immutable; the successor records the supersession.
    updated_old = knowledge.get_decision("c:/governance", "ADR-001")
    assert updated_old is not None
    assert updated_old.status == DecisionStatus.ACCEPTED
    assert any(
        updated_old.decision_id in decision.metadata.get("supersedes", []) for decision in adrs
    )
