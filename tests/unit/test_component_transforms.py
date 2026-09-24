"""Unit tests for Ember Classic extraction and modern Angular Standalone rendering."""

from pathlib import Path

from migration_agent.adapters import (
    AngularStandaloneComponentRenderer,
    EmberClassicComponentExtractor,
)


def test_ember_classic_component_extractor_from_fixture() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini" / "app"
    js_file = fixture_dir / "components" / "user-card.js"
    hbs_file = fixture_dir / "templates" / "components" / "user-card.hbs"

    js_source = js_file.read_text(encoding="utf-8")
    hbs_source = hbs_file.read_text(encoding="utf-8")

    extractor = EmberClassicComponentExtractor()
    component = extractor.extract(
        component_source=js_source,
        template_source=hbs_source,
    )

    assert component.name == "UserCard"
    assert component.tag_name == "app-user-card"
    assert "name" in component.inputs
    assert "description" in component.inputs
    assert "isExpanded" in component.state_properties
    assert "toggleDetails" in component.methods


def test_angular_standalone_component_renderer() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini" / "app"
    js_file = fixture_dir / "components" / "user-card.js"
    hbs_file = fixture_dir / "templates" / "components" / "user-card.hbs"

    extractor = EmberClassicComponentExtractor()
    component = extractor.extract(
        component_source=js_file.read_text(encoding="utf-8"),
        template_source=hbs_file.read_text(encoding="utf-8"),
    )

    renderer = AngularStandaloneComponentRenderer()

    # 1. Component TypeScript
    ts_code = renderer.render_component_ts(component)
    assert "standalone: true" in ts_code
    assert "ChangeDetectionStrategy.OnPush" in ts_code
    assert "readonly name = input<string>('');" in ts_code
    assert "readonly description = input<string>('');" in ts_code
    assert "readonly isExpanded = signal<boolean>(false);" in ts_code
    assert "toggleDetails(): void" in ts_code
    assert "this.isExpanded.update" in ts_code

    # 2. Template HTML
    html_code = renderer.render_template_html(component)
    assert "@if (isExpanded())" in html_code
    assert "*ngIf" not in html_code  # Enforce modern control flow rule
    assert "p-3 shadow-sm" in html_code  # Enforce Bootstrap 5 utilities rule
    assert '(click)="toggleDetails()"' in html_code

    # 3. Spec TypeScript
    spec_code = renderer.render_spec_ts(component)
    assert "describe('UserCardComponent'" in spec_code
    assert "TestBed.configureTestingModule" in spec_code
    assert "component.toggleDetails();" in spec_code
    assert "expect(component.isExpanded()).toBeTrue();" in spec_code
