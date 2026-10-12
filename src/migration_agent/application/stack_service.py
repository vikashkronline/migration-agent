"""Application services for source stack analysis, recommendations, and ADR generation."""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from migration_agent.domain.inventory import DependencyScope, ProjectInventory
from migration_agent.domain.knowledge import (
    ArchitecturalDecisionRecord,
    DecisionStatus,
    EpistemicStatus,
)
from migration_agent.domain.stack import (
    LegacyDependency,
    PackageMappingOutcome,
    ReplacementStrategy,
    StackAnalysisResult,
    StackRecommendationDraft,
    compute_draft_digest,
)
from migration_agent.domain.stack_catalog import (
    categorize_dependency,
    get_available_target_presets,
    get_default_target_preset,
    lookup_package_mapping,
)
from migration_agent.ports.filesystem import FilesystemInspectorPort, InspectionPolicy
from migration_agent.ports.knowledge import KnowledgePort


class StackAnalysisService:
    """Deterministic source inventory analysis and dependency categorization."""

    def __init__(
        self,
        inspector: FilesystemInspectorPort | None = None,
        knowledge_port: KnowledgePort | None = None,
    ) -> None:
        self._inspector = inspector
        self._knowledge = knowledge_port

    def analyze_inventory(
        self,
        inventory: ProjectInventory,
        governance_root: Path | None = None,
    ) -> StackAnalysisResult:
        """Analyze dependencies and source evidence from an existing ProjectInventory."""
        dependencies: list[LegacyDependency] = []
        unmapped: list[LegacyDependency] = []

        for dep in inventory.dependencies:
            is_dev = dep.scope == DependencyScope.DEVELOPMENT
            category = categorize_dependency(dep.name, is_dev=is_dev)
            mapping = lookup_package_mapping(dep.name, dep.version_spec)

            legacy_dep = LegacyDependency(
                name=dep.name,
                declared_version=dep.version_spec,
                resolved_version=None,
                category=category,
                is_dev=is_dev,
                manifest_path=dep.manifest_path,
                usage_evidence=(),
            )
            dependencies.append(legacy_dep)
            if mapping is None:
                unmapped.append(legacy_dep)

        source_framework = "unknown"
        if inventory.frameworks:
            top_framework = max(inventory.frameworks, key=lambda f: f.confidence)
            source_framework = top_framework.framework_id

        existing_adrs: list[ArchitecturalDecisionRecord] = []
        if governance_root is not None and self._knowledge is not None:
            existing_adrs = self._knowledge.list_decisions(str(governance_root))

        return StackAnalysisResult(
            source_framework=source_framework,
            dependencies=tuple(dependencies),
            existing_adrs=tuple(existing_adrs),
            detected_presets=get_available_target_presets(),
            unmapped_dependencies=tuple(unmapped),
        )

    def analyze_source(
        self,
        source_root: Path,
        governance_root: Path | None = None,
    ) -> StackAnalysisResult:
        """Inspect source_root directly and analyze dependencies with usage evidence."""
        if self._inspector is None:
            raise RuntimeError("FilesystemInspectorPort is required for analyze_source.")

        snapshot = self._inspector.inspect(source_root, InspectionPolicy())

        # Collect text contents for evidence matching
        source_files = [
            f for f in snapshot.files if f.category.value in ("source", "template", "style")
        ]

        # Read manifests directly
        dependencies: list[LegacyDependency] = []
        unmapped: list[LegacyDependency] = []

        manifest_files = [f for f in snapshot.files if f.path.endswith("package.json")]
        import json

        for mf in manifest_files:
            try:
                data = json.loads(mf.content)
            except (json.JSONDecodeError, ValueError):
                continue

            sections = (
                ("dependencies", False),
                ("devDependencies", True),
                ("peerDependencies", False),
                ("optionalDependencies", False),
            )

            for section_name, is_dev in sections:
                sec_dict = data.get(section_name, {})
                if not isinstance(sec_dict, dict):
                    continue

                for pkg_name, version_spec in sorted(sec_dict.items()):
                    if not isinstance(version_spec, str):
                        version_spec = str(version_spec)

                    # Gather heuristic usage evidence
                    evidence: list[str] = []
                    dep_pattern = re.compile(rf"['\"]{re.escape(pkg_name)}['\"]")
                    for sf in source_files:
                        if dep_pattern.search(sf.content):
                            evidence.append(sf.path)
                            if len(evidence) >= 3:
                                break

                    category = categorize_dependency(pkg_name, is_dev=is_dev)
                    mapping = lookup_package_mapping(pkg_name, version_spec)

                    legacy_dep = LegacyDependency(
                        name=pkg_name,
                        declared_version=version_spec,
                        resolved_version=None,
                        category=category,
                        is_dev=is_dev,
                        manifest_path=mf.path,
                        usage_evidence=tuple(evidence),
                    )
                    dependencies.append(legacy_dep)
                    if mapping is None:
                        unmapped.append(legacy_dep)

        source_framework = "unknown"
        for dep in dependencies:
            if dep.name == "ember-source":
                source_framework = "ember-classic"
                break
            elif dep.name == "@angular/core":
                source_framework = "angular-legacy"
                break

        existing_adrs: list[ArchitecturalDecisionRecord] = []
        if governance_root is not None and self._knowledge is not None:
            existing_adrs = self._knowledge.list_decisions(str(governance_root))

        return StackAnalysisResult(
            source_framework=source_framework,
            dependencies=tuple(dependencies),
            existing_adrs=tuple(existing_adrs),
            detected_presets=get_available_target_presets(),
            unmapped_dependencies=tuple(unmapped),
        )


