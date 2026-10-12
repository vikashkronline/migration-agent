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
    assert '<article class="user-card">' in html_code
    assert "<h2>{{ name() }}</h2>" in html_code
    assert '(click)="toggleDetails()"' in html_code

    # 3. Spec TypeScript
    spec_code = renderer.render_spec_ts(component)
    assert "describe('UserCardComponent'" in spec_code
    assert "TestBed.configureTestingModule" in spec_code
    assert "component.toggleDetails();" in spec_code
    assert "expect(component.isExpanded()).toBe(true);" in spec_code


def test_ember_classic_component_extractor_pod_layout(tmp_path: Path) -> None:
    feat_parent = "account-settings-parent"
    comp_dir = tmp_path / "app" / "features" / "components" / feat_parent / "delai-de-cloture"
    comp_dir.mkdir(parents=True)
    js_content = """
import Component from '@ember/component';
import { inject as service } from '@ember/service';

export default Component.extend({
  intl: service('intl'),
  wrfErrors: service('wrf-errors'),
  delaiMin: 5,
  isSubmitted: false,

  _initModel() {
    this.set('delaiMin', 10);
  },

  actions: {
    sauvegarder() {
      this.set('isSubmitted', true);
    }
  }
});
"""
    hbs_content = """
<div class="delai-container">
  <span>{{@title}}</span>
  <button {{action 'sauvegarder'}}>Valider</button>
</div>
"""
    (comp_dir / "component.js").write_text(js_content, encoding="utf-8")
    (comp_dir / "template.hbs").write_text(hbs_content, encoding="utf-8")

    extractor = EmberClassicComponentExtractor()
    bundles = extractor.discover_components(tmp_path)

    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.component_name == "DelaiDeCloture"
    expected_js = f"app/features/components/{feat_parent}/delai-de-cloture/component.js"
    expected_hbs = f"app/features/components/{feat_parent}/delai-de-cloture/template.hbs"
    assert expected_js in bundle.source_files
    assert expected_hbs in bundle.source_files

    component = extractor.extract(
        bundle.component_source,
        bundle.template_source,
        component_name=bundle.component_name,
    )
    assert component.name == "DelaiDeCloture"
    assert component.tag_name == "app-delai-de-cloture"
    assert "title" in component.inputs
    assert "delaiMin" in component.state_properties
    assert "isSubmitted" in component.state_properties
    assert "sauvegarder" in component.methods
    assert "_initModel" in component.methods
    assert "IntlService" in component.injected_services
    assert "WrfErrorsService" in component.injected_services
