"""Offline RBAC contracts with real ephemeral Ed25519 proofs and isolated repositories."""

import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import ValidationError
from ssh_signature_fixture import ssh_signature

from migration_agent.adapters.access_signatures import AccessSignatures
from migration_agent.adapters.access_store import AccessPointer, SignedAccessStore
from migration_agent.adapters.os_identity import current_os_identity
from migration_agent.application.access import AccessService
from migration_agent.domain.access import (
    AccessActor,
    AccessDenied,
    AccessMember,
    AccessPolicy,
    AccessProof,
    AccessRevision,
    AccessRole,
    ProjectAccessBinding,
    decide_access,
    default_roles,
)


@pytest.fixture
def security(tmp_path: Path) -> tuple[AccessService, Ed25519PrivateKey]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
    binding = ProjectAccessBinding(
        project_id="test-project",
        source_root=str(tmp_path / "source"),
        governance_root=str(tmp_path / "governance"),
        source_root_commit="a" * 40,
        governance_root_commit="b" * 40,
    )
    signatures = AccessSignatures(tmp_path / "state")
    store = SignedAccessStore(binding, tmp_path / "trust", tmp_path / "state", signatures)
    actor = AccessActor(os_identity=current_os_identity(), client="human")
    service = AccessService(store, actor, signatures)
    policy = AccessPolicy(
        binding=binding,
        revision=1,
        roles=default_roles(),
        owners=("owner",),
        members=(
            AccessMember(
                principal_id="owner",
                label="Owner",
                roles=("owner",),
                status="active",
                os_identity=actor.os_identity,
                public_key=public,
                key_fingerprint=signatures.fingerprint(public),
            ),
        ),
    )
    proposal = service.bootstrap(policy)
    service.commit(signed(proposal, private, policy.members[0]))
    return service, private


def signed(proposal, private: Ed25519PrivateKey, member: AccessMember) -> AccessRevision:
    return AccessRevision(
        proposal=proposal,
        proofs=(
            AccessProof(
                principal_id=member.principal_id,
                key_fingerprint=member.key_fingerprint or "",
                signature=ssh_signature(private, proposal.signing_digest),
            ),
        ),
    )


def test_owner_union_ceiling_agent_and_default_deny(security) -> None:
    service, _ = security
    assert service.require("access.commit").allowed
    policy = service.view()
    agent = service.actor.model_copy(update={"client": "agent"})
    assert not decide_access(policy, agent, "access.commit", int(time.time())).allowed
    assert decide_access(policy, agent, "changeset.stage", int(time.time())).allowed
    ceiling = service.actor.model_copy(update={"ceiling": frozenset({"project.read"})})
    assert not decide_access(policy, ceiling, "changeset.stage", int(time.time())).allowed
    stranger = AccessActor(os_identity="another-os-user", client="human")
    assert not decide_access(policy, stranger, "project.read", int(time.time())).allowed
    assert not service.explain("*").allowed


@pytest.mark.parametrize(
    "caps", [("*",), ("unknown.permission",), ("project.read", "project.read")]
)
def test_unknown_wildcard_and_duplicate_capabilities(caps) -> None:
    with pytest.raises(ValidationError):
        AccessRole(role_id="custom", label="Custom", capabilities=caps)


def test_membership_suspension_expiry_and_custom_roles(security) -> None:
    service, private = security
    policy = service.view()
    member = AccessMember(
        principal_id="dev",
        label="Developer",
        roles=("developer", "viewer"),
        status="active",
        os_identity="test:user",
        expires_at=int(time.time()) + 20,
    )
    candidate = policy.model_copy(
        update={
            "revision": 2,
            "previous_digest": policy.digest,
            "members": (*policy.members, member),
        }
    )
    service.commit(signed(service.propose(candidate), private, policy.members[0]))
    actor = AccessActor(os_identity="test:user", client="human")
    assert decide_access(candidate, actor, "changeset.stage", int(time.time())).allowed
    assert not decide_access(candidate, actor, "access.commit", int(time.time())).allowed
    assert not decide_access(candidate, actor, "changeset.stage", int(time.time()) + 30).allowed


