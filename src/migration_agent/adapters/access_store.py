"""Immutable signed access history, external anti-rollback anchor and bounded activation fence."""

import hashlib
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import Field

from migration_agent.adapters.access_rules import rule_text_digest
from migration_agent.adapters.apply_lock import ExclusiveApplyLock
from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.application.access_verification import verify_access_revision
from migration_agent.domain.access import (
    AccessDenied,
    AccessModel,
    AccessPolicy,
    AccessProposal,
    AccessRevision,
    GovernanceFileChange,
    ProjectAccessBinding,
)
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.ports.access import PublicSignaturePort
from migration_agent.ports.filesystem import InspectionPolicy


class AccessPointer(AccessModel):
    schema_version: Literal[2] = 2
    revision: int = Field(ge=1, le=10000)
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    locator: str = Field(pattern=r"^rev-[0-9a-f]{16}(?:[0-9a-f]{8}){0,2}$")


class AccessAnchor(AccessModel):
    binding: ProjectAccessBinding
    initial_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    initial_owner_keys: tuple[str, ...] = Field(min_length=1, max_length=32)
    current: AccessPointer
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    consumed_nonces: tuple[str, ...] = Field(min_length=1, max_length=10000)


class ActivationIntent(AccessModel):
    previous: AccessAnchor | None
    candidate: AccessAnchor
    governance_changes: tuple[GovernanceFileChange, ...] = ()


