from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.planning import AssuranceLevel

__all__ = [
    "AuthorityKey",
    "RepositoryBinding",
    "SignatureVerificationResult",
    "TrustRecord",
]


class AuthorityKey(BaseModel):
    """An authority signing key trusted to authorize policies and ChangeSets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key_id: str = Field(min_length=1)
    algorithm: str = Field(default="ed25519")
    public_key: str = Field(min_length=1)
    fingerprint: str = Field(min_length=1)
    created_at: str
    revoked: bool = False


class RepositoryBinding(BaseModel):
    """Binding signals associating authority keys to a specific repository."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    root_commit_sha: str | None = None
    remote_origin_url: str | None = None


class TrustRecord(BaseModel):
    """Durable trust record stored out-of-band in developer user-data store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: str = Field(min_length=1)
    authority_keys: tuple[AuthorityKey, ...] = Field(default_factory=tuple)
    repository_binding: RepositoryBinding = Field(default_factory=RepositoryBinding)
    schema_version: int = 1

    def find_key(self, key_id_or_fingerprint: str) -> AuthorityKey | None:
        """Find an active authority key by ID or fingerprint."""
        for key in self.authority_keys:
            if (
                key.key_id == key_id_or_fingerprint or key.fingerprint == key_id_or_fingerprint
            ) and not key.revoked:
                return key
        return None


class SignatureVerificationResult(BaseModel):
    """Result of validating an ApprovalSignature against the trust store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verified: bool
    assurance_level: AssuranceLevel
    key_id: str | None = None
    key_fingerprint: str | None = None
    reason: str | None = None
