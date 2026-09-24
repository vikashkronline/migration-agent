"""Typed migration analysis domain contracts introduced in Phase 2."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from migration_agent.domain.inventory import InventoryModel, RepositoryDescriptor


class FindingCategory(StrEnum):
    """Broad categories for migration findings."""

    ARCHITECTURE = "architecture"
    BUILD = "build"
    COMPONENT = "component"
    DEPENDENCY = "dependency"
    OTHER = "other"
    STYLE = "style"
    TEMPLATE = "template"
    TEST = "test"


class FindingSeverity(StrEnum):
    """Impact and urgency level of a migration finding."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceStatus(StrEnum):
    """Validation status of an evidence reference against repository inventory."""

    VALID = "valid"
    INVALID_PATH = "invalid_path"
    NOT_IN_INVENTORY = "not_in_inventory"


class EvidenceReference(InventoryModel):
    """One repository-backed evidence artifact supporting an analysis finding."""

    path: str
    description: str
    line_number: int | None = Field(default=None, ge=1)
    sample: str | None = None
    status: EvidenceStatus = EvidenceStatus.VALID
    validation_note: str | None = None


class AnalysisFinding(InventoryModel):
    """A typed finding produced by migration analysis."""

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: FindingCategory
    severity: FindingSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    description: str = Field(min_length=1)
    evidence_references: tuple[EvidenceReference, ...] = ()
    unsupported_constructs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()


class AnalysisResult(InventoryModel):
    """Validated structured output of a read-only repository analysis."""

    schema_version: Literal[1] = 1
    repository: RepositoryDescriptor
    provider: str = "gemini"
    model: str
    is_dry_run: bool = True
    summary: str
    findings: tuple[AnalysisFinding, ...] = ()
    unsupported_constructs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
