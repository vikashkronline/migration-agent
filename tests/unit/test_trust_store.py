"""Unit tests for Mode A trust store, authority keys, and cryptographic signatures."""

import hashlib
import hmac
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
from migration_agent.domain.security import SecurityConfigurationError


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


def _forged_public_proof(digest: str, public_key: str) -> str:
    return "ed25519:" + hmac.new(public_key.encode(), digest.encode(), hashlib.sha256).hexdigest()


def _legacy_key() -> AuthorityKey:
    return AuthorityKey(
        key_id="legacy",
        public_key="public-fixture",
        fingerprint="fixture",
        created_at="2026-10-09T00:00:00Z",
    )


@pytest.mark.parametrize("signature", ["", "ed25519:forged", "rsa:forged"])
@pytest.mark.parametrize("revoked", [False, True])
def test_legacy_verification_is_terminal(signature: str, revoked: bool) -> None:
    key = _legacy_key().model_copy(update={"revoked": revoked})
    with pytest.raises(SecurityConfigurationError, match="LEGACY_MODE_A_DISABLED"):
        CryptoSignatureVerifierAdapter().verify("sha256:" + "a" * 64, signature, key)


def test_public_key_hmac_cannot_claim_mode_a() -> None:
    key = _legacy_key()
    digest = "sha256:" + "b" * 64
    forged = _forged_public_proof(digest, key.public_key)
    with pytest.raises(SecurityConfigurationError, match="LEGACY_MODE_A_DISABLED"):
        CryptoSignatureVerifierAdapter().verify(digest, forged, key)


def test_legacy_signer_cannot_issue_a_proof() -> None:
    with pytest.raises(SecurityConfigurationError, match="LEGACY_MODE_A_DISABLED"):
        CryptoSignatureVerifierAdapter().sign("sha256:" + "a" * 64, private_key="test-only")


def _pending_plan(repo: Path, store: SqliteCheckpointStore) -> MigrationPlan:
    governance = GitGovernanceAdapter()
    governance.ensure_governance_layout(str(repo))
    plan = MigrationPlan(
        plan_id="plan-legacy",
        source_root=str(repo),
        run_id="run-legacy",
        status=PlanStatus.DRAFT,
        steps=[MigrationStep(step_id="step-1", title="Step", description="Fixture")],
        policy_digest=governance.get_policy_digest(str(repo)),
    )
    store.save_plan(plan)
    return plan


def test_planning_does_not_downgrade_failed_legacy_proof(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    store = SqliteCheckpointStore(tmp_path / "state")
    plan = _pending_plan(repo, store)
    key = _legacy_key()
    service = PlanningService(FakeAgentRuntime(), store, store, GitGovernanceAdapter())
    with pytest.raises(SecurityConfigurationError, match="LEGACY_MODE_A_DISABLED"):
        service.approve_plan(
            plan.plan_id,
            actor="legacy",
            assurance_level=AssuranceLevel.MODE_A,
            project_root=str(repo),
            custom_signature=_forged_public_proof(compute_plan_digest(plan), key.public_key),
            authority_key=key,
            signature_verifier=CryptoSignatureVerifierAdapter(),
        )
    persisted = store.get_plan(plan.plan_id)
    assert persisted is not None
    assert persisted.status == PlanStatus.DRAFT
    assert persisted.approval is None


def test_cli_legacy_mode_a_fails_without_approval(
    tmp_path: Path, cli_workflow_authorization
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = tmp_path / "state"
    store = SqliteCheckpointStore(state)
    plan = _pending_plan(repo, store)
    trust = tmp_path / "trust"
    key = _legacy_key()
    LocalTrustStoreAdapter(trust).bootstrap_authority_key(repo.name, key)
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "approve",
            plan.plan_id,
            "--actor",
            "legacy",
            "--assurance-level",
            "MODE_A",
            "--signature",
            _forged_public_proof(compute_plan_digest(plan), key.public_key),
            "--key-id",
            key.key_id,
            "--state-dir",
            str(state),
            "--project-root",
            str(repo),
            "--trust-dir",
            str(trust),
        ],
    )
    assert result.exit_code == 2
    assert "LEGACY_MODE_A_DISABLED" in result.output
    persisted = store.get_plan(plan.plan_id)
    assert persisted is not None and persisted.approval is None
    assert persisted.status == PlanStatus.DRAFT
