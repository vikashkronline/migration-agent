"""Separate cumulative target publication, exact review and drift regressions."""

from pathlib import Path

import pytest
from test_shared_apply import HumanFixture, validated
from test_shared_apply import workflow as workflow

from migration_agent.adapters.controlled_files import LocalControlledFiles, destination_fingerprint
from migration_agent.adapters.recovery_probe import LocalRecoveryProbe
from migration_agent.adapters.workbench_diff import project_file_diff
from migration_agent.domain.changeset import ApplyStatus, compute_changeset_digest


def separate(workflow, tmp_path: Path):
    runtime, _, _ = workflow
    target = tmp_path / "target"
    files = LocalControlledFiles(
        runtime.binding.project_root, runtime.staging, runtime.state, target
    )
    runtime.files = files
    runtime.apply_service.files = files
    return target


def test_target_apply_preserves_source_and_binds_review(workflow, tmp_path):
    target = separate(workflow, tmp_path)
    runtime, plan, step = workflow
    before = runtime.proposals.evidence.repository_state()
    record = validated(workflow)
    assert not target.exists()
    assert record.destination.root == str(target)
    approval = runtime.apply_service.approve(plan, step, HumanFixture())
    assert approval.destination == record.destination
    changeset = runtime.store.get_changeset(record.changeset_id)
    diff = project_file_diff(
        runtime.binding.project_root, "project", "task", "rev", changeset, changeset.changes[0]
    )
    assert diff.available and diff.base_revision == record.destination.fingerprint
    outcome = runtime.apply_service.apply(plan, step, record.changeset_id)
    assert outcome.status == ApplyStatus.APPLIED
    assert destination_fingerprint(target) == record.staging_fingerprint
    assert runtime.proposals.evidence.repository_state() == before
    assert runtime.files.lock_identity("other-project") == runtime.files.lock_identity(
        runtime.binding.project_id
    )


def test_target_drift_and_destination_switch_invalidate_approval(workflow, tmp_path):
    target = separate(workflow, tmp_path)
    runtime, plan, step = workflow
    record = validated(workflow)
    runtime.apply_service.approve(plan, step, HumanFixture())
    target.mkdir()
    (target / "unexpected.txt").write_text("unreviewed", encoding="utf-8")
    with pytest.raises(ValueError, match="DESTINATION_CHANGED"):
        runtime.apply_service.apply(plan, step, record.changeset_id)
    changeset = runtime.store.get_changeset(record.changeset_id)
    other = LocalControlledFiles(
        runtime.binding.project_root, runtime.staging, runtime.state, tmp_path / "other"
    )
    with pytest.raises(ValueError, match="DESTINATION_CHANGED"):
        other.verify_destination(changeset)
    tampered = changeset.model_copy(
        update={
            "destination": changeset.destination.model_copy(
                update={"root": str(tmp_path / "other")}
            )
        }
    )
    assert compute_changeset_digest(tampered) != changeset.changeset_digest


def test_cumulative_stage_and_recovery_use_destination(workflow, tmp_path):
    separate(workflow, tmp_path)
    runtime, plan, step = workflow
    first = validated(workflow)
    runtime.apply_service.approve(plan, step, HumanFixture())
    runtime.apply_service.apply(plan, step, first.changeset_id)
    # Repeating a plan against the same immutable source produces a new target-bound artifact.
    original = runtime.store.get_plan(plan)
    second = original.model_copy(update={"plan_id": "plan-second", "run_id": "run-second"})
    runtime.store.save_plan(second)
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "second")
    try:
        record = runtime.apply_service.stage(second.plan_id, step, lease)
        changeset = runtime.store.get_changeset(record.changeset_id)
        assert all(change.base_content_bytes is not None for change in changeset.changes)
        assert changeset.destination.fingerprint == first.staging_fingerprint
        assert (
            LocalRecoveryProbe(runtime.binding.project_root, tmp_path / "other").classify(
                record, changeset
            )
            == "ambiguous"
        )
        assert destination_fingerprint(Path(record.staging_path)) == record.staging_fingerprint
    finally:
        runtime.store.release_lease(lease)


def test_source_preserving_session_requires_target_and_foundation(workflow, tmp_path):
    runtime, plan, step = workflow
    runtime.apply_service.files = LocalControlledFiles(
        runtime.binding.project_root, runtime.staging, runtime.state, require_destination=True
    )
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "missing-target")
    try:
        with pytest.raises(ValueError, match="DESTINATION_REQUIRED"):
            runtime.apply_service.stage(plan, step, lease)
        runtime.apply_service.files = LocalControlledFiles(
            runtime.binding.project_root, runtime.staging, runtime.state, tmp_path / "target"
        )
        runtime.apply_service.foundation_contract = lambda: "accepted-architecture"
        with pytest.raises(ValueError, match="FOUNDATION_PUBLICATION_REQUIRED"):
            runtime.apply_service.stage(plan, step, lease)
    finally:
        runtime.store.release_lease(lease)


def test_target_overlap_rejected(workflow):
    runtime, _, _ = workflow
    with pytest.raises(ValueError, match="UNSAFE_ROOT_OVERLAP"):
        LocalControlledFiles(
            runtime.binding.project_root,
            runtime.staging,
            runtime.state,
            runtime.binding.project_root / "target",
        )
