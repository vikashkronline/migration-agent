"""Exact-base read-only reviews never substitute current source or expose unsafe content."""

import http.client
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import pytest
from test_workbench import make_source, save_plan, service

from migration_agent.adapters.control_api.server import LoopbackControlServer
from migration_agent.adapters.project_evidence import LocalProjectEvidence
from migration_agent.adapters.workbench import task_id
from migration_agent.adapters.workbench_diff import project_file_diff
from migration_agent.application.control_service import ControlApiService
from migration_agent.domain.changeset import (
    ChangeSet,
    FileChange,
    FileOperation,
    compute_changeset_digest,
    compute_file_sha256,
)
from migration_agent.domain.host_workflow import Lifecycle, WorkflowRecord
from migration_agent.ports.frameworks import FrameworkAdapterRegistry


def base_repo(root: Path) -> str:
    (root / "sample.ts").write_bytes(b"const value = 1;\r\nlast line")
    for args in [
        ("init",),
        ("config", "core.autocrlf", "false"),
        ("add", "."),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "base",
        ),
    ]:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, timeout=30)
    return (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, timeout=30
        )
        .stdout.decode()
        .strip()
    )


def artifact(
    base: str,
    operation=FileOperation.MODIFY,
    path="sample.ts",
    data=b"const value = 2;\r\nlast line",
) -> ChangeSet:
    cs = ChangeSet(
        changeset_id="cs-review",
        plan_id="plan-1",
        step_id="step-1",
        base_revision=base,
        worktree_fingerprint="fixture-base",
        changes=(
            FileChange(
                path=path,
                operation=operation,
                content_bytes=data,
                content_digest=compute_file_sha256(data),
            ),
        ),
    )
    return cs.model_copy(update={"changeset_digest": compute_changeset_digest(cs)})


@pytest.mark.parametrize(
    "operation,path",
    [
        (FileOperation.MODIFY, "sample.ts"),
        (FileOperation.CREATE, "new.ts"),
        (FileOperation.DELETE, "sample.ts"),
    ],
)
def test_diff_uses_immutable_base_and_preserves_lines(tmp_path: Path, operation, path) -> None:
    base = base_repo(tmp_path)
    cs = artifact(base, operation, path)
    (tmp_path / "sample.ts").write_text("unrelated current source", encoding="utf-8")
    before = (tmp_path / "sample.ts").read_bytes()
    diff = project_file_diff(tmp_path, "project", "node", "revision", cs, cs.changes[0])
    assert diff.available and diff.hunks
    lines = [line for hunk in diff.hunks for line in hunk.lines]
    assert "unrelated current source" not in diff.model_dump_json()
    if operation != FileOperation.CREATE:
        assert any(line.text == "const value = 1;\r\n" and line.old_line == 1 for line in lines)
    if operation != FileOperation.DELETE:
        assert any(line.text == "const value = 2;\r\n" and line.new_line == 1 for line in lines)
    assert (tmp_path / "sample.ts").read_bytes() == before


@pytest.mark.parametrize(
    "path,data",
    [
        ("../outside.ts", b"text"),
        ("secret.ts", ("sk-" + "A" * 48).encode()),
        ("binary.ts", b"a\0b"),
        ("huge.ts", b"x" * 32769),
    ],
    ids=["traversal", "credential", "binary", "oversized"],
)
def test_unsupported_preview_has_no_partial_content(tmp_path: Path, path, data) -> None:
    base = base_repo(tmp_path)
    cs = artifact(base, FileOperation.CREATE, path, data)
    result = project_file_diff(tmp_path, "p", "n", "r", cs, cs.changes[0])
    assert not result.available and not result.hunks and result.reason
    assert "A" * 48 not in result.model_dump_json()


