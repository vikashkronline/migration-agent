"""Framework detection port and deterministic adapter registry with capability negotiation."""

from typing import Protocol, runtime_checkable

from migration_agent.domain import (
    FrameworkCapabilities,
    FrameworkCapability,
    FrameworkFingerprint,
    NegotiationResult,
    RepositorySnapshot,
    ValidationCommand,
    ValidationProfile,
)
from migration_agent.ports.transformation import (
    ComponentExtractorPort,
    ComponentRendererPort,
)


@runtime_checkable
class FrameworkAdapter(Protocol):
    """A framework adapter declaring capabilities, detection, and transformation boundaries."""

    @property
    def framework_id(self) -> str:
        """Return the stable framework identifier owned by this adapter."""

    @property
    def capabilities(self) -> FrameworkCapabilities:
        """Return the typed capability declaration for this adapter."""

    def detect(self, snapshot: RepositorySnapshot) -> FrameworkFingerprint | None:
        """Return a fingerprint when repository evidence clears the adapter threshold."""

    def get_validation_commands(self, profile: ValidationProfile) -> tuple[ValidationCommand, ...]:
        """Return allowlisted validation commands owned by this framework for the given profile."""

    def get_extractor(self) -> ComponentExtractorPort | None:
        """Return source component extractor if supported, else None."""

    def get_renderer(self) -> ComponentRendererPort | None:
        """Return target component renderer if supported, else None."""


class FrameworkAdapterRegistry:
    """Select matching adapters and negotiate capabilities without hardcoded branching."""

    def __init__(self, adapters: tuple[FrameworkAdapter, ...]) -> None:
        adapter_ids = [adapter.framework_id for adapter in adapters]
        if len(adapter_ids) != len(set(adapter_ids)):
            raise ValueError("framework adapter IDs must be unique")
        self._adapters = tuple(sorted(adapters, key=lambda adapter: adapter.framework_id))
        self._adapters_by_id = {adapter.framework_id: adapter for adapter in self._adapters}

    def get_adapter(self, framework_id: str) -> FrameworkAdapter | None:
        """Look up an adapter by its unique framework ID."""
        return self._adapters_by_id.get(framework_id)

    def has_capability(self, framework_id: str, capability: FrameworkCapability) -> bool:
        """Check whether a registered adapter supports a given capability."""
        adapter = self.get_adapter(framework_id)
        if adapter is None:
            return False
        return adapter.capabilities.has_capability(capability)

    def detect(self, snapshot: RepositorySnapshot) -> tuple[FrameworkFingerprint, ...]:
        """Detect all matching frameworks present in the repository snapshot."""
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
        adapter = self.get_adapter(framework_id)
        if adapter is not None:
            return adapter.get_validation_commands(profile)
        return ()

    def negotiate_pair(
        self, source_framework_id: str, target_framework_id: str
    ) -> NegotiationResult:
        """Negotiate migration compatibility between a source and target framework."""
        source_adapter = self.get_adapter(source_framework_id)
        if source_adapter is None:
            return NegotiationResult(
                supported=False,
                source_framework=source_framework_id,
                target_framework=target_framework_id,
                reason=f"Source framework '{source_framework_id}' is not registered.",
            )

        if not source_adapter.capabilities.has_capability(
            FrameworkCapability.SOURCE_TRANSFORMATION
        ):
            return NegotiationResult(
                supported=False,
                source_framework=source_framework_id,
                target_framework=target_framework_id,
                reason=(
                    f"Source framework '{source_framework_id}' "
                    "does not support source transformation."
                ),
            )

        if (
            source_adapter.capabilities.supported_target_frameworks
            and target_framework_id not in source_adapter.capabilities.supported_target_frameworks
        ):
            return NegotiationResult(
                supported=False,
                source_framework=source_framework_id,
                target_framework=target_framework_id,
                reason=(
                    f"Source framework '{source_framework_id}' does not support "
                    f"migrating to target '{target_framework_id}'."
                ),
            )

        target_adapter = self.get_adapter(target_framework_id)
        if target_adapter is None:
            return NegotiationResult(
                supported=False,
                source_framework=source_framework_id,
                target_framework=target_framework_id,
                reason=f"Target framework '{target_framework_id}' is not registered.",
            )

        if not target_adapter.capabilities.has_capability(
            FrameworkCapability.TARGET_TRANSFORMATION
        ):
            return NegotiationResult(
                supported=False,
                source_framework=source_framework_id,
                target_framework=target_framework_id,
                reason=(
                    f"Target framework '{target_framework_id}' "
                    "does not support target transformation."
                ),
            )

        if source_adapter.get_extractor() is None:
            return NegotiationResult(
                supported=False,
                source_framework=source_framework_id,
                target_framework=target_framework_id,
                reason=f"Source adapter '{source_framework_id}' returned no component extractor.",
            )

        if target_adapter.get_renderer() is None:
            return NegotiationResult(
                supported=False,
                source_framework=source_framework_id,
                target_framework=target_framework_id,
                reason=f"Target adapter '{target_framework_id}' returned no component renderer.",
            )

        validation_available = bool(target_adapter.capabilities.supported_validation_profiles)

        return NegotiationResult(
            supported=True,
            source_framework=source_framework_id,
            target_framework=target_framework_id,
            validation_commands_available=validation_available,
        )

    def get_supported_pairs(self) -> tuple[tuple[str, str], ...]:
        """Return all supported migration pairs among registered adapters."""
        pairs: list[tuple[str, str]] = []
        for src in self._adapters:
            for tgt in self._adapters:
                if src.framework_id != tgt.framework_id:
                    negotiation = self.negotiate_pair(src.framework_id, tgt.framework_id)
                    if negotiation.supported:
                        pairs.append((src.framework_id, tgt.framework_id))
        return tuple(sorted(pairs))
