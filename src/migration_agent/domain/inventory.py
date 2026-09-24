"""Typed, framework-neutral repository inventory contracts."""

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InventoryModel(BaseModel):
    """Immutable base model for deterministic inventory data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FileCategory(StrEnum):
    """Kinds of web-project files collected by deterministic discovery."""

    BUILD_CONFIG = "build_config"
    LOCKFILE = "lockfile"
    MANIFEST = "manifest"
    SOURCE = "source"
    STYLE = "style"
    TEMPLATE = "template"
    TEST = "test"


class DependencyScope(StrEnum):
    """Supported JavaScript manifest dependency sections."""

    DEVELOPMENT = "development"
    OPTIONAL = "optional"
    PEER = "peer"
    RUNTIME = "runtime"


class RepositoryDescriptor(InventoryModel):
    """Identity of the repository selected for inspection."""

    name: str
    root: Path


class InspectedTextFile(InventoryModel):
    """An eligible text file available to deterministic analyzers."""

    path: str
    category: FileCategory
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: str = Field(exclude=True, repr=False)


class InventoryFile(InventoryModel):
    """Persistable metadata for one eligible repository file."""

    path: str
    category: FileCategory
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExclusionSummary(InventoryModel):
    """Aggregate exclusions that avoid disclosing skipped secret-like paths."""

    binary_files: int = Field(default=0, ge=0)
    ignored_entries: int = Field(default=0, ge=0)
    outside_root_entries: int = Field(default=0, ge=0)
    oversized_files: int = Field(default=0, ge=0)
    secret_like_files: int = Field(default=0, ge=0)
    symlink_entries: int = Field(default=0, ge=0)
    unreadable_entries: int = Field(default=0, ge=0)


class RepositorySnapshot(InventoryModel):
    """Read-only filesystem inspection result used inside the application."""

    repository: RepositoryDescriptor
    files: tuple[InspectedTextFile, ...]
    exclusions: ExclusionSummary


class FrameworkEvidence(InventoryModel):
    """One repository-backed signal supporting framework detection."""

    path: str
    kind: str
    description: str
    weight: float = Field(gt=0.0, le=1.0)


class FrameworkFingerprint(InventoryModel):
    """A detected framework with deterministic confidence and evidence."""

    framework_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[FrameworkEvidence, ...]


class Dependency(InventoryModel):
    """A dependency declared in a supported manifest."""

    name: str
    version_spec: str
    scope: DependencyScope
    manifest_path: str


class PackageBoundary(InventoryModel):
    """A package manifest and its repository-relative package root."""

    path: str
    manifest_path: str
    declared_workspace: bool


class InventoryIssue(InventoryModel):
    """A non-fatal deterministic discovery problem."""

    code: str
    path: str
    message: str


class ProjectInventory(InventoryModel):
    """Stable machine-readable inventory produced without an LLM."""

    schema_version: Literal[1] = 1
    repository: RepositoryDescriptor
    files: tuple[InventoryFile, ...]
    dependencies: tuple[Dependency, ...]
    package_boundaries: tuple[PackageBoundary, ...]
    frameworks: tuple[FrameworkFingerprint, ...]
    exclusions: ExclusionSummary
    issues: tuple[InventoryIssue, ...]
