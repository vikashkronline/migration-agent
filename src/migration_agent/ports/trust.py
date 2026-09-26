"""Application-owned ports for trust stores and cryptographic signature verification."""

from typing import Protocol, runtime_checkable

from migration_agent.domain.trust import (
    AuthorityKey,
    RepositoryBinding,
    SignatureVerificationResult,
    TrustRecord,
)


@runtime_checkable
class TrustStorePort(Protocol):
    """Boundary for managing out-of-band trusted developer Authority Keys."""

    def load_trust_record(self, project_id: str) -> TrustRecord | None:
        """Load a project's trust record from the local trust store."""

    def save_trust_record(self, record: TrustRecord) -> None:
        """Save a project's trust record in the local trust store."""

    def bootstrap_authority_key(
        self,
        project_id: str,
        authority_key: AuthorityKey,
        binding: RepositoryBinding | None = None,
    ) -> TrustRecord:
        """Add or update an Authority Key in the project's trust record."""

    def verify_repository_binding(
        self,
        project_id: str,
        root_commit_sha: str | None = None,
        remote_origin_url: str | None = None,
    ) -> bool:
        """Verify that current repository signals match the bootstrapped trust binding."""


@runtime_checkable
class SignatureVerifierPort(Protocol):
    """Boundary for cryptographic signing and signature verification."""

    def verify(
        self,
        payload_digest: str,
        signature: str,
        authority_key: AuthorityKey,
    ) -> SignatureVerificationResult:
        """Verify a signature against the payload digest and trusted authority key."""

    def sign(
        self,
        payload_digest: str,
        private_key: str,
        algorithm: str = "ed25519",
    ) -> str:
        """Generate a signature string over a canonical payload digest."""
