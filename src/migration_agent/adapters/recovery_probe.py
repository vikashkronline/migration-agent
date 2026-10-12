"""Bounded disk comparison for interrupted apply; never mutates source files."""

from pathlib import Path
from typing import Literal

from migration_agent.adapters.controlled_files import destination_fingerprint
from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.domain.changeset import (
    ChangeSet,
    FileOperation,
    compute_changeset_digest,
    compute_file_sha256,
    compute_worktree_fingerprint,
)
from migration_agent.domain.host_workflow import WorkflowRecord, normalized_path


class LocalRecoveryProbe:
    def __init__(self, root: Path, destination: Path | None = None) -> None:
        self.root = root.resolve()
        self.destination = destination.resolve() if destination else None

    def classify(
        self, record: WorkflowRecord, changeset: ChangeSet
    ) -> Literal["target", "base", "ambiguous"]:
        if (
            Path(record.source_root).resolve() != self.root
            or compute_changeset_digest(changeset) != record.changeset_digest
            or not record.backups
            or {entry.path for entry in record.backups}
            != {change.path for change in changeset.changes}
        ):
            return "ambiguous"
        if record.destination != changeset.destination or (
            record.destination is not None
            and (self.destination is None or record.destination.root != str(self.destination))
        ):
            return "ambiguous"
        root = self.destination if record.destination else self.root
        if root is None:
            return "ambiguous"
        try:
            if (
                record.destination
                and compute_worktree_fingerprint(self.root) != record.worktree_fingerprint
            ):
                return "ambiguous"
            current: dict[str, str | None] = {}
            for change in changeset.changes:
                path = validate_repository_path(root, normalized_path(change.path))
                current[change.path] = (
                    compute_file_sha256(read_repository_text(root, change.path).encode("utf-8"))
                    if path.exists()
                    else None
                )
            if all(
                current[change.path]
                == (None if change.operation == FileOperation.DELETE else change.content_digest)
                for change in changeset.changes
            ):
                if (
                    record.destination
                    and destination_fingerprint(root) != record.staging_fingerprint
                ):
                    return "ambiguous"
                return "target"
            if all(
                current[entry.path] == (entry.digest if entry.existed else None)
                for entry in record.backups
            ):
                if (
                    record.destination
                    and destination_fingerprint(root) != record.destination.fingerprint
                ):
                    return "ambiguous"
                return "base"
        except (ValueError, OSError):
            pass
        return "ambiguous"
