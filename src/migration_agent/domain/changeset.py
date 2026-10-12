"""Domain models for ChangeSets, working-tree fingerprints, and controlled apply states."""

import hashlib
import os
import stat
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.redaction import RedactionPolicy


class FileOperation(StrEnum):
    """File mutation operations supported within a ChangeSet."""

    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


class FileMode(StrEnum):
    """POSIX file permission modes."""

    STANDARD = "0644"
    EXECUTABLE = "0755"


class FileChange(BaseModel):
    """One discrete file mutation within a ChangeSet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)  # Normalized repository-relative POSIX path
    operation: FileOperation
    file_mode: FileMode = FileMode.STANDARD
    content_digest: str = Field(default="")  # SHA-256 of raw file bytes
    old_path: str | None = None
    content_bytes: bytes | None = Field(default=None, repr=False)
    base_content_bytes: bytes | None = Field(default=None, repr=False)


class DestinationBinding(BaseModel):
    """Exact separate destination reviewed for a source-preserving migration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    root: str = Field(min_length=1, max_length=4096)
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @property
    def digest(self) -> str:
        return compute_canonical_digest(self)


class ChangeSet(BaseModel):
    """Deterministic, immutable container representing proposed code mutations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    changeset_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    base_revision: str = Field(min_length=1)
    worktree_fingerprint: str = Field(min_length=1)
    changes: tuple[FileChange, ...] = Field(default_factory=tuple)
    changeset_digest: str = Field(default="")
    destination: DestinationBinding | None = None
    architecture_digest: str | None = None


class ApplyStatus(StrEnum):
    """Terminal and transitional states of the ADR-8 Controlled Apply Protocol."""

    APPLIED = "APPLIED"
    BASE_CHANGED = "BASE_CHANGED"
    ROLLED_BACK = "ROLLED_BACK"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class ApplyResult(BaseModel):
    """Immutable outcome of executing the controlled apply protocol."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ApplyStatus
    changeset_id: str = Field(min_length=1)
    applied_paths: tuple[str, ...] = Field(default_factory=tuple)
    backup_snapshot_path: str | None = None
    diagnostics: tuple[str, ...] = Field(default_factory=tuple)
    recovery_details: dict[str, Any] | None = None


def compute_file_sha256(content: bytes) -> str:
    """Compute standard SHA-256 digest over raw byte content."""
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _fingerprint_target(root: Path, relative: Path) -> Path:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ValueError("SOURCE_PATH_REJECTED: fingerprint cannot follow links.")
        if current.exists():
            attributes = getattr(current.lstat(), "st_file_attributes", 0)
            if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                raise ValueError("SOURCE_PATH_REJECTED: fingerprint reparse point.")
    if not current.resolve().is_relative_to(root):
        raise ValueError("SOURCE_PATH_REJECTED: fingerprint escapes the repository.")
    return current


def compute_worktree_fingerprint(
    repo_root: Path | str,
    file_paths: list[str] | None = None,
    max_file_bytes: int = 5_000_000,
    max_total_bytes: int = 50_000_000,
) -> str:
    """Calculate deterministic SHA-256 fingerprint over target repository working tree.

    If file_paths is None, walks all non-ignored, non-hidden regular files under repo_root.
    Any modified, added, or deleted file changes the fingerprint.
    """
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError("SOURCE_PATH_REJECTED: fingerprint requires an existing directory.")
    hasher = hashlib.sha256()

    if file_paths is not None:
        target_paths = sorted(file_paths)
    else:
        found_paths: list[str] = []
        ignored = {"node_modules", "build", "coverage", "dist", "env", "out", "tmp", "venv"}
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(
                name for name in dirs if not name.startswith(".") and name.casefold() not in ignored
            )
            for name in dirs:
                child = Path(directory) / name
                if child.is_symlink() or child.is_junction():
                    raise ValueError("SOURCE_PATH_REJECTED: fingerprint cannot follow links.")
            for name in sorted(names):
                path = Path(directory) / name
                if name.startswith(".") or RedactionPolicy.is_sensitive_path(path):
                    continue
                found_paths.append(path.relative_to(root).as_posix())
                if len(found_paths) > 10_000:
                    raise ValueError("INSPECTION_TOO_LARGE: fingerprint exceeds the file budget.")
        target_paths = sorted(found_paths)

    total_bytes = 0
    if len(target_paths) > 10_000:
        raise ValueError("INSPECTION_TOO_LARGE: fingerprint exceeds the file budget.")
    for rel_path in target_paths:
        relative = Path(rel_path)
        if (
            relative == Path(".")
            or relative.anchor
            or relative.drive
            or ".." in relative.parts
            or "\x00" in rel_path
        ):
            raise ValueError("SOURCE_PATH_REJECTED: invalid fingerprint path.")
        if RedactionPolicy.is_sensitive_path(relative):
            continue
        full_path = _fingerprint_target(root, relative)
        if full_path.is_file():
            before = full_path.stat(follow_symlinks=False)
            if before.st_size > max_file_bytes:
                raise ValueError("SOURCE_READ_REJECTED: fingerprint file exceeds the byte limit.")
            total_bytes += before.st_size
            if total_bytes > max_total_bytes:
                raise ValueError("INSPECTION_TOO_LARGE: fingerprint exceeds the byte budget.")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(full_path, flags), "rb") as file_handle:
                opened = os.fstat(file_handle.fileno())
                _fingerprint_target(root, relative)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise ValueError("SOURCE_READ_REJECTED: fingerprint file changed during open.")
                content = file_handle.read(max_file_bytes + 1)
                after = os.fstat(file_handle.fileno())
                _fingerprint_target(root, relative)
                if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                    raise ValueError("SOURCE_READ_REJECTED: fingerprint input changed during read.")
            if len(content) > max_file_bytes:
                raise ValueError("SOURCE_READ_REJECTED: fingerprint file exceeds the byte limit.")
            if RedactionPolicy().contains_secret(content.decode("utf-8", errors="ignore")):
                raise ValueError("SECRET_CONTENT_REJECTED: fingerprint input contains credentials.")
            file_hash = hashlib.sha256(content).hexdigest()
            hasher.update(f"{relative.as_posix()}:{file_hash}\n".encode())
        else:
            hasher.update(f"{relative.as_posix()}:absent\n".encode())

    return f"sha256:{hasher.hexdigest()}"


def compute_changeset_digest(changeset: ChangeSet) -> str:
    """Calculate RFC 8785 canonical metadata digest of a ChangeSet."""
    canonical_payload: dict[str, Any] = {
        "base_revision": changeset.base_revision,
        "changes": [
            {
                "content_digest": ch.content_digest,
                "file_mode": ch.file_mode.value,
                "old_path": ch.old_path,
                "operation": ch.operation.value,
                "path": ch.path,
            }
            for ch in sorted(changeset.changes, key=lambda c: c.path)
        ],
        "changeset_id": changeset.changeset_id,
        "plan_id": changeset.plan_id,
        "step_id": changeset.step_id,
        "worktree_fingerprint": changeset.worktree_fingerprint,
    }
    if changeset.destination is not None:
        canonical_payload["destination"] = changeset.destination.model_dump(mode="json")
        canonical_payload["destination_base"] = [
            {
                "path": change.path,
                "digest": compute_file_sha256(change.base_content_bytes)
                if change.base_content_bytes is not None
                else None,
            }
            for change in sorted(changeset.changes, key=lambda change: change.path)
        ]
    if changeset.architecture_digest is not None:
        canonical_payload["architecture_digest"] = changeset.architecture_digest
    return compute_canonical_digest(canonical_payload)
