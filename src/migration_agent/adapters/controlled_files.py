"""Guarded staging and transaction-like source apply with per-mutation fencing."""

import difflib
import hashlib
import os
import uuid
from collections.abc import Callable
from pathlib import Path

from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.domain.changeset import (
    ApplyResult,
    ApplyStatus,
    ChangeSet,
    DestinationBinding,
    FileOperation,
    compute_file_sha256,
    compute_worktree_fingerprint,
)
from migration_agent.domain.host_workflow import BackupEntry, WorkflowRecord, normalized_path
from migration_agent.domain.redaction import RedactionPolicy


def destination_fingerprint(root: Path) -> str:
    """Include target configuration files without inspecting credentials or build output."""
    for parent in (root, *root.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("DESTINATION_UNSAFE: target roots cannot traverse links.")
    if not root.exists():
        return compute_file_sha256(b"")
    if not root.is_dir():
        raise ValueError("DESTINATION_UNSAFE: target must be a local directory.")
    paths: list[str] = []
    ignored = {".git", ".angular", "node_modules", "dist", "coverage"}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name.casefold() not in ignored)
        for name in dirs:
            child = Path(directory) / name
            if child.is_symlink() or child.is_junction():
                raise ValueError("DESTINATION_UNSAFE: target cannot contain links.")
        for name in sorted(files):
            path = Path(directory) / name
            if RedactionPolicy.is_sensitive_path(path):
                raise ValueError(
                    "DESTINATION_UNSAFE: remove credentials from the target workspace."
                )
            paths.append(path.relative_to(root).as_posix())
    return compute_worktree_fingerprint(root, paths)