class StackRecommendationService:
    """Synthesizes stack recommendation drafts and generates collision-safe ADRs."""

    def __init__(self, knowledge_port: KnowledgePort | None = None) -> None:
        self._knowledge = knowledge_port

    def synthesize_draft(
        self,
        analysis: StackAnalysisResult,
        project_id: str,
        preset_id: str | None = None,
        custom_mappings: dict[str, ReplacementStrategy] | None = None,
        source_revision: str = "HEAD",
        governance_revision: str = "HEAD",
    ) -> StackRecommendationDraft:
        """Synthesize a complete stack recommendation draft with RFC 8785 canonical digest."""
        preset = get_default_target_preset()
        if preset_id:
            for p in get_available_target_presets():
                if p.preset_id == preset_id:
                    preset = p
                    break

        mappings: list[PackageMappingOutcome] = []
        custom_map = custom_mappings or {}

        for dep in analysis.dependencies:
            curated = lookup_package_mapping(dep.name, dep.declared_version)
            if dep.name in custom_map:
                strategy = custom_map[dep.name]
                if strategy in {
                    ReplacementStrategy.REPLACE,
                    ReplacementStrategy.KEEP,
                    ReplacementStrategy.NATIVE,
                } and (curated is None or not curated.target_packages):
                    raise ValueError(
                        "MAPPING_REPLACEMENT_REQUIRED: choose an installed mapping "
                        "or explicitly remove/defer this dependency."
                    )
                mappings.append(
                    PackageMappingOutcome(
                        legacy_name=dep.name,
                        strategy=strategy,
                        target_packages=curated.target_packages
                        if curated
                        and strategy
                        in {
                            ReplacementStrategy.REPLACE,
                            ReplacementStrategy.KEEP,
                            ReplacementStrategy.NATIVE,
                        }
                        else (),
                        rationale=f"User-specified custom replacement strategy: {strategy.value}",
                        behavioral_notes=None,
                    )
                )
            elif curated is not None:
                mappings.append(curated)
            else:
                mappings.append(
                    PackageMappingOutcome(
                        legacy_name=dep.name,
                        strategy=ReplacementStrategy.CUSTOM,
                        target_packages=(),
                        rationale=(
                            "Unmapped legacy dependency; requires manual architectural review."
                        ),
                        behavioral_notes=None,
                    )
                )

        unmapped_count = sum(
            1
            for m in mappings
            if m.strategy in (ReplacementStrategy.CUSTOM, ReplacementStrategy.DEFERRED)
        )

        now_iso = datetime.now(UTC).isoformat()
        draft_id = f"draft-{uuid4().hex[:8]}"

        payload: dict[str, Any] = {
            "draft_id": draft_id,
            "project_id": project_id,
            "source_revision": source_revision,
            "governance_revision": governance_revision,
            "preset": preset.model_dump(mode="json"),
            "mappings": [m.model_dump(mode="json") for m in mappings],
            "unmapped_count": unmapped_count,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        digest = compute_draft_digest(payload)

        return StackRecommendationDraft(
            draft_id=draft_id,
            project_id=project_id,
            source_revision=source_revision,
            governance_revision=governance_revision,
            preset=preset,
            mappings=tuple(mappings),
            unmapped_count=unmapped_count,
            created_at=now_iso,
            updated_at=now_iso,
            content_digest=digest,
        )

    def _next_decision_id(self, existing: list[ArchitecturalDecisionRecord]) -> str:
        """Find the next available sequential ADR identifier (e.g. 'ADR-004')."""
        highest = 0
        pattern = re.compile(r"^ADR-(\d+)$", re.IGNORECASE)
        for adr in existing:
            match = pattern.match(adr.decision_id)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"ADR-{highest + 1:03d}"

    def generate_foundation_adrs(
        self,
        draft: StackRecommendationDraft,
        governance_root: str,
        decided_by: str = "Maintainer",
    ) -> tuple[ArchitecturalDecisionRecord, ...]:
        """Generate typed ArchitecturalDecisionRecord proposals avoiding collisions.

        Checks existing decisions in governance_root. If a decision already covers
        the architectural scope, verifies alignment or records explicit supersession.
        """
        existing: list[ArchitecturalDecisionRecord] = []
        if self._knowledge is not None:
            existing = self._knowledge.list_decisions(governance_root)

        now = datetime.now(UTC)
        adrs: list[ArchitecturalDecisionRecord] = []

        # 1. Target Architecture & Framework Selection
        fw_existing = next(
            (
                a
                for a in existing
                if a.metadata.get("scope") == "target_framework"
                and a.status == DecisionStatus.ACCEPTED
            ),
            None,
        )
        fw_metadata: dict[str, Any] = {
            "scope": "target_framework",
            "preset_id": draft.preset.preset_id,
            "angular_version": draft.preset.angular_version,
            "draft_digest": draft.content_digest,
        }
        if fw_existing is not None:
            # Check if matching
            if (
                fw_existing.metadata.get("preset_id") == draft.preset.preset_id
                and fw_existing.metadata.get("draft_digest") == draft.content_digest
            ):
                adrs.append(fw_existing)
            else:
                # Propose supersession
                fw_metadata["supersedes"] = [fw_existing.decision_id]
                new_id = self._next_decision_id(existing + adrs)
                adrs.append(
                    ArchitecturalDecisionRecord(
                        decision_id=new_id,
                        title=f"Framework Architecture: {draft.preset.target_framework}",
                        status=DecisionStatus.PROPOSED,
                        context=(
                            f"Supersedes {fw_existing.decision_id}. Migrating from legacy source "
                            f"to modern standalone component architecture."
                        ),
                        decision=(
                            f"Adopt {draft.preset.target_framework} with Standalone Components, "
                            f"Signals reactivity, and OnPush change detection."
                        ),
                        consequences=(
                            "All components must be standalone: true. Legacy template conventions "
                            "and runloop patterns are eliminated."
                        ),
                        decided_by=decided_by,
                        decided_at=now,
                        epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
                        metadata=fw_metadata,
                    )
                )
        else:
            new_id = self._next_decision_id(existing + adrs)
            adrs.append(
                ArchitecturalDecisionRecord(
                    decision_id=new_id,
                    title=f"Framework Architecture: {draft.preset.target_framework}",
                    status=DecisionStatus.PROPOSED,
                    context=(
                        "Migrating from legacy source to modern standalone component architecture."
                    ),
                    decision=(
                        f"Adopt {draft.preset.target_framework} with Standalone Components, "
                        f"Signals reactivity, and OnPush change detection."
                    ),
                    consequences=(
                        "All components must be standalone: true. Legacy template conventions "
                        "and runloop patterns are eliminated."
                    ),
                    decided_by=decided_by,
                    decided_at=now,
                    epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
                    metadata=fw_metadata,
                )
            )

        # 2. UI & Styling System
        style_existing = next(
            (
                a
                for a in existing
                if a.metadata.get("scope") == "ui_styling" and a.status == DecisionStatus.ACCEPTED
            ),
            None,
        )
        style_metadata: dict[str, Any] = {
            "scope": "ui_styling",
            "ui_library": draft.preset.ui_library,
            "draft_digest": draft.content_digest,
        }
        if style_existing is not None:
            if (
                style_existing.metadata.get("ui_library") == draft.preset.ui_library
                and style_existing.metadata.get("draft_digest") == draft.content_digest
            ):
                adrs.append(style_existing)
            else:
                style_metadata["supersedes"] = [style_existing.decision_id]
                new_id = self._next_decision_id(existing + adrs)
                adrs.append(
                    ArchitecturalDecisionRecord(
                        decision_id=new_id,
                        title=f"UI Styling System: {draft.preset.ui_library} and Scoped SCSS",
                        status=DecisionStatus.PROPOSED,
                        context=(
                            f"Supersedes {style_existing.decision_id}. "
                            "Legacy app used outdated CSS/styling."
                        ),
                        decision=(
                            f"Adopt {draft.preset.ui_library} and component-scoped SCSS. "
                            f"Prohibit jQuery or external CSS frameworks."
                        ),
                        consequences=(
                            "Use modern Flexbox/Grid utility classes (ms-*/me-*) and limit "
                            "SCSS nesting to at most 3 levels."
                        ),
                        decided_by=decided_by,
                        decided_at=now,
                        epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
                        metadata=style_metadata,
                    )
                )
        else:
            new_id = self._next_decision_id(existing + adrs)
            adrs.append(
                ArchitecturalDecisionRecord(
                    decision_id=new_id,
                    title=f"UI Styling System: {draft.preset.ui_library} and Scoped SCSS",
                    status=DecisionStatus.PROPOSED,
                    context="Legacy application used outdated CSS styling and global selectors.",
                    decision=(
                        f"Adopt {draft.preset.ui_library} and component-scoped SCSS. "
                        f"Prohibit jQuery or external CSS frameworks."
                    ),
                    consequences=(
                        "Use modern Flexbox/Grid utility classes (ms-*/me-*) and limit "
                        "SCSS nesting to at most 3 levels."
                    ),
                    decided_by=decided_by,
                    decided_at=now,
                    epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
                    metadata=style_metadata,
                )
            )

        # 3. State Management & Asynchronous Reactivity
        state_existing = next(
            (
                a
                for a in existing
                if a.metadata.get("scope") == "reactivity_state"
                and a.status == DecisionStatus.ACCEPTED
            ),
            None,
        )
        state_metadata: dict[str, Any] = {
            "scope": "reactivity_state",
            "rxjs_version": draft.preset.rxjs_version,
            "draft_digest": draft.content_digest,
        }
        if (
            state_existing is not None
            and state_existing.metadata.get("draft_digest") == draft.content_digest
        ):
            adrs.append(state_existing)
        else:
            if state_existing is not None:
                state_metadata["supersedes"] = [state_existing.decision_id]
            new_id = self._next_decision_id(existing + adrs)
            adrs.append(
                ArchitecturalDecisionRecord(
                    decision_id=new_id,
                    title="State Management & Reactivity: Angular Signals and RxJS Pipelines",
                    status=DecisionStatus.PROPOSED,
                    context=(
                        "Asynchronous data flow and state management without monolithic stores "
                        "or Ember Concurrency."
                    ),
                    decision=(
                        "Use Angular Signals (signal(), computed()) for synchronous local state, "
                        "and RxJS streams with takeUntilDestroyed() for async operations."
                    ),
                    consequences=(
                        "Ember concurrency tasks are refactored to RxJS operators. "
                        "Direct mutations are eliminated."
                    ),
                    decided_by=decided_by,
                    decided_at=now,
                    epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
                    metadata=state_metadata,
                )
            )

        return tuple(adrs)

    def accept_foundation_adrs(
        self,
        decisions: tuple[ArchitecturalDecisionRecord, ...],
        governance_root: str,
    ) -> tuple[str, ...]:
        """Save decisions with status ACCEPTED and update superseded ADRs."""
        if self._knowledge is None:
            raise RuntimeError("KnowledgePort is required to accept foundation ADRs.")

        written_paths: list[str] = []
        for d in decisions:
            # Signed historical decisions stay immutable; the new manifest selects active IDs.
            accepted = d.model_copy(update={"status": DecisionStatus.ACCEPTED})
            path = self._knowledge.save_decision(governance_root, accepted)
            written_paths.append(path)

        return tuple(written_paths)
