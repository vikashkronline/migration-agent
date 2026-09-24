"""Unit tests for framework capability negotiation and pair compatibility."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from migration_agent.adapters import (
    AngularAdapter,
    AngularJsDirectiveAdapter,
    EmberClassicAdapter,
    LocalWorkspaceAdapter,
    SafeFilesystemInspector,
)
from migration_agent.application.transformation import TransformationService
from migration_agent.domain import (
    FrameworkCapabilities,
    FrameworkCapability,
    ValidationProfile,
)
from migration_agent.ports import FrameworkAdapterRegistry


def test_framework_capabilities_model_invariants() -> None:
    caps = FrameworkCapabilities(
        supports_inventory=True,
        supports_validation=True,
        supports_source_transformation=True,
        supports_target_transformation=False,
        supported_validation_profiles=(ValidationProfile.TEST,),
        supported_target_frameworks=("angular",),
    )
    assert caps.has_capability(FrameworkCapability.INVENTORY) is True
    assert caps.has_capability(FrameworkCapability.VALIDATION) is True
    assert caps.has_capability(FrameworkCapability.SOURCE_TRANSFORMATION) is True
    assert caps.has_capability(FrameworkCapability.TARGET_TRANSFORMATION) is False

    with pytest.raises(ValidationError):
        # Model is frozen
        caps.supports_inventory = False  # type: ignore[misc]


def test_registry_capability_queries() -> None:
    registry = FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )

    assert registry.has_capability("ember-classic", FrameworkCapability.INVENTORY) is True
    assert (
        registry.has_capability("ember-classic", FrameworkCapability.SOURCE_TRANSFORMATION) is True
    )
    assert (
        registry.has_capability("ember-classic", FrameworkCapability.TARGET_TRANSFORMATION) is False
    )

    assert (
        registry.has_capability("angularjs-directive", FrameworkCapability.SOURCE_TRANSFORMATION)
        is True
    )
    assert (
        registry.has_capability("angularjs-directive", FrameworkCapability.TARGET_TRANSFORMATION)
        is False
    )

    assert registry.has_capability("angular", FrameworkCapability.SOURCE_TRANSFORMATION) is False
    assert registry.has_capability("angular", FrameworkCapability.TARGET_TRANSFORMATION) is True

    # Unknown framework
    assert registry.has_capability("nonexistent", FrameworkCapability.INVENTORY) is False


def test_registry_negotiates_valid_migration_pairs() -> None:
    registry = FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )

    # Pair 1: Ember Classic -> Angular Standalone
    res_ember = registry.negotiate_pair("ember-classic", "angular")
    assert res_ember.supported is True
    assert res_ember.source_framework == "ember-classic"
    assert res_ember.target_framework == "angular"
    assert res_ember.validation_commands_available is True
    assert res_ember.reason is None

    # Pair 2: AngularJS Directive -> Angular Standalone
    res_ngjs = registry.negotiate_pair("angularjs-directive", "angular")
    assert res_ngjs.supported is True
    assert res_ngjs.source_framework == "angularjs-directive"
    assert res_ngjs.target_framework == "angular"
    assert res_ngjs.validation_commands_available is True
    assert res_ngjs.reason is None

    # List all supported pairs
    pairs = registry.get_supported_pairs()
    assert ("angularjs-directive", "angular") in pairs
    assert ("ember-classic", "angular") in pairs


def test_registry_rejects_incompatible_migration_pairs() -> None:
    registry = FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )

    # Angular cannot be a source transformation framework
    res1 = registry.negotiate_pair("angular", "ember-classic")
    assert res1.supported is False
    assert "does not support source transformation" in (res1.reason or "")

    # Unknown source framework
    res2 = registry.negotiate_pair("vue", "angular")
    assert res2.supported is False
    assert "is not registered" in (res2.reason or "")

    # Unknown target framework
    res3 = registry.negotiate_pair("ember-classic", "react")
    assert res3.supported is False
    assert "does not support migrating to target 'react'" in (res3.reason or "")


def test_transformation_service_negotiates_pair_from_repository(tmp_path: Path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    registry = FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )
    filesystem = SafeFilesystemInspector()

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        registry=registry,
        filesystem=filesystem,
    )

    extractor, renderer = service._resolve_pair(fixture_dir)
    assert extractor is not None
    assert renderer is not None
    bundles = extractor.discover_components(fixture_dir)
    assert len(bundles) == 1
    assert bundles[0].component_name == "UserBadge"


def test_transformation_service_resolve_pair_fails_on_unknown_repo(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty_repo"
    empty_dir.mkdir()
    (empty_dir / "random.txt").write_text("hello", encoding="utf-8")

    registry = FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )
    filesystem = SafeFilesystemInspector()

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        registry=registry,
        filesystem=filesystem,
    )

    with pytest.raises(ValueError, match="No recognizable framework detected"):
        service._resolve_pair(empty_dir)
