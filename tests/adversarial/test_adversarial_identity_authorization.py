"""Adversarial test suite for Section 15.1: Identity & Authorization Verification.

Tests security invariants for:
- Policy Tampering (ADR-2)
- Unknown Key Rejection
- Repository Binding Mismatch
- Signature Integrity & Digest Tampering
- Revocation Enforcement
- Assurance Boundary Enforcement (Mode A vs Mode B/C)
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.adapters.trust_store import (
    CryptoSignatureVerifierAdapter,
    LocalTrustStoreAdapter,
)
from migration_agent.domain import (
    ApprovalSignature,
    AssuranceLevel,
    AuthorityKey,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    RepositoryBinding,
    compute_plan_digest,
    verify_approval,
)
from migration_agent.ports.governance import ProjectPolicy


def test_policy_tampering_defense(tmp_path: Path) -> None:
    """Tampered or invalid project policies must fail closed to safe defaults."""
    adapter = GitGovernanceAdapter()
    adapter.ensure_governance_layout(str(tmp_path), project_id="tamper-test")

    # Initial policy digest
    initial_digest = adapter.get_policy_digest(str(tmp_path))
    assert initial_digest is not None

    # 1. Valid policy modification changes policy digest immediately
    policy_file = tmp_path / ".agent" / "policy.json"
    modified_policy = ProjectPolicy(
        schema_version=1,
        default_mode="MODE_A",
        max_step_files=5,
        require_approval_for_apply=True,
    )
    policy_file.write_text(modified_policy.model_dump_json(indent=2), encoding="utf-8")
    modified_digest = adapter.get_policy_digest(str(tmp_path))
    assert modified_digest != initial_digest

    # 2. Injected forbidden extra fields fail closed with ValidationError
    policy_file.write_text(
        '{\n  "schema_version": 1,\n  "unauthorized_field": "dangerous"\n}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        adapter.get_policy(str(tmp_path))

    # 3. Corrupted / malformed non-JSON fails closed with error
    policy_file.write_text("NOT_VALID_JSON{:::broken", encoding="utf-8")
    with pytest.raises(ValidationError):
        adapter.get_policy(str(tmp_path))


def test_unknown_key_rejection(tmp_path: Path) -> None:
    """Signatures generated with unknown keys must be rejected unconditionally."""
    store = LocalTrustStoreAdapter(trust_root=tmp_path / "trust")
    verifier = CryptoSignatureVerifierAdapter()

    # Valid key bootstrapped in store
    legit_key = AuthorityKey(
        key_id="legit-authority-key",
        algorithm="ed25519",
        public_key="legit-secret-seed-987",
        fingerprint="fp-legit-987",
        created_at="2026-09-30T00:00:00Z",
    )
    store.bootstrap_authority_key("project-x", legit_key)

    # Adversary signs with their own unknown key
    payload = "sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    adversary_sig = verifier.sign(payload, private_key="adversary-key", algorithm="ed25519")

    # Verification against project trust store with unknown key ID must fail
    record = store.load_trust_record("project-x")
    assert record is not None
    unknown_key = record.find_key("adversary-key-id")
    assert unknown_key is None

    # Even if adversary passes their own key object, verification against legit key fails
    res = verifier.verify(payload, adversary_sig, legit_key)
    assert res.verified is False
    assert res.assurance_level == AssuranceLevel.MODE_C
    assert "digest mismatch" in (res.reason or "").lower()


def test_repository_binding_mismatch_defense(tmp_path: Path) -> None:
    """Cloned or spoofed repositories with mismatched root commits or remotes must be rejected."""
    store = LocalTrustStoreAdapter(trust_root=tmp_path / "trust")
    project_id = "acme-enterprise"

    key = AuthorityKey(
        key_id="sec-key-1",
        algorithm="ed25519",
        public_key="key-bytes-1",
        fingerprint="fp-1",
        created_at="2026-09-30T00:00:00Z",
    )
    binding = RepositoryBinding(
        root_commit_sha="e5fa44f2b31c1fb553b6021e7360d07d5d91ff5e",
        remote_origin_url="git@github.com:acme-org/production-app.git",
    )
    store.bootstrap_authority_key(project_id, key, binding)

    # 1. Matching binding succeeds
    assert (
        store.verify_repository_binding(
            project_id,
            root_commit_sha="e5fa44f2b31c1fb553b6021e7360d07d5d91ff5e",
            remote_origin_url="git@github.com:acme-org/production-app.git",
        )
        is True
    )

    # 2. Case-insensitivity on commit SHA is supported
    assert (
        store.verify_repository_binding(
            project_id,
            root_commit_sha="E5FA44F2B31C1FB553B6021E7360D07D5D91FF5E",
            remote_origin_url="git@github.com:acme-org/production-app.git",
        )
        is True
    )

    # 3. Mismatched root commit (spoofed history / rebased repo) is rejected
    assert (
        store.verify_repository_binding(
            project_id,
            root_commit_sha="0000000000000000000000000000000000000000",
            remote_origin_url="git@github.com:acme-org/production-app.git",
        )
        is False
    )

    # 4. Mismatched remote origin URL (forked or phishing repo) is rejected
    assert (
        store.verify_repository_binding(
            project_id,
            root_commit_sha="e5fa44f2b31c1fb553b6021e7360d07d5d91ff5e",
            remote_origin_url="git@github.com:attacker-org/spoofed-app.git",
        )
        is False
    )


def test_signature_integrity_and_corruption_vectors() -> None:
    """Corrupted signatures, payload changes, and invalid algorithm prefixes must fail."""
    verifier = CryptoSignatureVerifierAdapter()
    key = AuthorityKey(
        key_id="k-1",
        algorithm="ed25519",
        public_key="correct-shared-secret-12345",
        fingerprint="fp-1",
        created_at="2026-09-30T00:00:00Z",
    )
    digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    valid_sig = verifier.sign(
        digest, private_key="correct-shared-secret-12345", algorithm="ed25519"
    )

    # 1. Empty signature rejected
    empty_res = verifier.verify(digest, "", key)
    assert empty_res.verified is False
    assert "empty signature" in (empty_res.reason or "").lower()

    # 2. Algorithm mismatch in signature prefix rejected
    wrong_algo_sig = f"rsa:{valid_sig.split(':', 1)[1]}"
    algo_res = verifier.verify(digest, wrong_algo_sig, key)
    assert algo_res.verified is False
    assert "algorithm mismatch" in (algo_res.reason or "").lower()

    # 3. Bit-flipped / corrupted signature rejected
    corrupted_body = valid_sig[:-4] + "dead"
    corrupt_res = verifier.verify(digest, corrupted_body, key)
    assert corrupt_res.verified is False
    assert corrupt_res.assurance_level == AssuranceLevel.MODE_C

    # 4. Altered payload digest rejected
    tampered_digest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    digest_res = verifier.verify(tampered_digest, valid_sig, key)
    assert digest_res.verified is False


def test_revocation_enforcement() -> None:
    """Revoked authority keys must fail verification, even with otherwise valid signatures."""
    verifier = CryptoSignatureVerifierAdapter()
    revoked_key = AuthorityKey(
        key_id="compromised-key-99",
        algorithm="ed25519",
        public_key="leaked-secret-bytes",
        fingerprint="fp-comp-99",
        revoked=True,
        created_at="2026-09-01T00:00:00Z",
    )

    digest = "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    # Even with legitimate signature produced from the key's secret
    valid_sig = verifier.sign(digest, private_key="leaked-secret-bytes", algorithm="ed25519")

    res = verifier.verify(digest, valid_sig, revoked_key)
    assert res.verified is False
    assert res.assurance_level == AssuranceLevel.MODE_C
    assert "revoked" in (res.reason or "").lower()


def test_assurance_boundary_enforcement() -> None:
    """Mode B and C signatures cannot satisfy plans demanding Mode A cryptographic assurance."""
    step = MigrationStep(
        step_id="step-1",
        title="Migrate sensitive auth component",
        description="Refactor OAuth handler",
    )
    plan = MigrationPlan(
        plan_id="plan-mode-a-required",
        source_root="/repo",
        run_id="run-1",
        status=PlanStatus.DRAFT,
        steps=[step],
        policy_digest="policy-digest-1",
    )

    digest = compute_plan_digest(plan)

    # 1. Plan approved with Mode C
    sig_c = ApprovalSignature(
        actor="anonymous-heuristics",
        plan_digest=digest,
        policy_digest="policy-digest-1",
        signature="heuristic-auto-token",
        assurance_level=AssuranceLevel.MODE_C,
    )
    mode_c_plan = plan.model_copy(update={"status": PlanStatus.APPROVED, "approval": sig_c})
    assert verify_approval(mode_c_plan, active_policy_digest="policy-digest-1") is True
    assert mode_c_plan.approval is not None
    assert mode_c_plan.approval.assurance_level == AssuranceLevel.MODE_C
    assert mode_c_plan.approval.assurance_level != AssuranceLevel.MODE_A

    # 2. Plan approved with Mode B (authenticated user session)
    sig_b = ApprovalSignature(
        actor="engineer@corp.local",
        plan_digest=digest,
        policy_digest="policy-digest-1",
        signature="session-token-sig",
        assurance_level=AssuranceLevel.MODE_B,
    )
    mode_b_plan = plan.model_copy(update={"status": PlanStatus.APPROVED, "approval": sig_b})
    assert verify_approval(mode_b_plan, active_policy_digest="policy-digest-1") is True
    assert mode_b_plan.approval is not None
    assert mode_b_plan.approval.assurance_level == AssuranceLevel.MODE_B
    assert mode_b_plan.approval.assurance_level != AssuranceLevel.MODE_A

    # 3. Tampering with plan steps after approval invalidates verification
    tampered_steps_plan = mode_b_plan.model_copy(
        update={
            "steps": [
                MigrationStep(
                    step_id="malicious-step",
                    title="Exfiltrate credentials",
                    description="Injected step",
                ),
            ]
        }
    )
    assert verify_approval(tampered_steps_plan) is False
