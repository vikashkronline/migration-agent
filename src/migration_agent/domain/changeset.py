"""Domain models for ChangeSets, working-tree fingerprints, and controlled apply states."""

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.canonical import compute_canonical_digest


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


def compute_worktree_fingerprint(
    repo_root: Path | str,
    file_paths: list[str] | None = None,
) -> str:
    """Calculate deterministic SHA-256 fingerprint over target repository working tree.

    If file_paths is None, walks all non-ignored, non-hidden regular files under repo_root.
    Any modified, added, or deleted file changes the fingerprint.
    """
    root = Path(repo_root).resolve()
    hasher = hashlib.sha256()

    if file_paths is not None:
        target_paths = sorted(file_paths)
    else:
        found_paths: list[str] = []
        for path in root.rglob("*"):
            if path.is_file() and not any(
                part.startswith((".", "node_modules")) for part in path.parts
            ):
                rel = path.relative_to(root).as_posix()
                found_paths.append(rel)
        target_paths = sorted(found_paths)

    for rel_path in target_paths:
        full_path = root / rel_path
        if full_path.is_file():
            try:
                content = full_path.read_bytes()
                file_hash = hashlib.sha256(content).hexdigest()
                hasher.update(f"{rel_path}:{file_hash}\n".encode())
            except OSError:
                hasher.update(f"{rel_path}:unreadable\n".encode())
        else:
            hasher.update(f"{rel_path}:absent\n".encode())

    return f"sha256:{hasher.hexdigest()}"


def compute_changeset_digest(changeset: ChangeSet) -> str:
    """Calculate RFC 8785 canonical metadata digest of a ChangeSet."""
    canonical_payload = {
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
    return compute_canonical_digest(canonical_payload)
