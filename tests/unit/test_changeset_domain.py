"""Unit tests for ChangeSet domain models, fingerprinting, and canonical digests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from migration_agent.domain import (
    ApplyResult,
    ApplyStatus,
    ChangeSet,
    FileChange,
    FileMode,
    FileOperation,
    compute_changeset_digest,
    compute_file_sha256,
    compute_worktree_fingerprint,
)


def test_file_change_immutability() -> None:
    fc = FileChange(
        path="src/app.ts",
        operation=FileOperation.CREATE,
        file_mode=FileMode.STANDARD,
        content_digest="sha256:abcdef",
        content_bytes=b"console.log('hello');",
    )
    with pytest.raises(ValidationError):
        fc.path = "src/other.ts"  # type: ignore[misc]


def test_compute_file_sha256() -> None:
    digest1 = compute_file_sha256(b"hello world")
    assert digest1.startswith("sha256:")
    assert len(digest1) == 71  # "sha256:" (7) + 64 hex characters
    digest2 = compute_file_sha256(b"hello world")
    assert digest1 == digest2
    assert digest1 != compute_file_sha256(b"different content")


def test_changeset_immutability() -> None:
    cs = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="rev-001",
        worktree_fingerprint="sha256:1111",
        changes=(
            FileChange(
                path="src/comp.ts",
                operation=FileOperation.CREATE,
                content_digest="sha256:2222",
            ),
        ),
    )
    with pytest.raises(ValidationError):
        cs.step_id = "step-002"  # type: ignore[misc]


def test_compute_worktree_fingerprint_deterministic(tmp_path: Path) -> None:
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "sub" / "b.txt"
    f2.parent.mkdir(parents=True)
    f1.write_text("file a", encoding="utf-8")
    f2.write_text("file b", encoding="utf-8")

    fp1 = compute_worktree_fingerprint(tmp_path)
    fp2 = compute_worktree_fingerprint(tmp_path)
    assert fp1 == fp2
    assert fp1.startswith("sha256:")


def test_compute_worktree_fingerprint_detects_mutation(tmp_path: Path) -> None:
    f1 = tmp_path / "a.txt"
    f1.write_text("initial", encoding="utf-8")
    fp1 = compute_worktree_fingerprint(tmp_path)

    f1.write_text("modified", encoding="utf-8")
    fp2 = compute_worktree_fingerprint(tmp_path)
    assert fp1 != fp2


def test_compute_worktree_fingerprint_detects_addition_and_deletion(tmp_path: Path) -> None:
    f1 = tmp_path / "a.txt"
    f1.write_text("initial", encoding="utf-8")
    fp1 = compute_worktree_fingerprint(tmp_path)

    f2 = tmp_path / "b.txt"
    f2.write_text("new file", encoding="utf-8")
    fp2 = compute_worktree_fingerprint(tmp_path)
    assert fp1 != fp2

    f2.unlink()
    fp3 = compute_worktree_fingerprint(tmp_path)
    assert fp1 == fp3


def test_compute_changeset_digest_order_independent() -> None:
    ch1 = FileChange(
        path="src/a.ts",
        operation=FileOperation.CREATE,
        content_digest="sha256:1111",
    )
    ch2 = FileChange(
        path="src/b.ts",
        operation=FileOperation.MODIFY,
        content_digest="sha256:2222",
    )

    cs1 = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="rev-1",
        worktree_fingerprint="sha256:root",
        changes=(ch1, ch2),
    )
    cs2 = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="rev-1",
        worktree_fingerprint="sha256:root",
        changes=(ch2, ch1),  # Reversed order
    )

    digest1 = compute_changeset_digest(cs1)
    digest2 = compute_changeset_digest(cs2)
    assert digest1 == digest2
    assert digest1.startswith("sha256:")


def test_compute_changeset_digest_detects_tampering() -> None:
    ch1 = FileChange(
        path="src/a.ts",
        operation=FileOperation.CREATE,
        content_digest="sha256:1111",
    )
    cs1 = ChangeSet(
        changeset_id="cs-001",
        plan_id="plan-001",
        step_id="step-001",
        base_revision="rev-1",
        worktree_fingerprint="sha256:root",
        changes=(ch1,),
    )
    digest1 = compute_changeset_digest(cs1)

    tampered_cs = cs1.model_copy(update={"base_revision": "rev-tampered"})
    digest2 = compute_changeset_digest(tampered_cs)
    assert digest1 != digest2


def test_apply_result_models() -> None:
    res_applied = ApplyResult(
        status=ApplyStatus.APPLIED,
        changeset_id="cs-001",
        applied_paths=("src/a.ts",),
        backup_snapshot_path="/backups/cs-001",
        diagnostics=("Success",),
    )
    assert res_applied.status == ApplyStatus.APPLIED

    res_recovery = ApplyResult(
        status=ApplyStatus.RECOVERY_REQUIRED,
        changeset_id="cs-001",
        applied_paths=("src/a.ts",),
        diagnostics=("Double fault",),
        recovery_details={"apply_error": "err1", "rollback_error": "err2"},
    )
    assert res_recovery.status == ApplyStatus.RECOVERY_REQUIRED
    assert res_recovery.recovery_details is not None
