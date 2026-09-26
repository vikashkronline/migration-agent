"""Unit tests for Mode A trust store, authority keys, and cryptographic signatures."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from migration_agent.adapters import (
    CryptoSignatureVerifierAdapter,
    LocalTrustStoreAdapter,
    SqliteCheckpointStore,
)
from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.application.planning import PlanningService
from migration_agent.cli import app
from migration_agent.domain import (
    AssuranceLevel,
    AuthorityKey,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    RepositoryBinding,
    compute_plan_digest,
)


def test_trust_store_bootstrap_and_binding(tmp_path: Path) -> None:
    store = LocalTrustStoreAdapter(trust_root=tmp_path / "trust")
    project_id = "test-proj"

    key = AuthorityKey(
        key_id="auth-key-1",
        algorithm="ed25519",
        public_key="secret-pub-key-123",
        fingerprint="fp-123",
        created_at="2026-09-26T12:00:00Z",
    )
    binding = RepositoryBinding(
        root_commit_sha="abcd1234abcd",
        remote_origin_url="git@github.com:org/repo.git",
    )

    # Bootstrap authority key
    record = store.bootstrap_authority_key(project_id, key, binding)
    assert record.project_id == project_id
    assert len(record.authority_keys) == 1
    assert record.authority_keys[0].key_id == "auth-key-1"

    # Reload from disk
    loaded = store.load_trust_record(project_id)
    assert loaded is not None
    assert loaded.find_key("auth-key-1") is not None
    assert loaded.find_key("fp-123") is not None
    assert loaded.find_key("nonexistent") is None

    # Verify repository binding signals
    assert store.verify_repository_binding(project_id, root_commit_sha="abcd1234abcd") is True
    assert (
        store.verify_repository_binding(project_id, remote_origin_url="git@github.com:org/repo.git")
        is True
    )
    assert store.verify_repository_binding(project_id, root_commit_sha="wrong-sha") is False
    assert (
        store.verify_repository_binding(
            project_id, remote_origin_url="git@github.com:other/repo.git"
        )
        is False
    )


def test_crypto_signature_verifier() -> None:
    verifier = CryptoSignatureVerifierAdapter()
    key = AuthorityKey(
        key_id="auth-key-1",
        algorithm="ed25519",
        public_key="shared-secret-key",
        fingerprint="fp-1",
        created_at="2026-09-26T12:00:00Z",
    )

    payload_digest = "sha256:11223344556677889900aabbccddeeff"
    sig = verifier.sign(payload_digest, private_key="shared-secret-key", algorithm="ed25519")
    assert sig.startswith("ed25519:")

    # Successful verification
    res = verifier.verify(payload_digest, sig, key)
    assert res.verified is True
    assert res.assurance_level == AssuranceLevel.MODE_A

    # Corrupted payload digest
    bad_res = verifier.verify("sha256:corrupted_digest", sig, key)
    assert bad_res.verified is False
    assert bad_res.assurance_level == AssuranceLevel.MODE_C

    # Revoked key
    revoked_key = key.model_copy(update={"revoked": True})
    rev_res = verifier.verify(payload_digest, sig, revoked_key)
    assert rev_res.verified is False
    assert "revoked" in (rev_res.reason or "")


def test_planning_service_mode_a_approval(tmp_path: Path) -> None:
    checkpoint_store = SqliteCheckpointStore(tmp_path / "state")
    governance = GitGovernanceAdapter()
    runtime = FakeAgentRuntime()
    service = PlanningService(
        runtime=runtime,
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
        governance=governance,
    )

    proj_dir = tmp_path / "repo"
    proj_dir.mkdir()
    governance.ensure_governance_layout(proj_dir)

    plan = MigrationPlan(
        plan_id="plan-mode-a",
        source_root=str(proj_dir),
        run_id="run-001",
        status=PlanStatus.DRAFT,
        steps=[
            MigrationStep(
                step_id="step-1",
                title="Migrate component",
                description="desc",
            )
        ],
        policy_digest=governance.get_policy_digest(proj_dir),
    )
    checkpoint_store.save_plan(plan)

    verifier = CryptoSignatureVerifierAdapter()
    key = AuthorityKey(
        key_id="lead-architect",
        algorithm="ed25519",
        public_key="architect-secret",
        fingerprint="fp-arch",
        created_at="2026-09-26T12:00:00Z",
    )

    plan_digest = compute_plan_digest(plan)
    sig = verifier.sign(plan_digest, private_key="architect-secret", algorithm="ed25519")

    # Mode A approval with valid signature
    approved = service.approve_plan(
        plan.plan_id,
        actor="lead-architect",
        assurance_level=AssuranceLevel.MODE_A,
        project_root=str(proj_dir),
        custom_signature=sig,
        authority_key=key,
        signature_verifier=verifier,
    )
    assert approved.status == PlanStatus.APPROVED
    assert approved.approval is not None
    assert approved.approval.assurance_level == AssuranceLevel.MODE_A
    assert approved.approval.signature == sig

    # Mode A approval with invalid signature should raise ValueError
    with pytest.raises(ValueError, match="Mode A signature verification failed"):
        service.approve_plan(
            plan.plan_id,
            actor="lead-architect",
            assurance_level=AssuranceLevel.MODE_A,
            project_root=str(proj_dir),
            custom_signature="ed25519:invalid_sig",
            authority_key=key,
            signature_verifier=verifier,
        )


def test_cli_mode_a_approval(tmp_path: Path) -> None:
    runner = CliRunner()
    state_dir = tmp_path / "state"
    trust_dir = tmp_path / "trust"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Bootstrap trust store
    trust_store = LocalTrustStoreAdapter(trust_root=trust_dir)
    key = AuthorityKey(
        key_id="deployer-key",
        algorithm="ed25519",
        public_key="deployer-secret-key",
        fingerprint="fp-deployer",
        created_at="2026-09-26T12:00:00Z",
    )
    trust_store.bootstrap_authority_key(repo_dir.name, key)

    # Initialize plan
    checkpoint_store = SqliteCheckpointStore(state_dir)
    gov = GitGovernanceAdapter()
    gov.ensure_governance_layout(repo_dir)

    plan = MigrationPlan(
        plan_id="plan-cli-mode-a",
        source_root=str(repo_dir),
        run_id="run-cli-001",
        status=PlanStatus.DRAFT,
        steps=[MigrationStep(step_id="step-1", title="Step 1", description="desc")],
        policy_digest=gov.get_policy_digest(repo_dir),
    )
    checkpoint_store.save_plan(plan)

    verifier = CryptoSignatureVerifierAdapter()
    plan_digest = compute_plan_digest(plan)
    valid_sig = verifier.sign(plan_digest, private_key="deployer-secret-key")

    # Missing signature on Mode A -> exit 2
    res_no_sig = runner.invoke(
        app,
        [
            "plan",
            "approve",
            "plan-cli-mode-a",
            "--actor",
            "deployer-key",
            "--assurance-level",
            "MODE_A",
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(repo_dir),
            "--trust-dir",
            str(trust_dir),
        ],
    )
    assert res_no_sig.exit_code == 2
    assert "Mode A approval requires --signature" in res_no_sig.output

    # Valid Mode A approval -> exit 0
    res_valid = runner.invoke(
        app,
        [
            "plan",
            "approve",
            "plan-cli-mode-a",
            "--actor",
            "deployer-key",
            "--assurance-level",
            "MODE_A",
            "--signature",
            valid_sig,
            "--key-id",
            "deployer-key",
            "--state-dir",
            str(state_dir),
            "--project-root",
            str(repo_dir),
            "--trust-dir",
            str(trust_dir),
        ],
    )
    assert res_valid.exit_code == 0
    assert '"status":"APPROVED"' in res_valid.output
    assert '"assurance_level":"MODE_A"' in res_valid.output
