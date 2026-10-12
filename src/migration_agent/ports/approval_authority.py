"""Trusted workflow key and issuer eligibility resolution."""

from typing import Protocol

from migration_agent.domain.apply_approval import ApplyApprovalRecord
from migration_agent.domain.execution import NativeExecutionConsent
from migration_agent.domain.trust import AuthorityKey


class ApprovalAuthorityPort(Protocol):
    def key(
        self, project_id: str, fingerprint: str, root_commit: str | None = None
    ) -> AuthorityKey: ...
    def accepts(self, record: ApplyApprovalRecord | NativeExecutionConsent) -> bool: ...
