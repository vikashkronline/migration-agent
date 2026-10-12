"""Unit tests for LocalWorkspaceAdapter staging isolation, confinement, and materialization."""

from pathlib import Path

import pytest

from migration_agent.adapters import LocalWorkspaceAdapter
from migration_agent.domain import ChangeSet, FileChange, FileMode, FileOperation


def test_create_staging_copies_files(tmp_path: Path) -> None:
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    (src_dir / "app").mkdir()
    (src_dir / "app" / "comp.js").write_text("console.log('hi');", encoding="utf-8")
    (src_dir / ".hidden").write_text("secret", encoding="utf-8")
    (src_dir / "node_modules").mkdir()
    (src_dir / "node_modules" / "dep.js").write_text("dep", encoding="utf-8")

    stg_root = tmp_path / "staging_root"
    adapter = LocalWorkspaceAdapter()
    ws = adapter.create_staging("run-001", src_dir, stg_root)

    assert ws.exists()
    assert (ws / "app" / "comp.js").exists()
    assert (ws / "app" / "comp.js").read_text(encoding="utf-8") == "console.log('hi');"
    # Hidden files and node_modules must not be copied
    assert not (ws / ".hidden").exists()
    assert not (ws / "node_modules").exists()


def test_create_staging_rejects_nonexistent_source(tmp_path: Path) -> None:
    adapter = LocalWorkspaceAdapter()
    with pytest.raises(ValueError, match="does not exist"):
        adapter.create_staging("run-001", tmp_path / "nonexistent", tmp_path / "staging")


def test_create_staging_rejects_path_traversal(tmp_path: Path) -> None:
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    adapter = LocalWorkspaceAdapter()
    with pytest.raises(ValueError, match="INVALID_ID"):
        adapter.create_staging("../../escaped", src_dir, tmp_path / "staging")


def test_create_staging_rejects_overlapping_paths(tmp_path: Path) -> None:
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    nested_staging = src_dir / "staging"
    adapter = LocalWorkspaceAdapter()
    with pytest.raises(ValueError, match="overlaps"):
        adapter.create_staging("run-001", src_dir, nested_staging)


def test_create_staging_ignores_symlinks_outside(tmp_path: Path) -> None:
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("confidential", encoding="utf-8")

    src_dir = tmp_path / "source"
    src_dir.mkdir()
    link = src_dir / "leak_symlink"
    try:
        link.symlink_to(outside_file)
    except OSError:
        pytest.skip("Symlink creation not supported on this host without elevation.")

    stg_root = tmp_path / "staging"
    adapter = LocalWorkspaceAdapter()
    with pytest.raises(ValueError, match="SOURCE_PATH_REJECTED"):
        adapter.create_staging("run-001", src_dir, stg_root)


def test_apply_changeset_materializes_changes(tmp_path: Path) -> None:
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    to_delete = ws_dir / "old.txt"
    to_delete.write_text("delete me", encoding="utf-8")

    changeset = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="rev-1",
        worktree_fingerprint="sha256:dummy",
        changes=(
            FileChange(
                path="src/new_file.ts",
                operation=FileOperation.CREATE,
                file_mode=FileMode.EXECUTABLE,
                content_bytes=b"#!/usr/bin/env node\nconsole.log(1);",
            ),
            FileChange(
                path="old.txt",
                operation=FileOperation.DELETE,
            ),
        ),
    )

    adapter = LocalWorkspaceAdapter()
    adapter.apply_changeset(ws_dir, changeset)

    assert not to_delete.exists()
    new_file = ws_dir / "src" / "new_file.ts"
    assert new_file.exists()
    assert new_file.read_bytes() == b"#!/usr/bin/env node\nconsole.log(1);"


def test_apply_changeset_rejects_escaping_path(tmp_path: Path) -> None:
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()

    changeset = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="rev-1",
        worktree_fingerprint="sha256:dummy",
        changes=(
            FileChange(
                path="../../escaped.txt",
                operation=FileOperation.CREATE,
                content_bytes=b"malicious",
            ),
        ),
    )

    adapter = LocalWorkspaceAdapter()
    with pytest.raises(ValueError, match="INVALID_PATH"):
        adapter.apply_changeset(ws_dir, changeset)


def test_cleanup_staging(tmp_path: Path) -> None:
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    (ws_dir / "test.txt").write_text("data", encoding="utf-8")

    adapter = LocalWorkspaceAdapter()
    assert ws_dir.exists()
    adapter.cleanup_staging(ws_dir)
    assert not ws_dir.exists()
