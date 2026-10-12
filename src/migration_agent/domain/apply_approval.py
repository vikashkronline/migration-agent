"""Exact artifact review and approval records; no caller-supplied bearer authorization."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import DestinationBinding
from migration_agent.domain.host_workflow import WorkflowModel
from migration_agent.domain.planning import AssuranceLevel


class ApplyApprovalRecord(WorkflowModel):
    project_id: str
    run_id: str
    plan_id: str
    step_id: str
    changeset_id: str
    changeset_digest: str
    policy_digest: str
    base_revision: str
    worktree_fingerprint: str
    validation_digest: str
    action: Literal["APPLY_CHANGESET"] = "APPLY_CHANGESET"
    actor: str
    principal_id: str | None = None
    access_digest: str | None = None
    assurance_level: AssuranceLevel
    key_fingerprint: str | None = None
    signature: str = ""
    nonce: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    destination: DestinationBinding | None = None

    @property
    def signing_digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"signature"})
        if self.destination is None:
            payload.pop("destination", None)
        return compute_canonical_digest(payload)


class ReviewRequestPayload(WorkflowModel):
    project_id: str
    run_id: str
    plan_id: str
    step_id: str
    changeset_id: str
    changeset_digest: str
    policy_digest: str
    base_revision: str
    worktree_fingerprint: str
    validation_digest: str
    required_assurance: AssuranceLevel
    diff: str
    review_command: tuple[str, ...]
    destination: DestinationBinding | None = None
    signer_key_fingerprint: str | None = None
    message: str = "APPROVAL_REQUIRED: human review must run in a trusted terminal."


class HumanDecision(WorkflowModel):
    confirmed: bool
    actor: str
    assurance: AssuranceLevel
    key_fingerprint: str | None = None
