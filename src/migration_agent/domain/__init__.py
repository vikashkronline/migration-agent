"""Framework-neutral migration domain models."""

from migration_agent.domain.analysis import (
    AnalysisFinding,
    AnalysisResult,
    EvidenceReference,
    EvidenceStatus,
    FindingCategory,
    FindingSeverity,
)
from migration_agent.domain.canonical import (
    canonical_json_dumps,
    compute_canonical_digest,
)
from migration_agent.domain.inventory import (
    Dependency,
    DependencyScope,
    ExclusionSummary,
    FileCategory,
    FrameworkEvidence,
    FrameworkFingerprint,
    InspectedTextFile,
    InventoryFile,
    InventoryIssue,
    PackageBoundary,
    ProjectInventory,
    RepositoryDescriptor,
    RepositorySnapshot,
)
from migration_agent.domain.models import MigrationRequest
from migration_agent.domain.planning import (
    ApprovalSignature,
    AssuranceLevel,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    StepRisk,
    compute_plan_digest,
    verify_approval,
)

__all__ = [
    "AnalysisFinding",
    "AnalysisResult",
    "ApprovalSignature",
    "AssuranceLevel",
    "Dependency",
    "DependencyScope",
    "EvidenceReference",
    "EvidenceStatus",
    "ExclusionSummary",
    "FileCategory",
    "FindingCategory",
    "FindingSeverity",
    "FrameworkEvidence",
    "FrameworkFingerprint",
    "InspectedTextFile",
    "InventoryFile",
    "InventoryIssue",
    "MigrationPlan",
    "MigrationRequest",
    "MigrationStep",
    "PackageBoundary",
    "PlanStatus",
    "ProjectInventory",
    "RepositoryDescriptor",
    "RepositorySnapshot",
    "StepRisk",
    "canonical_json_dumps",
    "compute_canonical_digest",
    "compute_plan_digest",
    "verify_approval",
]
