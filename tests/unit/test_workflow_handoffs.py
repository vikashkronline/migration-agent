"""Role handoff assurance and directory latency contracts."""

import pytest
from test_shared_apply import validated
from test_shared_apply import workflow as workflow

from migration_agent.adapters.git_directory import ProviderGitDirectory, _deadline
from migration_agent.domain.git_directory import GitDirectoryRequest
from migration_agent.domain.planning import AssuranceLevel


def test_reviewer_only_role_requires_independent_signature(workflow, monkeypatch):
    runtime, plan, step = workflow
    record = validated(workflow)
    authorization = runtime.proposals.authorization
    original = authorization.require

    def reviewer(capability, expected_digest=None):
        decision = original(capability, expected_digest)
        return decision.model_copy(
            update={
                "capabilities": tuple(c for c in decision.capabilities if c != "changeset.apply"),
                "key_fingerprint": "SHA256:enrolled-reviewer",
            }
        )

    monkeypatch.setattr(authorization, "require", reviewer)
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "reviewer-handoff")
    try:
        review = runtime.apply_service.request_review(plan, step, record.changeset_id, lease)
    finally:
        runtime.store.release_lease(lease)
    assert review.required_assurance == AssuranceLevel.MODE_A
    assert review.signer_key_fingerprint == "SHA256:enrolled-reviewer"


def test_directory_total_deadline_is_bounded_and_reset(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("migration_agent.adapters.git_directory.time.monotonic", lambda: clock[0])
    directory = ProviderGitDirectory(())

    def response(request, page):
        clock[0] += 11
        return {"id": 123} if page is None else []

    monkeypatch.setattr(directory, "_response", response)
    request = GitDirectoryRequest(provider="github", host="github.com", repository="team/repo")
    with pytest.raises(ValueError, match="GIT_DIRECTORY_TIMEOUT"):
        directory.members(request)
    assert _deadline.get() is None


def test_short_heartbeat_does_not_shorten_interactive_lease_or_revive_expiry(tmp_path, monkeypatch):
    from migration_agent.adapters.workflow_store import SqliteWorkflowStore

    clock = [1000.0]
    monkeypatch.setattr("migration_agent.adapters.workflow_store.time.time", lambda: clock[0])
    store = SqliteWorkflowStore(tmp_path / "state")
    lease = store.acquire_lease("project", "interactive", ttl=900)
    clock[0] += 10
    store.renew_lease(lease, 300)
    with store._get_connection() as connection:
        assert connection.execute("SELECT expires_at FROM writer_leases").fetchone()[0] == 1900
    clock[0] = 1901
    with pytest.raises(ValueError, match="LEASE_LOST"):
        store.renew_lease(lease, 300)


def test_signed_handoff_crosses_os_accounts_but_local_confirmation_does_not(tmp_path):
    import getpass
    from datetime import UTC, datetime, timedelta

    from security_project import security_project
    from ssh_signature_fixture import ssh_signature

    from migration_agent.adapters.access_approval_authority import AccessApprovalAuthority
    from migration_agent.adapters.approval_proof import LocalApprovalProof
    from migration_agent.domain.apply_approval import ApplyApprovalRecord

    authorization, owner, private = security_project(tmp_path)
    policy = owner.view()
    project_id = "workflow-fixture"
    proof = LocalApprovalProof(
        authorization.trust, authorization.state, AccessApprovalAuthority(authorization, project_id)
    )
    local = ApplyApprovalRecord(
        project_id=project_id,
        run_id="run-fixture",
        plan_id="plan-fixture",
        step_id="step-fixture",
        changeset_id="cs-fixture",
        changeset_digest="sha256:" + "1" * 64,
        policy_digest="sha256:" + "2" * 64,
        base_revision=policy.binding.source_root_commit,
        worktree_fingerprint="sha256:" + "3" * 64,
        validation_digest="sha256:" + "4" * 64,
        actor=getpass.getuser(),
        principal_id="owner",
        access_digest=policy.digest,
        assurance_level=AssuranceLevel.MODE_B,
        nonce="nonce-fixture",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    local = local.model_copy(update={"signature": proof.sign(local)})
    assert proof.verify(local, policy.binding.source_root_commit)
    authorization.actor = authorization.actor.model_copy(update={"os_identity": "test:operator"})
    assert not proof.verify(local, policy.binding.source_root_commit)
    signed = local.model_copy(
        update={
            "assurance_level": AssuranceLevel.MODE_A,
            "key_fingerprint": policy.members[0].key_fingerprint,
            "signature": "",
        }
    )
    signed = signed.model_copy(
        update={"signature": ssh_signature(private, signed.signing_digest, "migration-agent-apply")}
    )
    assert proof.verify(signed, policy.binding.source_root_commit)
    wrong_purpose = signed.model_copy(
        update={
            "signature": ssh_signature(private, signed.signing_digest, "migration-agent-access")
        }
    )
    assert not proof.verify(wrong_purpose, policy.binding.source_root_commit)
