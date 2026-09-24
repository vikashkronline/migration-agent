"""Framework detection port and deterministic adapter registry."""

from typing import Protocol

from migration_agent.domain import (
    FrameworkFingerprint,
    RepositorySnapshot,
    ValidationCommand,
    ValidationProfile,
)


class FrameworkAdapter(Protocol):
    """A framework-specific detector that returns evidence, never transformations."""

    @property
    def framework_id(self) -> str:
        """Return the stable framework identifier owned by this adapter."""

    def detect(self, snapshot: RepositorySnapshot) -> FrameworkFingerprint | None:
        """Return a fingerprint when repository evidence clears the adapter threshold."""

    def get_validation_commands(self, profile: ValidationProfile) -> tuple[ValidationCommand, ...]:
        """Return allowlisted validation commands owned by this framework for the given profile."""


class FrameworkAdapterRegistry:
    """Select all matching adapters without framework-specific branching."""

    def __init__(self, adapters: tuple[FrameworkAdapter, ...]) -> None:
        adapter_ids = [adapter.framework_id for adapter in adapters]
        if len(adapter_ids) != len(set(adapter_ids)):
            raise ValueError("framework adapter IDs must be unique")
        self._adapters = tuple(sorted(adapters, key=lambda adapter: adapter.framework_id))

    def detect(self, snapshot: RepositorySnapshot) -> tuple[FrameworkFingerprint, ...]:
        detected = [
            fingerprint
            for adapter in self._adapters
            if (fingerprint := adapter.detect(snapshot)) is not None
        ]
        return tuple(sorted(detected, key=lambda item: item.framework_id))

    def get_validation_commands(
        self, framework_id: str, profile: ValidationProfile
    ) -> tuple[ValidationCommand, ...]:
        """Retrieve allowlisted validation commands for a specific framework and profile."""
        for adapter in self._adapters:
            if adapter.framework_id == framework_id:
                return adapter.get_validation_commands(profile)
        return ()
