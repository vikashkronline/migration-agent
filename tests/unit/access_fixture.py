"""Explicit authorization double for non-security workflow mechanics tests."""

from contextlib import contextmanager

from migration_agent.domain.access import CAPABILITIES, AccessDecision, AccessDenied


class WorkflowAuthorizationFixture:
    def require_signature(self, capability, fingerprint):
        self.require(capability)

    def require(self, capability, expected_digest=None):
        if capability not in CAPABILITIES:
            raise AccessDenied("CAPABILITY_DENIED")
        if expected_digest and expected_digest != "sha256:" + "f" * 64:
            raise AccessDenied("ACCESS_CHANGED")
        return AccessDecision(
            allowed=True,
            reason="TEST_HARNESS",
            principal_id="fixture",
            access_digest="sha256:" + "f" * 64,
            capabilities=tuple(sorted(CAPABILITIES)),
        )

    @contextmanager
    def fence(self, capability):
        self.require(capability)
        yield
