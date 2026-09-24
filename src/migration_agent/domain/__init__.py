"""Framework-neutral migration domain models."""

from migration_agent.domain.analysis import (
    AnalysisFinding,
    AnalysisResult,
    EvidenceReference,
    EvidenceStatus,
    FindingCategory,
    FindingSeverity,
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

__all__ = [
    "AnalysisFinding",
    "AnalysisResult",
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
    "MigrationRequest",
    "PackageBoundary",
    "ProjectInventory",
    "RepositoryDescriptor",
    "RepositorySnapshot",
]