class LocalControlledFiles:
    def __init__(
        self,
        source: Path,
        staging: Path,
        state: Path,
        destination: Path | None = None,
        require_destination: bool = False,
    ) -> None:
        self.source = source.resolve()
        self.staging = staging.resolve()
        self.state = state.resolve()
        self.destination = destination.absolute() if destination is not None else None
        self.require_destination = require_destination
        if self.destination is not None:
            destination_fingerprint(self.destination)
            self.destination = self.destination.resolve()
            for root in (self.source, self.staging, self.state):
                if self.destination.is_relative_to(root) or root.is_relative_to(self.destination):
                    raise ValueError(
                        "UNSAFE_ROOT_OVERLAP: target must be separate from source/state/staging."
                    )

    @property
    def write_root(self) -> Path:
        return self.destination or self.source

    @property
    def destination_root(self) -> str | None:
        return str(self.destination) if self.destination else None

    def lock_identity(self, project_id: str) -> str:
        if self.destination is None:
            return project_id
        return (
            "target-" + hashlib.sha256(os.path.normcase(str(self.destination)).encode()).hexdigest()
        )

    def bind_destination(self, changeset: ChangeSet) -> ChangeSet:
        if self.destination is None:
            if self.require_destination:
                raise ValueError(
                    "DESTINATION_REQUIRED: select a separate target in Settings > Directories "
                    "before staging."
                )
            return changeset
        base = DestinationBinding(
            root=str(self.destination), fingerprint=destination_fingerprint(self.destination)
        )
        changes = []
        for change in changeset.changes:
            target = (
                self._target(self.destination, change.path) if self.destination.exists() else None
            )
            old = (
                read_repository_text(self.destination, change.path).encode()
                if target is not None and target.exists()
                else None
            )
            if old is not None and len(old) > 32768:
                raise ValueError("REVIEW_TOO_LARGE: target base file exceeds the review budget.")
            operation = change.operation
            if operation != FileOperation.DELETE:
                operation = FileOperation.MODIFY if old is not None else FileOperation.CREATE
            elif old is None:
                raise ValueError("FILE_OPERATION_MISMATCH: deleted target file does not exist.")
            changes.append(
                change.model_copy(update={"operation": operation, "base_content_bytes": old})
            )
        if destination_fingerprint(self.destination) != base.fingerprint:
            raise ValueError("DESTINATION_CHANGED: target changed while binding the proposal.")
        return changeset.model_copy(update={"destination": base, "changes": tuple(changes)})

    def verify_destination(self, changeset: ChangeSet) -> None:
        if changeset.destination is None:
            if self.destination is not None or self.require_destination:
                raise ValueError(
                    "DESTINATION_BINDING_REQUIRED: regenerate this legacy proposal "
                    "for the selected target."
                )
            return
        if self.destination is None or str(self.destination) != changeset.destination.root:
            raise ValueError(
                "DESTINATION_CHANGED: select the originally reviewed target or submit a fresh plan."
            )
        if destination_fingerprint(self.destination) != changeset.destination.fingerprint:
            raise ValueError("DESTINATION_CHANGED: inspect target changes and submit a fresh plan.")

    def _target(self, root: Path, path: str) -> Path:
        for ancestor in (root, *root.parents):
            if ancestor.is_symlink() or ancestor.is_junction():
                raise ValueError("DESTINATION_UNSAFE: mutation roots cannot traverse links.")
        normalized_path(path)
        if RedactionPolicy.is_sensitive_path(Path(path)):
            raise ValueError("PROTECTED_PATH: credential filename cannot be mutated.")
        return validate_repository_path(root, path)

    def materialize(
        self, changeset: ChangeSet, workspace_id: str, fence: Callable[[], None]
    ) -> Path:
        fence()
        compute_worktree_fingerprint(self.source)
        self.verify_destination(changeset)
        if self.write_root.exists():
            path = LocalWorkspaceAdapter().create_staging(
                workspace_id,
                self.write_root,
                self.staging,
                include_hidden=self.destination is not None,
            )
        else:
            normalized_path(workspace_id)
            path = self.staging / workspace_id
            path.mkdir(parents=True, exist_ok=False)
        for change in changeset.changes:
            fence()
            target = self._target(path, change.path)
            if change.operation == FileOperation.DELETE:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                self._target(path, change.path)
                target.write_bytes(change.content_bytes or b"")
                target.chmod(int(change.file_mode.value, 8))
        self.verify_staging(str(path), changeset)
        return path

    def verify_staging(self, path: str, changeset: ChangeSet) -> str:
        root = Path(path)
        if root.is_symlink() or root.is_junction() or root.resolve().parent != self.staging:
            raise ValueError("STAGING_PATH_INVALID: workspace is outside its configured root.")
        for change in changeset.changes:
            target = self._target(root, change.path)
            if change.operation == FileOperation.DELETE:
                if target.exists():
                    raise ValueError("STAGING_CHANGED: deleted file remains present.")
            elif (
                compute_file_sha256(read_repository_text(root, change.path).encode("utf-8"))
                != change.content_digest
            ):
                raise ValueError(
                    "STAGING_CHANGED: generated file differs from the reviewed artifact."
                )
        return (
            destination_fingerprint(root)
            if changeset.destination
            else compute_worktree_fingerprint(root)
        )

    def prepare_backup(
        self, changeset: ChangeSet, fence: Callable[[], None]
    ) -> tuple[Path, tuple[BackupEntry, ...]]:
        backup = self.state / "backups" / f"{changeset.changeset_id}-{uuid.uuid4().hex}"
        backup.mkdir(parents=True, exist_ok=False)
        entries = []
        for change in changeset.changes:
            fence()
            self.write_root.mkdir(parents=True, exist_ok=True)
            target = self._target(self.write_root, change.path)
            existed = target.exists()
            if (change.operation == FileOperation.CREATE and existed) or (
                change.operation != FileOperation.CREATE and not existed
            ):
                raise ValueError(
                    "FILE_OPERATION_MISMATCH: create/modify/delete preconditions failed."
                )
            content = (
                read_repository_text(self.write_root, change.path).encode("utf-8")
                if existed
                else None
            )
            entry = BackupEntry(
                path=change.path,
                existed=existed,
                digest=compute_file_sha256(content) if content is not None else None,
                mode=target.stat().st_mode & 0o777 if existed else 0o644,
            )
            entries.append(entry)
            if content is not None:
                saved = self._target(backup, change.path)
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(content)
        return backup, tuple(entries)

    def _write(
        self, root: Path, path: str, content: bytes, mode: int, fence: Callable[[], None]
    ) -> None:
        target = self._target(root, path)
        fence()
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self._target(root, path)
        fence()
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_TRUNC
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        with os.fdopen(os.open(target, flags, mode), "wb") as handle:
            self._target(root, path)
            fence()
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        fence()
        self._target(root, path).chmod(mode)

    def apply_files(
        self, record: WorkflowRecord, changeset: ChangeSet, fence: Callable[[], None]
    ) -> ApplyResult:
        applied: list[str] = []
        try:
            for change in changeset.changes:
                fence()
                if change.operation == FileOperation.DELETE:
                    self._target(self.write_root, change.path).unlink()
                else:
                    self._write(
                        self.write_root,
                        change.path,
                        change.content_bytes or b"",
                        int(change.file_mode.value, 8),
                        fence,
                    )
                applied.append(change.path)
            for change in changeset.changes:
                fence()
                target = self._target(self.write_root, change.path)
                if change.operation == FileOperation.DELETE:
                    if target.exists():
                        raise ValueError("POSTCONDITION_FAILED: deleted file exists.")
                elif (
                    compute_file_sha256(read_repository_text(self.write_root, change.path).encode())
                    != change.content_digest
                ):
                    raise ValueError("POSTCONDITION_FAILED: final content digest mismatch.")
            if record.destination:
                if compute_worktree_fingerprint(self.source) != record.worktree_fingerprint:
                    raise ValueError("SOURCE_CHANGED: source drifted during target publication.")
                if destination_fingerprint(self.write_root) != record.staging_fingerprint:
                    raise ValueError(
                        "POSTCONDITION_FAILED: cumulative target differs from validated staging."
                    )
            return ApplyResult(
                status=ApplyStatus.APPLIED,
                changeset_id=changeset.changeset_id,
                applied_paths=tuple(applied),
                backup_snapshot_path=record.backup_path,
            )
        except (OSError, ValueError):
            try:
                fence()
                if not record.backup_path:
                    raise ValueError("BACKUP_MISSING: cannot restore source.")
                backup = Path(record.backup_path).resolve()
                if not backup.is_relative_to(self.state / "backups"):
                    raise ValueError("BACKUP_PATH_INVALID: snapshot outside state root.")
                for entry in record.backups:
                    fence()
                    if entry.existed:
                        content = read_repository_text(backup, entry.path).encode()
                        if compute_file_sha256(content) != entry.digest:
                            raise ValueError("BACKUP_CORRUPTED: snapshot digest mismatch.")
                        self._write(self.write_root, entry.path, content, entry.mode, fence)
                    else:
                        self._target(self.write_root, entry.path).unlink(missing_ok=True)
                if (
                    destination_fingerprint(self.write_root)
                    if record.destination
                    else compute_worktree_fingerprint(self.source)
                ) != (
                    record.destination.fingerprint
                    if record.destination
                    else record.worktree_fingerprint
                ):
                    raise ValueError("ROLLBACK_FAILED: base fingerprint was not restored.")
                return ApplyResult(
                    status=ApplyStatus.ROLLED_BACK,
                    changeset_id=changeset.changeset_id,
                    backup_snapshot_path=record.backup_path,
                    diagnostics=("Apply failed; original bytes restored. Fresh review required.",),
                )
            except (OSError, ValueError):
                return ApplyResult(
                    status=ApplyStatus.RECOVERY_REQUIRED,
                    changeset_id=changeset.changeset_id,
                    applied_paths=tuple(applied),
                    backup_snapshot_path=record.backup_path,
                    diagnostics=(
                        "Apply interrupted or fencing lost; inspect backups and recover.",
                    ),
                )

    def review_diff(self, changeset: ChangeSet) -> str:
        chunks = []
        if changeset.destination:
            chunks.append(
                f"# Destination: {changeset.destination.root}\n"
                f"# Target base: {changeset.destination.fingerprint}\n"
            )
        for change in changeset.changes:
            if changeset.destination:
                old = (change.base_content_bytes or b"").decode("utf-8")
            else:
                target = self._target(self.source, change.path)
                old = read_repository_text(self.source, change.path) if target.exists() else ""
            new = (change.content_bytes or b"").decode("utf-8")
            chunks.append(
                f"# {change.operation.value} {change.path} mode={change.file_mode.value}\n"
            )
            chunks.extend(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{change.path}",
                    tofile=f"b/{change.path}",
                )
            )
        result = "".join(chunks)
        if len(result.encode()) > 65536:
            raise ValueError("REVIEW_TOO_LARGE: select a smaller bounded ChangeSet.")
        if RedactionPolicy().contains_secret(result):
            raise ValueError("SECRET_CONTENT_REJECTED: review contains credentials.")
        return result
