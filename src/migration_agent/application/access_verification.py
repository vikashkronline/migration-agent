"""Pure signed access transitions shared by local activation and trusted publication gates."""

from migration_agent.domain.access import (
    AccessDenied,
    AccessPolicy,
    AccessRevision,
    ProjectAccessBinding,
)
from migration_agent.ports.access import PublicSignaturePort


def verify_access_revision(
    revision: AccessRevision,
    previous: AccessPolicy | None,
    binding: ProjectAccessBinding,
    signatures: PublicSignaturePort,
) -> None:
    proposal = revision.proposal
    policy = proposal.candidate
    if policy.revision_nonce != proposal.nonce or proposal.snapshot_digest != policy.digest:
        raise AccessDenied(
            "ACCESS_SIGNATURE_INVALID: revision identity does not match its proposal."
        )
    for candidate_member in policy.members:
        if (
            candidate_member.public_key
            and signatures.fingerprint(candidate_member.public_key)
            != candidate_member.key_fingerprint
        ):
            raise AccessDenied("ACCESS_SIGNATURE_INVALID: member key binding does not match.")
    if policy.binding != binding:
        raise AccessDenied("ACCESS_BINDING_INVALID: revision belongs to another project.")
    expected = previous.digest if previous else None
    if proposal.base_digest != expected or policy.previous_digest != expected:
        raise AccessDenied("ACCESS_CONFLICT: signed proposal is based on another revision.")
    if policy.revision != (previous.revision + 1 if previous else 1):
        raise AccessDenied("ACCESS_CONFLICT: revision sequence is invalid.")
    authority = previous or policy
    owners = {m.principal_id: m for m in authority.members if m.principal_id in authority.owners}
    candidate_members = {m.principal_id: m for m in policy.members}
    verified: set[str] = set()
    for proof in revision.proofs:
        member = owners.get(proof.principal_id)
        if member is None or proof.key_fingerprint != member.key_fingerprint:
            member = candidate_members.get(proof.principal_id)
        if not member or not member.public_key or proof.key_fingerprint != member.key_fingerprint:
            raise AccessDenied("ACCESS_SIGNATURE_INVALID: signature identity is not bound.")
        if signatures.fingerprint(member.public_key) != member.key_fingerprint:
            raise AccessDenied("ACCESS_SIGNATURE_INVALID: mismatched key fingerprint.")
        if not signatures.verify(member.public_key, proposal.signing_digest, proof.signature):
            raise AccessDenied("ACCESS_SIGNATURE_INVALID: genuine Ed25519 approval is required.")
        verified.add(proof.key_fingerprint)
    if not any(m.key_fingerprint in verified for m in owners.values()):
        raise AccessDenied("OWNER_REQUIRED: candidate keys cannot authorize their own elevation.")
    old_keys = {m.key_fingerprint for m in previous.members} if previous else set()
    old_owners = set(previous.owners) if previous else set()
    for owner in set(policy.owners) - old_owners:
        if candidate_members[owner].key_fingerprint not in verified:
            raise AccessDenied("OWNER_CONSENT_REQUIRED: incoming owners must sign this proposal.")
    for member in policy.members:
        if (
            member.public_key
            and member.key_fingerprint not in old_keys
            and member.key_fingerprint not in verified
        ):
            raise AccessDenied(
                "ENROLLMENT_REQUIRED: new public keys must prove possession of this proposal."
            )
