"""Verify a governance push against an external trusted revision and signatures."""

from migration_agent.application.access_verification import verify_access_revision
from migration_agent.domain.access import AccessDenied, AccessPolicy
from migration_agent.domain.governance_publication import GovernancePublication, PublicationDecision
from migration_agent.ports.access import PublicSignaturePort


def verify_publication(
    trusted: AccessPolicy,
    candidate: GovernancePublication,
    signatures: PublicSignaturePort,
) -> PublicationDecision:
    previous: AccessPolicy | None = None
    seen_nonces: set[str] = set()
    contains_trusted = False
    for revision in candidate.revisions:
        verify_access_revision(revision, previous, trusted.binding, signatures)
        if revision.proposal.nonce in seen_nonces:
            raise AccessDenied("PUBLICATION_REPLAY: signed proposal nonce was reused.")
        seen_nonces.add(revision.proposal.nonce)
        previous = revision.proposal.candidate
        if previous.digest == trusted.digest:
            contains_trusted = True
    if not contains_trusted or previous is None or previous.revision < trusted.revision:
        raise AccessDenied(
            "PUBLICATION_ROLLBACK: candidate must extend the externally trusted history."
        )
    if previous.rules != candidate.rule_digests:
        raise AccessDenied(
            "PUBLICATION_RULES_INVALID: pushed security rule bytes are not owner-approved."
        )
    return PublicationDecision(
        accepted=True,
        reason="VERIFIED_SIGNED_GOVERNANCE",
        candidate_commit=candidate.commit_id,
        access_digest=previous.digest,
        revision=previous.revision,
    )
