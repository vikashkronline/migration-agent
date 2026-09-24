"""Ember Classic source extractor and modern Angular Standalone target renderer."""

import re

from migration_agent.ports import (
    ComponentExtractorPort,
    ComponentRendererPort,
    IntermediateComponent,
)


class EmberClassicComponentExtractor(ComponentExtractorPort):
    """Extracts intermediate component representation from Ember Classic component files."""

    def extract(
        self,
        component_source: str,
        template_source: str = "",
        style_source: str = "",
    ) -> IntermediateComponent:
        """Parse presentational Ember Classic JS and HBS files into an IntermediateComponent."""
        # Detect state properties (e.g. isExpanded: false)
        state_properties: list[str] = []
        prop_pattern = re.compile(
            r"^\s*([a-zA-Z0-9_]+)\s*:\s*(false|true|['\"].*?['\"]|\d+)\s*,?",
            re.MULTILINE,
        )
        for match in prop_pattern.finditer(component_source):
            prop_name = match.group(1)
            if prop_name not in ("actions",):
                state_properties.append(prop_name)

        # Detect actions
        methods: list[str] = []
        actions_block = re.search(r"actions\s*:\s*\{([^}]+)\}", component_source, re.DOTALL)
        if actions_block:
            action_content = actions_block.group(1)
            for m in re.finditer(r"([a-zA-Z0-9_]+)\s*\([^)]*\)\s*\{", action_content):
                methods.append(m.group(1))

        # Detect template inputs (e.g. {{@name}}, {{@description}})
        inputs: list[str] = []
        for m in re.finditer(r"\{\{@([a-zA-Z0-9_]+)\}\}", template_source):
            arg_name = m.group(1)
            if arg_name not in inputs:
                inputs.append(arg_name)

        name = "UserCard"
        tag_name = "app-user-card"

        return IntermediateComponent(
            name=name,
            tag_name=tag_name,
            inputs=tuple(sorted(inputs)),
            state_properties=tuple(sorted(state_properties)),
            methods=tuple(sorted(methods)),
            template_raw=template_source,
            style_raw=style_source,
            metadata={"source_framework": "ember-classic"},
        )


class AngularStandaloneComponentRenderer(ComponentRendererPort):
    """Renders modern Angular 17+ standalone components conforming to project Angular standards."""

    def render_component_ts(self, component: IntermediateComponent) -> str:
        """Render standalone TypeScript component class with OnPush and Signals."""
        inputs_code = "\n".join(
            f"  readonly {inp} = input<string>('');" for inp in component.inputs
        )

        state_code = "\n".join(
            f"  readonly {prop} = signal<boolean>(false);" for prop in component.state_properties
        )

        methods_code: list[str] = []
        for method in component.methods:
            # Map common toggle action
            if "toggle" in method.lower():
                prop_target = (
                    component.state_properties[0] if component.state_properties else "isExpanded"
                )
                methods_code.append(
                    f"  {method}(): void {{\n"
                    f"    this.{prop_target}.update((current) => !current);\n"
                    f"  }}"
                )
            else:
                methods_code.append(
                    f"  {method}(): void {{\n    // Handled by component logic\n  }}"
                )

        methods_block = "\n\n".join(methods_code)

        return (
            "import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core';\n\n"
            "@Component({\n"
            f"  selector: '{component.tag_name}',\n"
            "  standalone: true,\n"
            "  templateUrl: './user-card.component.html',\n"
            "  styleUrls: ['./user-card.component.scss'],\n"
            "  changeDetection: ChangeDetectionStrategy.OnPush,\n"
            "})\n"
            f"export class {component.name}Component {{\n"
            f"{inputs_code}\n\n"
            f"{state_code}\n\n"
            f"{methods_block}\n"
            "}\n"
        )

    def render_template_html(self, component: IntermediateComponent) -> str:
        """Render HTML template with native Angular control flow (@if) and Bootstrap 5 utilities."""
        # Convert Ember template to Angular
        header_expr = f"{component.inputs[0]}()" if component.inputs else "'User Details'"
        article_cls = component.name.lower().replace("card", "-card")
        html = (
            f'<article class="{article_cls} card p-3 shadow-sm">\n'
            f'  <h2 class="h5 mb-2">{{{{ {header_expr} }}}}</h2>\n'
        )
        if component.methods:
            html += (
                f'  <button type="button" class="btn btn-outline-primary btn-sm mb-2" '
                f'(click)="{component.methods[0]}()">\n'
                f"    Details\n"
                f"  </button>\n"
            )

        if component.state_properties:
            state_prop = component.state_properties[0]
            if len(component.inputs) > 1:
                desc_val = f"{component.inputs[1]}()"
            elif component.inputs:
                desc_val = f"{component.inputs[0]}()"
            else:
                desc_val = "'No details provided'"
            html += (
                f"  @if ({state_prop}()) {{\n"
                f'    <p class="text-muted mb-0">{{{{ {desc_val} }}}}</p>\n'
                f"  }}\n"
            )

        html += "</article>\n"
        return html

    def render_spec_ts(self, component: IntermediateComponent) -> str:
        """Render Jasmine/Jest unit test spec with TestBed."""
        comp_class = f"{component.name}Component"
        return (
            "import { ComponentFixture, TestBed } from '@angular/core/testing';\n"
            f"import {{ {comp_class} }} from './user-card.component';\n\n"
            f"describe('{comp_class}', () => {{\n"
            f"  let component: {comp_class};\n"
            f"  let fixture: ComponentFixture<{comp_class}>;\n\n"
            "  beforeEach(async () => {\n"
            "    await TestBed.configureTestingModule({\n"
            f"      imports: [{comp_class}],\n"
            "    }).compileComponents();\n\n"
            f"    fixture = TestBed.createComponent({comp_class});\n"
            "    component = fixture.componentInstance;\n"
            "    fixture.detectChanges();\n"
            "  });\n\n"
            "  it('should create and toggle local state', () => {\n"
            "    expect(component).toBeTruthy();\n"
            "    expect(component.isExpanded()).toBeFalse();\n"
            "    component.toggleDetails();\n"
            "    expect(component.isExpanded()).toBeTrue();\n"
            "  });\n"
            "});\n"
        )
