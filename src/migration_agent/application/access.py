"""Shared owner administration and authorization against verified snapshots."""

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from migration_agent.domain.access import (
    CAPABILITIES,
    AccessActor,
    AccessDecision,
    AccessDenied,
    AccessPolicy,
    AccessProof,
    AccessProposal,
    AccessRevision,
    GovernanceFileChange,
    decide_access,
)
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.ports.access import AccessStorePort, PublicSignaturePort


class AccessService:
    def __init__(
        self, store: AccessStorePort, actor: AccessActor, signatures: PublicSignaturePort
    ) -> None:
        self.store = store
        self.actor = actor
        self.signatures = signatures

    def explain(self, capability: str) -> AccessDecision:
        return decide_access(self.store.read(), self.actor, capability, int(time.time()))

    def require(self, capability: str, expected_digest: str | None = None) -> AccessDecision:
        decision = self.explain(capability)
        if expected_digest and decision.access_digest != expected_digest:
            raise AccessDenied("ACCESS_CHANGED: refresh permissions and repeat the operation.")
        if not decision.allowed:
            raise AccessDenied(
                "CAPABILITY_DENIED: current project membership does not grant this action."
            )
        return decision

    @contextmanager
    def fence(self, capability: str) -> Iterator[None]:
        with self.store.fence():
            self.require(capability)
            yield

    def require_signature(self, capability: str, fingerprint: str | None) -> None:
        decision = self.require(capability)
        if fingerprint is not None:
            member = next(
                (m for m in self.store.read().members if m.principal_id == decision.principal_id),
                None,
            )
            if not member or member.key_fingerprint != fingerprint:
                raise AccessDenied(
                    "SIGNER_MISMATCH: signing key must belong to the authorized principal."
                )

    def view(self) -> AccessPolicy:
        self.require("access.read")
        return self.store.read()

    def propose(
        self, candidate: AccessPolicy, governance_changes: tuple[GovernanceFileChange, ...] = ()
    ) -> AccessProposal:
        candidate = AccessPolicy.model_validate_json(candidate.model_dump_json())
        self.require("access.propose")
        current = self.store.read()
        if (
            candidate.binding != current.binding
            or candidate.revision != current.revision + 1
            or candidate.previous_digest != current.digest
        ):
            raise ValueError("ACCESS_CONFLICT: propose against the current project revision.")
        if candidate.rules != current.rules or governance_changes:
            self.require("rules.manage")
        return self._proposal(candidate, current.digest, governance_changes)

    def bootstrap(self, candidate: AccessPolicy) -> AccessProposal:
        candidate = AccessPolicy.model_validate_json(candidate.model_dump_json())
        if self.actor.client != "human" or candidate.revision != 1 or candidate.previous_digest:
            raise AccessDenied("BOOTSTRAP_INVALID: a human must create the first revision.")
        if candidate.binding != self.store.binding:
            raise ValueError("PROJECT_MISMATCH: bootstrap is bound to another project.")
        owner = next(
            (m for m in candidate.members if m.os_identity == self.actor.os_identity), None
        )
        if not owner or owner.principal_id not in candidate.owners:
            raise AccessDenied("BOOTSTRAP_INVALID: owner must bind the current OS identity.")
        return self._proposal(candidate, None)

    def _proposal(
        self,
        candidate: AccessPolicy,
        base: str | None,
        governance_changes: tuple[GovernanceFileChange, ...] = (),
    ) -> AccessProposal:
        if len(candidate.model_dump_json().encode("utf-8")) > 1_000_000:
            raise ValueError("ACCESS_TOO_LARGE: policy exceeds its proposal budget.")
        if RedactionPolicy().contains_secret(candidate.model_dump_json()):
            raise ValueError("ACCESS_SECRET_REJECTED: policy records cannot contain credentials.")
        for member in candidate.members:
            if (
                member.public_key
                and self.signatures.fingerprint(member.public_key) != member.key_fingerprint
            ):
                raise ValueError("KEY_INVALID: fingerprint does not match the public key.")
        now = int(time.time())
        nonce = uuid.uuid4().hex
        candidate = candidate.model_copy(update={"revision_nonce": nonce})
        proposal = AccessProposal(
            proposal_id=uuid.uuid4().hex,
            candidate=candidate,
            snapshot_digest=candidate.digest,
            revision_locator=self.store.locator(candidate.digest),
            base_digest=base,
            proposer=self.actor.os_identity,
            created_at=now,
            expires_at=now + 900,
            nonce=nonce,
            governance_changes=governance_changes,
        )
        if RedactionPolicy().contains_secret(proposal.model_dump_json()):
            raise ValueError("ACCESS_SECRET_REJECTED: governance cannot contain credentials.")
        self.store.save_proposal(proposal)
        return proposal

    def review(self, proposal_id: str) -> AccessProposal:
        proposal = self.store.proposal(proposal_id)
        if proposal.base_digest:
            self.require("access.commit", proposal.base_digest)
        elif self.actor.client != "human" or proposal.proposer != self.actor.os_identity:
            raise AccessDenied("BOOTSTRAP_INVALID: only the proposed local owner can review.")
        if proposal.expires_at <= int(time.time()):
            raise ValueError("ACCESS_EXPIRED: create a fresh proposal.")
        return proposal

    def sign(self, proposal_id: str) -> AccessRevision:
        proposal = self.review(proposal_id)
        policy = self.store.read() if proposal.base_digest else proposal.candidate
        owner = next((m for m in policy.members if m.os_identity == self.actor.os_identity), None)
        if not owner or owner.principal_id not in policy.owners or not owner.public_key:
            raise AccessDenied("OWNER_REQUIRED: access activation requires a current owner.")
        signature = self.signatures.sign(owner.public_key, proposal.signing_digest)
        return AccessRevision(
            proposal=proposal,
            proofs=(
                AccessProof(
                    principal_id=owner.principal_id,
                    key_fingerprint=owner.key_fingerprint or "",
                    signature=signature,
                ),
            ),
        )

    def commit(self, revision: AccessRevision) -> AccessPolicy:
        if self.actor.client != "human":
            raise AccessDenied("HUMAN_REQUIRED: an agent session cannot activate access changes.")
        saved = self.review(revision.proposal.proposal_id)
        if revision.proposal.governance_changes:
            self.require("rules.manage", revision.proposal.base_digest)
        if saved != revision.proposal:
            raise ValueError("ACCESS_CONFLICT: signature must match the saved exact proposal.")
        self.store.activate(revision)
        return self.store.read()

    @staticmethod
    def catalog() -> tuple[str, ...]:
        return tuple(sorted(CAPABILITIES))
