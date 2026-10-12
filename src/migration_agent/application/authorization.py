"""Fail-closed defaults for services without a trusted composition context."""

from collections.abc import Iterator
from contextlib import contextmanager

from migration_agent.domain.access import AccessDecision, AccessDenied


class UnboundAuthorization:
    def require_signature(self, capability: str, fingerprint: str | None) -> None:
        self.require(capability)

    def require(self, capability: str, expected_digest: str | None = None) -> AccessDecision:
        raise AccessDenied("ACCESS_CONTEXT_REQUIRED: compose verified project authorization.")

    @contextmanager
    def fence(self, capability: str) -> Iterator[None]:
        self.require(capability)
        yield
