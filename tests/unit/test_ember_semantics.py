"""Preservation and explicit unsupported-source diagnostics, not scaffold snapshots."""

import pytest

from migration_agent.adapters.transforms import (
    AngularStandaloneComponentRenderer,
    EmberClassicComponentExtractor,
)


def test_preserves_initial_values_actual_action_target_markup_and_styles():
    source = """import Component from '@ember/component';
export default Component.extend({ amount: 5, open: true,
 actions: { flip() { this.toggleProperty('open'); }, reset() { this.set('amount', 0); } }
});"""
    template = (
        '<section class="original"><h2>{{@title}}</h2>{{#if this.open}}'
        "<p>{{this.amount}}</p>{{else}}Closed{{/if}}"
        '<button {{action "flip"}}>Expand</button></section>'
    )
    component = EmberClassicComponentExtractor().extract(
        source, template, ".original { width: 70%; }"
    )
    renderer = AngularStandaloneComponentRenderer()
    typescript = renderer.render_component_ts(component)
    assert "amount = signal<number>(5)" in typescript
    assert "open = signal<boolean>(true)" in typescript
    assert "this.open.update((current) => !current)" in typescript
    assert "this.amount.set(0)" in typescript
    assert "Handled by component logic" not in typescript
    html = renderer.render_template_html(component)
    assert '<section class="original">' in html and "{{ amount() }}" in html
    assert "} @else {" in html and '(click)="flip()"' in html
    assert renderer.render_style_scss(component) == ".original { width: 70%; }"
    spec = renderer.render_spec_ts(component)
    assert "component.open()).toBe(true)" in spec and "component.open()).toBe(false)" in spec


@pytest.mark.parametrize(
    "member",
    [
        'value: computed("other", function() { return 1; })',
        "init() { this._super(...arguments); }",
        'save() { return fetch("/api/items"); }',
        'save(value) { this.set("amount", value); }',
        'classNames: ["custom-host"]',
    ],
)
def test_unknown_javascript_fails_instead_of_empty_methods(member):
    with pytest.raises(ValueError, match="EMBER_CONSTRUCT_UNSUPPORTED"):
        EmberClassicComponentExtractor().extract(
            "import Component from '@ember/component'; export default Component.extend({ "
            + member
            + " });"
        )


@pytest.mark.parametrize(
    "template",
    [
        "{{format-date this.value}}",
        "{{{this.value}}}",
        "{{#each @items as |item|}}{{item.name}}{{/each}}",
        "{{unknown}}",
        "{{#if @name}}unfinished",
    ],
)
def test_unknown_template_fails_instead_of_a_details_card(template):
    component = EmberClassicComponentExtractor().extract(
        "import Component from '@ember/component'; export default Component.extend({});", template
    )
    with pytest.raises(ValueError, match="EMBER_CONSTRUCT_UNSUPPORTED"):
        AngularStandaloneComponentRenderer().render_template_html(component)
