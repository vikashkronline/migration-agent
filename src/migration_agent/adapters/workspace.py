"""Local isolated staging workspace adapter implementing WorkspacePort."""

import contextlib
import os
import shutil
from pathlib import Path

from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.domain import ChangeSet, FileMode, FileOperation
from migration_agent.domain.host_workflow import normalized_path
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.ports import WorkspacePort


class LocalWorkspaceAdapter(WorkspacePort):
    """Manages isolated staging workspaces under user-data staging roots with path containment."""

    def create_staging(
        self,
        run_id: str,
        source_root: Path,
        staging_root: Path,
        *,
        include_hidden: bool = False,
    ) -> Path:
        """Create an isolated staging workspace by copying eligible files from source repository."""
        src_path = Path(source_root).resolve()
        stg_root = Path(staging_root).resolve()

        if not src_path.is_dir():
            raise ValueError(
                f"Source repository root '{src_path}' does not exist or is not a directory."
            )

        workspace_path = (stg_root / run_id).resolve()

        from migration_agent.application.host_proposals import opaque_id

        opaque_id(run_id)

        # Path containment validation
        if workspace_path.parent != stg_root:
            raise ValueError(f"Staging path '{workspace_path}' escapes staging root '{stg_root}'.")

        # Reject overlapping unsafe paths
        if (
            workspace_path == src_path
            or str(workspace_path).startswith(str(src_path) + os.sep)
            or str(src_path).startswith(str(workspace_path) + os.sep)
        ):
            raise ValueError(
                f"Staging path '{workspace_path}' overlaps source repository '{src_path}'."
            )

        if workspace_path.exists():
            shutil.rmtree(workspace_path, ignore_errors=True)
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Copy non-ignored, non-secret files with symlink defense
        for root, dirs, files in os.walk(src_path, followlinks=False):
            dirs[:] = sorted(
                d
                for d in dirs
                if (include_hidden or not d.startswith("."))
                and d
                not in {
                    ".git",
                    ".agent",
                    ".angular",
                    "node_modules",
                    "dist",
                    "build",
                    "coverage",
                    "venv",
                }
            )
            for name in dirs:
                validate_repository_path(
                    src_path, (Path(root) / name).relative_to(src_path).as_posix()
                )
            rel_dir = Path(root).relative_to(src_path)
            target_dir = workspace_path / rel_dir
            target_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                if (
                    file.startswith(".") and not include_hidden
                ) or RedactionPolicy.is_sensitive_path(Path(file)):
                    continue
                file_src = Path(root) / file
                file_dest = target_dir / file
                relative = file_src.relative_to(src_path).as_posix()
                try:
                    content = read_repository_text(src_path, relative)
                    file_dest.write_bytes(content.encode("utf-8"))
                except ValueError as err:
                    if "oversized or binary file" in str(err):
                        validate_repository_path(src_path, relative)
                        raw = file_src.read_bytes()
                        if len(raw) <= 10_000_000:
                            file_dest.write_bytes(raw)
                    else:
                        raise

        return workspace_path

    def apply_changeset(
        self,
        workspace_path: Path,
        changeset: ChangeSet,
    ) -> None:
        """Materialize proposed ChangeSet mutations directly in the isolated workspace."""
        base_dir = Path(workspace_path).resolve()

        for change in changeset.changes:
            target = validate_repository_path(base_dir, normalized_path(change.path))
            if not target.is_relative_to(base_dir):
                raise ValueError(
                    f"Change path '{change.path}' escapes staging workspace '{base_dir}'."
                )

            if change.operation == FileOperation.DELETE:
                if target.exists():
                    target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                content = change.content_bytes or b""
                target.write_bytes(content)
                if change.file_mode == FileMode.EXECUTABLE:
                    with contextlib.suppress(OSError):
                        target.chmod(0o755)
                else:
                    with contextlib.suppress(OSError):
                        target.chmod(0o644)

    def cleanup_staging(
        self,
        workspace_path: Path,
    ) -> None:
        """Safely destroy an isolated staging workspace."""
        ws_path = Path(workspace_path).resolve()
        if ws_path.exists():
            shutil.rmtree(ws_path, ignore_errors=True)
