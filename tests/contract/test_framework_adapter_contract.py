"""Reusable contract tests verified against all framework adapters."""

from pathlib import Path

import pytest

from migration_agent.adapters import (
    AngularAdapter,
    AngularJsDirectiveAdapter,
    EmberClassicAdapter,
    SafeFilesystemInspector,
)
from migration_agent.domain import (
    ExclusionSummary,
    FrameworkCapabilities,
    FrameworkCapability,
    RepositoryDescriptor,
    RepositorySnapshot,
    ValidationCommand,
    ValidationProfile,
)
from migration_agent.ports import (
    ComponentExtractorPort,
    ComponentRendererPort,
    FrameworkAdapter,
    InspectionPolicy,
    IntermediateComponent,
)

ALL_ADAPTERS: list[FrameworkAdapter] = [
    EmberClassicAdapter(),
    AngularJsDirectiveAdapter(),
    AngularAdapter(),
]


@pytest.mark.parametrize("adapter", ALL_ADAPTERS, ids=lambda a: a.framework_id)
def test_adapter_framework_id_contract(adapter: FrameworkAdapter) -> None:
    """Every adapter must declare a non-empty, kebab-case framework identifier."""
    assert isinstance(adapter.framework_id, str)
    assert len(adapter.framework_id) > 0
    assert adapter.framework_id == adapter.framework_id.lower()
    assert "_" not in adapter.framework_id


@pytest.mark.parametrize("adapter", ALL_ADAPTERS, ids=lambda a: a.framework_id)
def test_adapter_capabilities_contract(adapter: FrameworkAdapter) -> None:
    """Every adapter must declare immutable typed FrameworkCapabilities."""
    caps = adapter.capabilities
    assert isinstance(caps, FrameworkCapabilities)
    assert caps.has_capability(FrameworkCapability.INVENTORY) is True

    # Check consistency of validation profiles
    if caps.supports_validation:
        assert len(caps.supported_validation_profiles) > 0
    else:
        assert len(caps.supported_validation_profiles) == 0


@pytest.mark.parametrize("adapter", ALL_ADAPTERS, ids=lambda a: a.framework_id)
def test_adapter_detect_empty_repository(adapter: FrameworkAdapter) -> None:
    """Adapters must return None when inspecting a completely empty repository."""
    empty_snapshot = RepositorySnapshot(
        repository=RepositoryDescriptor(root="/empty", name="empty"),
        files=(),
        exclusions=ExclusionSummary(),
    )
    assert adapter.detect(empty_snapshot) is None


@pytest.mark.parametrize("adapter", ALL_ADAPTERS, ids=lambda a: a.framework_id)
def test_adapter_validation_commands_contract(adapter: FrameworkAdapter) -> None:
    """Adapters must return commands matching declared supported profiles and () for others."""
    caps = adapter.capabilities
    for profile in ValidationProfile:
        cmds = adapter.get_validation_commands(profile)
        if profile in caps.supported_validation_profiles:
            assert len(cmds) > 0
            assert all(isinstance(c, ValidationCommand) for c in cmds)
            assert all(c.profile == profile for c in cmds)
        else:
            assert cmds == ()


@pytest.mark.parametrize("adapter", ALL_ADAPTERS, ids=lambda a: a.framework_id)
def test_adapter_source_transformation_contract(adapter: FrameworkAdapter) -> None:
    """Source transformation adapters must provide an extractor producing IntermediateComponents."""
    caps = adapter.capabilities
    extractor = adapter.get_extractor()

    if caps.supports_source_transformation:
        assert extractor is not None
        assert isinstance(extractor, ComponentExtractorPort)

        # Extraction smoke check with basic inputs
        comp = extractor.extract(
            component_source="/* dummy */",
            template_source="<p>Test</p>",
            style_source="",
        )
        assert isinstance(comp, IntermediateComponent)
        assert len(comp.name) > 0
        assert len(comp.tag_name) > 0
    else:
        assert extractor is None


@pytest.mark.parametrize("adapter", ALL_ADAPTERS, ids=lambda a: a.framework_id)
def test_adapter_target_transformation_contract(adapter: FrameworkAdapter) -> None:
    """Target transformation adapters must provide a renderer meeting Angular standards."""
    caps = adapter.capabilities
    renderer = adapter.get_renderer()

    if caps.supports_target_transformation:
        assert renderer is not None
        assert isinstance(renderer, ComponentRendererPort)

        sample = IntermediateComponent(
            name="ContractCard",
            tag_name="app-contract-card",
            inputs=("title",),
            state_properties=("isActive",),
            methods=("toggleActive",),
            template_raw="<p>{{title}}</p>",
            style_raw="",
        )

        ts = renderer.render_component_ts(sample)
        assert "standalone: true" in ts
        assert "ChangeDetectionStrategy.OnPush" in ts
        assert "signal<boolean>" in ts
        assert "ContractCardComponent" in ts

        html = renderer.render_template_html(sample)
        assert "@if" in html
        assert "*ngIf" not in html
        assert "p-3 shadow-sm" in html

        scss = renderer.render_style_scss(sample)
        assert ".contract-card" in scss

        spec = renderer.render_spec_ts(sample)
        assert "TestBed" in spec
        assert "ContractCardComponent" in spec
    else:
        assert renderer is None


def test_fixture_detection_ember_classic() -> None:
    """EmberClassicAdapter must detect the ember-classic-mini fixture with high confidence."""
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    snapshot = SafeFilesystemInspector().inspect(fixture_dir, InspectionPolicy())
    fp = EmberClassicAdapter().detect(snapshot)
    assert fp is not None
    assert fp.framework_id == "ember-classic"
    assert fp.confidence >= 0.8
    assert len(fp.evidence) >= 2


def test_fixture_detection_angularjs_directive() -> None:
    """AngularJsDirectiveAdapter detects angularjs-directive-mini with high confidence."""
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    snapshot = SafeFilesystemInspector().inspect(fixture_dir, InspectionPolicy())
    fp = AngularJsDirectiveAdapter().detect(snapshot)
    assert fp is not None
    assert fp.framework_id == "angularjs-directive"
    assert fp.confidence >= 0.8
    assert len(fp.evidence) >= 2
    assert any(e.kind == "manifest_dependency" for e in fp.evidence)
    assert any(e.kind == "directive_declaration" for e in fp.evidence)
