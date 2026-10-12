"""Domain models for stack analysis, recommendation presets, and dependency mappings."""

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.knowledge import ArchitecturalDecisionRecord


class LibraryCategory(StrEnum):
    FRAMEWORK = "framework"
    DATA_LAYER = "data_layer"
    ROUTING = "routing"
    UI_STYLING = "ui_styling"
    UTILITY = "utility"
    BUILD_TOOL = "build_tool"
    TEST_RUNNER = "test_runner"
    OTHER = "other"


class ReplacementStrategy(StrEnum):
    REPLACE = "replace"  # Direct modern package equivalent
    NATIVE = "native"  # Language/framework feature (still tracks required runtime packages)
    KEEP = "keep"  # Supported as-is in modern stack (e.g. lodash-es)
    REMOVE = "remove"  # Obsolete/deprecated in modern architecture (e.g. bower, jquery)
    CUSTOM = "custom"  # Proprietary or unmapped; requires manual architectural review
    DEFERRED = "deferred"  # Excluded from initial foundation; migrated in later phase


class PackageCoordinate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    version_spec: str
    is_dev: bool = False


class LegacyDependency(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    declared_version: str
    resolved_version: str | None = None
    category: LibraryCategory
    is_dev: bool = False
    manifest_path: str
    usage_evidence: tuple[str, ...] = Field(default_factory=tuple)


class PackageMappingOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    legacy_name: str
    strategy: ReplacementStrategy
    target_packages: tuple[PackageCoordinate, ...] = Field(default_factory=tuple)
    rationale: str
    behavioral_notes: str | None = None


class TargetStackPreset(BaseModel):
    model_config = ConfigDict(frozen=True)

    preset_id: str
    label: str
    description: str
    target_framework: str  # e.g. "Angular 17.3.x (Standalone)"
    angular_version: str  # "17.3.12"
    typescript_version: str  # "~5.4.5"
    rxjs_version: str  # "~7.8.1"
    ui_library: str  # "Bootstrap 5.3.3 Utilities"
    test_framework: str  # "Vitest 1.6.x + @angular/build"
    directory_structure: dict[str, str] = Field(default_factory=dict)  # Path -> Semantic purpose
    base_dependencies: tuple[PackageCoordinate, ...] = Field(default_factory=tuple)
    base_dev_dependencies: tuple[PackageCoordinate, ...] = Field(default_factory=tuple)
    validation_catalog: Literal["node-v1", "node-vitest-v1", "node-angular-v21"] = "node-vitest-v1"


class StackRecommendationDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id: str
    project_id: str
    source_revision: str
    governance_revision: str
    preset: TargetStackPreset
    mappings: tuple[PackageMappingOutcome, ...] = Field(default_factory=tuple)
    unmapped_count: int = 0
    created_at: str
    updated_at: str
    content_digest: str


class StackAnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_framework: str
    dependencies: tuple[LegacyDependency, ...] = Field(default_factory=tuple)
    existing_adrs: tuple[ArchitecturalDecisionRecord, ...] = Field(default_factory=tuple)
    detected_presets: tuple[TargetStackPreset, ...] = Field(default_factory=tuple)
    unmapped_dependencies: tuple[LegacyDependency, ...] = Field(default_factory=tuple)


class StackRecommendationView(StackRecommendationDraft):
    decisions: tuple[ArchitecturalDecisionRecord, ...] = Field(default=(), max_length=16)


class FoundationStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    plan_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    step_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class FoundationTaskChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan_id: str
    step_id: str
    title: str
    state: str


class StackReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ready: bool
    architecture_accepted: bool
    foundation_staged: bool
    foundation_validated: bool
    foundation_published: bool
    accepted_decision_ids: tuple[str, ...]
    ready_for_migration: bool
    target_root: str | None
    foundation_tasks: tuple[FoundationTaskChoice, ...] = ()


class ArchitectureManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    source_revision: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    source_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    draft_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    preset_id: str
    decision_digests: dict[str, str] = Field(min_length=3, max_length=16)

    @field_validator("decision_digests")
    @classmethod
    def validate_decisions(cls, value: dict[str, str]) -> dict[str, str]:
        for path, digest in value.items():
            if not re.fullmatch(r"\.agent/decisions/[A-Za-z0-9_-]+\.md", path):
                raise ValueError("Architecture decisions require bounded repository paths.")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise ValueError("Architecture decisions require SHA-256 content digests.")
        return value


def compute_draft_digest(draft_payload: dict[str, Any] | BaseModel) -> str:
    """Compute the RFC 8785 canonical digest over a stack recommendation draft."""
    if isinstance(draft_payload, BaseModel):
        data = draft_payload.model_dump(mode="json")
    else:
        data = dict(draft_payload)
    # Exclude dynamic metadata if present during digest calculation
    data.pop("content_digest", None)
    return compute_canonical_digest(data)
