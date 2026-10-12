"""Workflow signing authority resolved from current externally anchored access."""

import time
from datetime import UTC, datetime

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.domain.apply_approval import ApplyApprovalRecord
from migration_agent.domain.execution import NativeExecutionConsent
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.trust import AuthorityKey


class AccessApprovalAuthority:
    def __init__(self, authorization: ProjectAuthorization, workflow_project_id: str) -> None:
        self.authorization = authorization
        self.project_id = workflow_project_id

    def key(
        self, project_id: str, fingerprint: str, root_commit: str | None = None
    ) -> AuthorityKey:
        policy = self.authorization.service().store.read()
        if project_id != self.project_id or (
            root_commit and root_commit != policy.binding.source_root_commit
        ):
            raise ValueError("AUTHORITY_BINDING_INVALID: authority belongs to another project.")
        member = next((m for m in policy.members if m.key_fingerprint == fingerprint), None)
        if (
            not member
            or not member.public_key
            or member.status != "active"
            or (member.expires_at and member.expires_at <= int(time.time()))
        ):
            raise ValueError("AUTHORITY_REQUIRED: active enrolled key is unavailable.")
        return AuthorityKey(
            key_id=member.principal_id,
            public_key=member.public_key,
            fingerprint=fingerprint,
            algorithm="ed25519",
            created_at=datetime.now(UTC).isoformat(),
        )

    def accepts(self, record: ApplyApprovalRecord | NativeExecutionConsent) -> bool:
        policy = self.authorization.service().store.read()
        if record.project_id != self.project_id or record.access_digest != policy.digest:
            return False
        member = next((m for m in policy.members if m.principal_id == record.principal_id), None)
        if (
            not member
            or member.status != "active"
            or (member.expires_at and member.expires_at <= int(time.time()))
        ):
            return False
        roles = {role.role_id: role for role in policy.roles}
        grants = {capability for role in member.roles for capability in roles[role].capabilities}
        capability = (
            "execution.consent" if isinstance(record, NativeExecutionConsent) else "approval.sign"
        )
        if capability not in grants:
            return False
        if record.assurance_level == AssuranceLevel.MODE_B:
            return member.os_identity == self.authorization.actor.os_identity
        return member.key_fingerprint == record.key_fingerprint
