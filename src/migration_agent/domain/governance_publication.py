"""Git publication evidence, independent of Git client and transport implementations."""

from pydantic import Field

from migration_agent.domain.access import AccessModel, AccessRevision


class GovernancePublication(AccessModel):
    commit_id: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    revisions: tuple[AccessRevision, ...] = Field(min_length=1, max_length=10000)
    rule_digests: dict[str, str] = Field(max_length=512)


class PublicationDecision(AccessModel):
    accepted: bool
    reason: str
    candidate_commit: str
    access_digest: str
    revision: int