class SignedAccessStore:
    def __init__(
        self,
        binding: ProjectAccessBinding,
        trust_root: Path,
        state_root: Path,
        signatures: PublicSignaturePort,
    ) -> None:
        self.binding = binding
        self.root = Path(binding.governance_root).resolve()
        self.trust = trust_root.resolve()
        self.state = state_root.resolve()
        self.signatures = signatures
        source = Path(binding.source_root).resolve()
        roots = (self.root, self.trust, self.state, source)
        for index, left in enumerate(roots):
            for right in roots[index + 1 :]:
                if left.is_relative_to(right) or right.is_relative_to(left):
                    raise ValueError(
                        "UNSAFE_ROOTS: governance, source, state and trust must be disjoint."
                    )
        self.identity = hashlib.sha256(binding.project_id.encode()).hexdigest()[:24]
        self.lock = ExclusiveApplyLock(self.trust / "access-locks")
        self.anchor_name = f"access-{self.identity}.json"
        self.intent_name = f"access-{self.identity}.intent.json"
        for root in (self.root, self.trust, self.state):
            root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def fence(self) -> Iterator[None]:
        with self.lock.acquire(f"access-{self.identity}"):
            yield

    def _path(self, root: Path, relative: str) -> Path:
        path = validate_repository_path(root, relative)
        if os.name == "nt" and len(str(path).encode("utf-16-le")) // 2 > 230:
            raise ValueError(
                "ACCESS_PATH_TOO_LONG: use a shorter external governance or state root."
            )
        return path

    def _read_text(self, root: Path, relative: str) -> str:
        path = self._path(root, relative)
        if not path.is_file() or path.stat().st_size > 2_000_000:
            raise AccessDenied("ACCESS_CORRUPT: required bounded access record is missing.")
        return read_repository_text(
            root, relative, policy=InspectionPolicy(max_text_file_bytes=2_000_000)
        )

    def _write(self, root: Path, relative: str, value: AccessModel) -> None:
        serialized = value.model_dump_json(indent=2) + "\n"
        self._write_text(root, relative, serialized)

    def _write_text(self, root: Path, relative: str, serialized: str) -> None:
        if len(serialized.encode("utf-8")) > 2_000_000:
            raise ValueError("ACCESS_TOO_LARGE: access record exceeds its storage budget.")
        path = self._path(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path(root, relative + ".tmp-" + uuid.uuid4().hex[:8])
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            validate_repository_path(root, relative)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        if os.name != "nt":
            handle = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(handle)
            finally:
                os.close(handle)

    def initialized(self) -> bool:
        return self._path(self.trust, self.anchor_name).exists()

    def _anchor(self) -> AccessAnchor:
        if self._path(self.trust, self.intent_name).exists():
            raise AccessDenied(
                "ACCESS_ACTIVATION_PENDING: run access recover before using the project."
            )
        if not self.initialized():
            raise AccessDenied(
                "ACCESS_BOOTSTRAP_REQUIRED: enroll the project owner with access bootstrap."
            )
        anchor = AccessAnchor.model_validate_json(self._read_text(self.trust, self.anchor_name))
        if anchor.binding != self.binding:
            raise AccessDenied(
                "ACCESS_BINDING_INVALID: trusted project roots or repository changed."
            )
        return anchor

    def _revision(self, pointer: AccessPointer) -> AccessRevision:
        revision = AccessRevision.model_validate_json(
            self._read_text(self.root, f".agent/access/revisions/{pointer.locator}/manifest.json")
        )
        policy = revision.proposal.candidate
        if policy.digest != pointer.digest or policy.revision != pointer.revision:
            raise AccessDenied("ACCESS_CORRUPT: full revision digest does not match its pointer.")
        return revision

    def _locate(self, digest: str) -> str:
        for length in (16, 24, 32):
            locator = "rev-" + digest.split(":")[1][:length]
            path = self._path(self.root, f".agent/access/revisions/{locator}/manifest.json")
            if not path.exists():
                return locator
            existing = AccessRevision.model_validate_json(
                self._read_text(self.root, f".agent/access/revisions/{locator}/manifest.json")
            )
            if existing.proposal.candidate.digest == digest:
                return locator
        raise AccessDenied(
            "ACCESS_DIGEST_COLLISION: cannot allocate an unambiguous revision directory."
        )

    def locator(self, digest: str) -> str:
        return self._locate(digest)

    def _verify(self, revision: AccessRevision, previous: AccessPolicy | None) -> None:
        verify_access_revision(revision, previous, self.binding, self.signatures)
        for change in revision.proposal.governance_changes:
            if rule_text_digest(
                change.path, change.content
            ) != revision.proposal.candidate.rules.get(change.path):
                raise AccessDenied("ACCESS_SIGNATURE_INVALID: protected content is not signed.")

    def _governance_changes(
        self,
        changes: tuple[GovernanceFileChange, ...],
        *,
        write: bool = False,
        recovering: bool = False,
    ) -> None:
        for change in changes:
            path = self._path(self.root, change.path)
            current = (
                "sha256:"
                + hashlib.sha256(self._read_text(self.root, change.path).encode()).hexdigest()
                if path.exists()
                else None
            )
            target = "sha256:" + hashlib.sha256(change.content.encode()).hexdigest()
            if current != change.previous_digest and not (recovering and current == target):
                raise AccessDenied(
                    "ACCESS_CONFLICT: protected file changed; review a fresh proposal."
                )
            if write:
                self._write_text(self.root, change.path, change.content)

    def _history(self, anchor: AccessAnchor) -> AccessPolicy:
        reversed_history = []
        pointer = anchor.current
        while True:
            revision = self._revision(pointer)
            reversed_history.append(revision)
            previous_digest = revision.proposal.candidate.previous_digest
            if not previous_digest:
                break
            pointer = AccessPointer(
                revision=pointer.revision - 1,
                digest=previous_digest,
                locator=self._locate(previous_digest),
            )
        previous = None
        nonces: set[str] = set()
        for revision in reversed(reversed_history):
            if revision.proposal.nonce in nonces:
                raise AccessDenied("ACCESS_REPLAY: access proposal nonce was reused.")
            nonces.add(revision.proposal.nonce)
            self._verify(revision, previous)
            if previous is None:
                initial = revision.proposal.candidate
                keys = tuple(
                    sorted(
                        m.key_fingerprint or ""
                        for m in initial.members
                        if m.principal_id in initial.owners
                    )
                )
                if initial.digest != anchor.initial_digest or keys != anchor.initial_owner_keys:
                    raise AccessDenied(
                        "ACCESS_TRUST_INVALID: initial owner does not match external trust."
                    )
            previous = revision.proposal.candidate
        if previous is None:
            raise AccessDenied("ACCESS_CORRUPT: signed history is empty.")
        return previous

    def read(self) -> AccessPolicy:
        for _ in range(3):
            anchor = self._anchor()
            pointer = AccessPointer.model_validate_json(
                self._read_text(self.root, ".agent/access/current.json")
            )
            if pointer != anchor.current:
                raise AccessDenied(
                    "ACCESS_ROLLBACK: active pointer differs from the external trusted head."
                )
            revision = self._revision(pointer)
            if compute_canonical_digest(revision) != anchor.manifest_digest:
                raise AccessDenied(
                    "ACCESS_CORRUPT: revision proof differs from the verified external anchor."
                )
            policy = revision.proposal.candidate
            if self._anchor() == anchor:
                return policy
        raise AccessDenied(
            "ACCESS_CHANGED: access changed repeatedly; retry after activation completes."
        )

    def save_proposal(self, proposal: AccessProposal) -> None:
        self._write(self.state, f"access-proposals/{proposal.proposal_id}.json", proposal)

    def proposal(self, proposal_id: str) -> AccessProposal:
        if len(proposal_id) != 32 or any(c not in "0123456789abcdef" for c in proposal_id):
            raise ValueError("ACCESS_PROPOSAL_INVALID: use the exact proposal ID.")
        return AccessProposal.model_validate_json(
            self._read_text(self.state, f"access-proposals/{proposal_id}.json")
        )

    def activate(self, revision: AccessRevision) -> None:
        with self.fence():
            old_anchor = self._anchor() if self.initialized() else None
            previous = self.read() if old_anchor else None
            if self._path(self.root, ".agent/access/current.json").exists() and old_anchor is None:
                raise AccessDenied(
                    "ACCESS_ADOPTION_REQUIRED: existing access files need trusted adoption."
                )
            proposal = revision.proposal
            if old_anchor and proposal.nonce in old_anchor.consumed_nonces:
                raise AccessDenied("ACCESS_REPLAY: proposal nonce has already been activated.")
            now = int(time.time())
            if (
                not proposal.created_at <= now < proposal.expires_at
                or proposal.expires_at - proposal.created_at > 900
            ):
                raise AccessDenied(
                    "ACCESS_EXPIRED: exact approval has expired or has an invalid lifetime."
                )
            self._verify(revision, previous)
            self._governance_changes(proposal.governance_changes)
            pointer = AccessPointer(
                revision=proposal.candidate.revision,
                digest=proposal.candidate.digest,
                locator=self._locate(proposal.candidate.digest),
            )
            if pointer.locator != proposal.revision_locator:
                raise AccessDenied(
                    "ACCESS_CONFLICT: approved revision locator changed; propose again."
                )
            self._write(
                self.root, f".agent/access/revisions/{pointer.locator}/manifest.json", revision
            )
            anchor = AccessAnchor(
                manifest_digest=compute_canonical_digest(revision),
                consumed_nonces=(
                    *(old_anchor.consumed_nonces if old_anchor else ()),
                    proposal.nonce,
                ),
                binding=self.binding,
                initial_digest=old_anchor.initial_digest if old_anchor else pointer.digest,
                initial_owner_keys=old_anchor.initial_owner_keys
                if old_anchor
                else tuple(
                    sorted(
                        m.key_fingerprint or ""
                        for m in proposal.candidate.members
                        if m.principal_id in proposal.candidate.owners
                    )
                ),
                current=pointer,
            )
            self._write(
                self.trust,
                self.intent_name,
                ActivationIntent(
                    previous=old_anchor,
                    candidate=anchor,
                    governance_changes=proposal.governance_changes,
                ),
            )
            self._governance_changes(proposal.governance_changes, write=True)
            self._write(self.trust, self.anchor_name, anchor)
            self._write(self.root, ".agent/access/current.json", pointer)
            self._path(self.trust, self.intent_name).unlink()

    def is_active_revision(self, revision: AccessRevision) -> bool:
        policy = self.read()
        if policy.digest != revision.proposal.candidate.digest:
            return False
        anchor = self._anchor()
        return bool(anchor and self._revision(anchor.current) == revision)

    def recover(self) -> None:
        with self.fence():
            intent = ActivationIntent.model_validate_json(
                self._read_text(self.trust, self.intent_name)
            )
            current_path = self._path(self.trust, self.anchor_name)
            current = (
                AccessAnchor.model_validate_json(self._read_text(self.trust, self.anchor_name))
                if current_path.exists()
                else None
            )
            if (
                current not in (intent.previous, intent.candidate)
                or intent.candidate.binding != self.binding
            ):
                raise AccessDenied(
                    "ACCESS_RECOVERY_INVALID: activation intent conflicts with trusted state."
                )
            self._history(intent.candidate)
            revision = self._revision(intent.candidate.current)
            if intent.governance_changes != revision.proposal.governance_changes:
                raise AccessDenied(
                    "ACCESS_RECOVERY_INVALID: protected intent does not match signed content."
                )
            self._governance_changes(intent.governance_changes, write=True, recovering=True)
            self._write(self.trust, self.anchor_name, intent.candidate)
            self._write(self.root, ".agent/access/current.json", intent.candidate.current)
            self._path(self.trust, self.intent_name).unlink()