def test_last_owner_unknown_role_and_duplicate_identity(security) -> None:
    service, _ = security
    data = service.view().model_dump_json()
    for invalid in (
        data.replace('"owners":["owner"]', '"owners":[]'),
        data.replace('"roles":["owner"]', '"roles":["missing"]'),
        data.replace('"status":"active"', '"status":"suspended"'),
    ):
        with pytest.raises(ValidationError):
            AccessPolicy.model_validate_json(invalid)


def test_stale_signature_replay_and_public_hmac_rejected(security) -> None:
    service, private = security
    current = service.view()
    candidate = current.model_copy(update={"revision": 2, "previous_digest": current.digest})
    proposal = service.propose(candidate)
    proof = signed(proposal, private, current.members[0])
    fake = proof.model_copy(
        update={"proofs": (proof.proofs[0].model_copy(update={"signature": "ed25519:fake-hmac"}),)}
    )
    with pytest.raises(AccessDenied, match="SIGNATURE_INVALID"):
        service.commit(fake)
    service.commit(proof)
    with pytest.raises(AccessDenied, match="ACCESS_CHANGED"):
        service.commit(proof)
    assert service.view().revision == 2


def test_external_anchor_detects_rollback_and_tampering(security) -> None:
    service, private = security
    policy = service.view()
    store = service.store
    first = (store.root / ".agent/access/current.json").read_text()
    candidate = policy.model_copy(update={"revision": 2, "previous_digest": policy.digest})
    service.commit(signed(service.propose(candidate), private, policy.members[0]))
    pointer_path = store.root / ".agent/access/current.json"
    second = pointer_path.read_text()
    pointer_path.write_text(first)
    with pytest.raises(AccessDenied, match="ROLLBACK"):
        store.read()
    pointer_path.write_text(second)
    pointer = AccessPointer.model_validate_json(second)
    manifest = store.root / f".agent/access/revisions/{pointer.locator}/manifest.json"
    manifest.write_text(manifest.read_text().replace('"label": "Owner"', '"label": "Tampered"'))
    with pytest.raises(AccessDenied, match="CORRUPT"):
        store.read()


def test_new_owner_and_member_key_need_possession(security) -> None:
    service, private = security
    policy = service.view()
    new_key = Ed25519PrivateKey.generate()
    public = new_key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
    incoming = policy.members[0].model_copy(
        update={
            "principal_id": "incoming",
            "os_identity": "test:incoming",
            "public_key": public,
            "key_fingerprint": service.signatures.fingerprint(public),
        }
    )
    candidate = policy.model_copy(
        update={
            "revision": 2,
            "previous_digest": policy.digest,
            "members": (*policy.members, incoming),
            "owners": ("incoming",),
        }
    )
    proposal = service.propose(candidate)
    outgoing = signed(proposal, private, policy.members[0])
    with pytest.raises(AccessDenied, match="OWNER_CONSENT_REQUIRED"):
        service.commit(outgoing)
    incoming_proof = signed(proposal, new_key, incoming).proofs[0]
    service.commit(outgoing.model_copy(update={"proofs": (*outgoing.proofs, incoming_proof)}))
    assert service.view().owners == ("incoming",)


def test_corrupt_trust_no_fallback_and_overlapping_roots(security, tmp_path: Path) -> None:
    service, _ = security
    store = service.store
    (store.trust / store.anchor_name).write_text("{}")
    with pytest.raises(ValidationError):
        store.read()
    with pytest.raises(ValueError, match="UNSAFE_ROOTS"):
        SignedAccessStore(
            store.binding, store.root / "trust", tmp_path / "state", service.signatures
        )


