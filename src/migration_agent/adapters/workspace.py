"""Local isolated staging workspace adapter implementing WorkspacePort."""

import contextlib
import os
import shutil
from pathlib import Path

from migration_agent.domain import ChangeSet, FileMode, FileOperation
from migration_agent.ports import WorkspacePort


class LocalWorkspaceAdapter(WorkspacePort):
    """Manages isolated staging workspaces under user-data staging roots with path containment."""

    def create_staging(
        self,
        run_id: str,
        source_root: Path,
        staging_root: Path,
    ) -> Path:
        """Create an isolated staging workspace by copying eligible files from source repository."""
        src_path = Path(source_root).resolve()
        stg_root = Path(staging_root).resolve()

        if not src_path.is_dir():
            raise ValueError(
                f"Source repository root '{src_path}' does not exist or is not a directory."
            )

        workspace_path = (stg_root / run_id).resolve()

        # Path containment validation
        if not str(workspace_path).startswith(str(stg_root)):
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
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
            rel_dir = Path(root).relative_to(src_path)
            target_dir = workspace_path / rel_dir
            target_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                if file.startswith("."):
                    continue
                file_src = Path(root) / file
                # Do not follow symlinks pointing outside source_root
                if file_src.is_symlink():
                    continue
                file_dest = target_dir / file
                shutil.copy2(file_src, file_dest)

        return workspace_path

    def apply_changeset(
        self,
        workspace_path: Path,
        changeset: ChangeSet,
    ) -> None:
        """Materialize proposed ChangeSet mutations directly in the isolated workspace."""
        base_dir = Path(workspace_path).resolve()

        for change in changeset.changes:
            target = (base_dir / change.path).resolve()
            if not str(target).startswith(str(base_dir)):
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