def test_exact_scope_staleness_and_tampered_proposed_bytes(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    base = base_repo(source.binding.project_root)
    save_plan(source)
    cs = artifact(base)
    source.store.save_changeset(cs)
    record = WorkflowRecord(
        project_id=source.binding.project_id,
        source_root=str(source.binding.project_root),
        run_id="run-1",
        plan_id="plan-1",
        step_id="step-1",
        state=Lifecycle.PLAN_SAVED,
        base_revision=base,
        root_commit=base,
        worktree_fingerprint=cs.worktree_fingerprint,
        policy_digest="policy",
        changeset_id=cs.changeset_id,
        changeset_digest=cs.changeset_digest,
    )
    lease = source.store.acquire_lease(record.project_id, "diff-fixture")
    try:
        source.store.save_workflow(record, lease)
    finally:
        source.store.release_lease(lease)
    api = service(source)
    snap = api.snapshot()
    node = task_id("plan-1", "step-1")
    result = api.file_diff(snap.project_id, node, snap.revision, cs.changeset_digest, 0)
    assert result.available and result.path == "sample.ts"
    server = LoopbackControlServer(ControlApiService(), source.binding.project_root, workbench=api)
    server.start("127.0.0.1", 0, "diff-fixture")
    conn = http.client.HTTPConnection("127.0.0.1", server.port)
    try:
        query = urlencode(
            {
                "project": snap.project_id,
                "node": node,
                "revision": snap.revision,
                "artifact": cs.changeset_digest,
                "index": "0",
            }
        )
        conn.request(
            "GET", "/api/v1/workbench/diff?" + query, headers={"X-Session-Token": "diff-fixture"}
        )
        response = conn.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["data"]["path"] == "sample.ts"
        conn.request("GET", "/api/v1/workbench/diff?" + query)
        response = conn.getresponse()
        assert response.status == 401
        response.read()
    finally:
        conn.close()
        server.stop()
    with pytest.raises(ValueError, match="PROJECT_MISMATCH"):
        api.file_diff("foreign", node, snap.revision, cs.changeset_digest, 0)
    with pytest.raises(ValueError, match="STALE"):
        api.file_diff(snap.project_id, node, "old", cs.changeset_digest, 0)
    with pytest.raises(ValueError, match="STALE"):
        api.file_diff(snap.project_id, node, snap.revision, "foreign-artifact", 0)
    with pytest.raises(ValueError, match="INDEX_INVALID"):
        api.file_diff(snap.project_id, node, snap.revision, cs.changeset_digest, -1)
    source.store.save_changeset(
        cs.model_copy(
            update={"changes": (cs.changes[0].model_copy(update={"content_bytes": b"tampered"}),)}
        )
    )
    with pytest.raises(ValueError, match="digest differs"):
        api.file_diff(snap.project_id, node, snap.revision, cs.changeset_digest, 0)


@pytest.mark.parametrize(
    "data",
    [b"a\0b", ("sk-" + "A" * 48).encode(), b"x" * 32769, b"line\n" * 4001],
    ids=["binary", "credential", "oversized", "line-budget"],
)
def test_unavailable_base_never_returns_partial_diff(tmp_path: Path, data: bytes) -> None:
    base_repo(tmp_path)
    (tmp_path / "sample.ts").write_bytes(data)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True, timeout=30)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "unsupported-base",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        timeout=30,
    )
    base = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, timeout=30
        )
        .stdout.decode()
        .strip()
    )
    cs = artifact(base)
    result = project_file_diff(tmp_path, "p", "n", "r", cs, cs.changes[0])
    assert not result.available and not result.hunks


def test_git_inspection_disables_fetch_and_interactive_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    def read_only_run(args, **kwargs):
        assert kwargs["shell"] is False
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert kwargs["env"]["GIT_ALLOW_PROTOCOL"] == ""
        return subprocess.CompletedProcess(args, 0, stdout=b"bounded", stderr=b"")

    monkeypatch.setattr(subprocess, "run", read_only_run)
    evidence = LocalProjectEvidence(tmp_path, FrameworkAdapterRegistry(()))
    assert evidence._git_bytes("rev-parse", "HEAD") == b"bounded"