def test_os_identity_is_stable() -> None:
    assert current_os_identity() == current_os_identity()
    assert current_os_identity().startswith(("windows:S-1-", "posix:"))


def test_interrupted_activation_fails_closed_and_recovers(security, monkeypatch):
    service, private = security
    before = service.view()
    proposal = service.propose(
        before.model_copy(update={"revision": 2, "previous_digest": before.digest})
    )
    store = service.store
    write = store._write

    def interrupted(root, path, value):
        if path == ".agent/access/current.json":
            raise OSError("Injected activation interruption")
        write(root, path, value)

    monkeypatch.setattr(store, "_write", interrupted)
    with pytest.raises(OSError, match="interruption"):
        service.commit(signed(proposal, private, before.members[0]))
    with pytest.raises(AccessDenied, match="ACTIVATION_PENDING"):
        store.read()
    monkeypatch.setattr(store, "_write", write)
    store.recover()
    assert service.view().revision == 2
    assert not (store.trust / store.intent_name).exists()


def test_access_reads_do_not_take_writer_fence_and_activation_is_serialized(security):
    service, private = security
    before = service.view()
    proposal = service.propose(
        before.model_copy(update={"revision": 2, "previous_digest": before.digest})
    )
    other = SignedAccessStore(
        service.store.binding, service.store.trust, service.store.state, service.signatures
    )
    with service.store.fence():
        assert other.read().digest == before.digest
        with pytest.raises(ValueError, match="WRITER_BUSY"):
            other.activate(signed(proposal, private, before.members[0]))
    assert service.view().digest == before.digest


def test_equal_grant_proposals_have_distinct_immutable_locators(security):
    service, _ = security
    before = service.view()
    candidate = before.model_copy(update={"revision": 2, "previous_digest": before.digest})
    first, second = service.propose(candidate), service.propose(candidate)
    assert first.snapshot_digest != second.snapshot_digest
    assert first.revision_locator != second.revision_locator
    assert first.candidate.roles == second.candidate.roles


def test_recovery_rejects_oversized_anchor_and_retains_intent(security, monkeypatch):
    service, private = security
    store = service.store
    before = service.view()
    proposal = service.propose(
        before.model_copy(update={"revision": 2, "previous_digest": before.digest})
    )
    pointer_before = (store.root / ".agent/access/current.json").read_bytes()
    write = store._write

    def interrupted(root, path, value):
        if path == ".agent/access/current.json":
            raise OSError("Injected activation interruption")
        write(root, path, value)

    monkeypatch.setattr(store, "_write", interrupted)
    with pytest.raises(OSError, match="interruption"):
        service.commit(signed(proposal, private, before.members[0]))
    monkeypatch.setattr(store, "_write", write)
    anchor_path = store.trust / store.anchor_name
    valid_anchor = anchor_path.read_bytes()
    anchor_path.write_bytes(b"x" * 2_000_001)
    with pytest.raises(AccessDenied, match="ACCESS_CORRUPT"):
        store.recover()
    assert (store.root / ".agent/access/current.json").read_bytes() == pointer_before
    assert (store.trust / store.intent_name).is_file()
    assert anchor_path.stat().st_size == 2_000_001
    anchor_path.write_bytes(valid_anchor)
    store.recover()
    assert service.view().revision == 2


@pytest.mark.parametrize("clock", ["before_creation", "at_expiry"])
def test_activation_rejects_clock_outside_exact_approval_window(security, monkeypatch, clock):
    service, private = security
    before = service.view()
    proposal = service.propose(
        before.model_copy(update={"revision": 2, "previous_digest": before.digest})
    )
    revision = signed(proposal, private, before.members[0])
    now = proposal.created_at - 1 if clock == "before_creation" else proposal.expires_at
    monkeypatch.setattr("migration_agent.adapters.access_store.time.time", lambda: now)
    with pytest.raises(AccessDenied, match="ACCESS_EXPIRED"):
        service.store.activate(revision)
    assert service.store.read().digest == before.digest
