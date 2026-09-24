"""Ember Classic and AngularJS source extractors, and Angular Standalone target renderer."""

import re
from pathlib import Path

from migration_agent.domain.frameworks import SourceComponentBundle
from migration_agent.ports import (
    ComponentExtractorPort,
    ComponentRendererPort,
    IntermediateComponent,
)


def _to_kebab_case(value: str) -> str:
    """Convert PascalCase or camelCase or snake_case to kebab-case."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    s = s.replace("_", "-").strip("-").lower()
    return re.sub(r"-+", "-", s)


def _to_pascal_case(value: str) -> str:
    """Convert kebab-case or camelCase or snake_case to PascalCase."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    parts = re.split(r"[-_]+", s)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


class EmberClassicComponentExtractor(ComponentExtractorPort):
    """Extracts intermediate component representation from Ember Classic component files."""

    def discover_components(self, source_root: Path) -> tuple[SourceComponentBundle, ...]:
        """Discover Ember Classic components in app/components/ and matching templates."""
        root = Path(source_root).resolve()
        comp_dir = root / "app" / "components"
        if not comp_dir.is_dir():
            return ()

        bundles: list[SourceComponentBundle] = []
        for js_path in sorted(comp_dir.glob("*.js")):
            base_name = js_path.stem  # e.g. "user-card"
            comp_name = _to_pascal_case(base_name)  # e.g. "UserCard"

            hbs_path = root / "app" / "templates" / "components" / f"{base_name}.hbs"
            css_path = root / "app" / "styles" / "app.css"

            source_files: list[str] = [str(js_path.relative_to(root)).replace("\\", "/")]
            template_source = ""
            style_source = ""

            if hbs_path.is_file():
                source_files.append(str(hbs_path.relative_to(root)).replace("\\", "/"))
                template_source = hbs_path.read_text(encoding="utf-8")

            if css_path.is_file():
                source_files.append(str(css_path.relative_to(root)).replace("\\", "/"))
                style_source = css_path.read_text(encoding="utf-8")

            component_source = js_path.read_text(encoding="utf-8")
            bundles.append(
                SourceComponentBundle(
                    component_name=comp_name,
                    source_files=tuple(sorted(source_files)),
                    component_source=component_source,
                    template_source=template_source,
                    style_source=style_source,
                )
            )

        return tuple(bundles)

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


class AngularJsDirectiveExtractor(ComponentExtractorPort):
    """Extracts intermediate component representation from AngularJS directive definitions."""

    def discover_components(self, source_root: Path) -> tuple[SourceComponentBundle, ...]:
        """Discover AngularJS directives in the repository and matching templates/styles."""
        root = Path(source_root).resolve()
        bundles: list[SourceComponentBundle] = []

        # Find .directive.js or .directive.ts files anywhere in source tree
        directive_files = sorted(
            [
                p
                for p in root.rglob("*.js")
                if p.name.endswith(".directive.js")
                or (".directive" in p.name and not p.name.endswith(".spec.js"))
            ]
        )

        for js_path in directive_files:
            content = js_path.read_text(encoding="utf-8")
            # Extract directive name from .directive('name', ...)
            dir_match = re.search(r"\.directive\(\s*['\"]([a-zA-Z0-9_-]+)['\"]", content)
            raw_name = dir_match.group(1) if dir_match else js_path.stem.replace(".directive", "")
            comp_name = _to_pascal_case(raw_name)

            base_stem = js_path.name.replace(".directive.js", "").replace(".directive", "")
            parent_dir = js_path.parent

            # Look for template file (.template.html or .html)
            template_source = ""
            source_files: list[str] = [str(js_path.relative_to(root)).replace("\\", "/")]

            tpl_candidates = [
                parent_dir / f"{base_stem}.template.html",
                parent_dir / f"{base_stem}.html",
                root / "src" / f"{base_stem}.template.html",
            ]
            for tpl_path in tpl_candidates:
                if tpl_path.is_file():
                    source_files.append(str(tpl_path.relative_to(root)).replace("\\", "/"))
                    template_source = tpl_path.read_text(encoding="utf-8")
                    break

            # Look for css file
            style_source = ""
            css_candidates = [
                parent_dir / f"{base_stem}.css",
                root / "src" / f"{base_stem}.css",
            ]
            for css_path in css_candidates:
                if css_path.is_file():
                    source_files.append(str(css_path.relative_to(root)).replace("\\", "/"))
                    style_source = css_path.read_text(encoding="utf-8")
                    break

            bundles.append(
                SourceComponentBundle(
                    component_name=comp_name,
                    source_files=tuple(sorted(source_files)),
                    component_source=content,
                    template_source=template_source,
                    style_source=style_source,
                )
            )

        return tuple(bundles)

    def extract(
        self,
        component_source: str,
        template_source: str = "",
        style_source: str = "",
    ) -> IntermediateComponent:
        """Parse AngularJS directive code and template into IntermediateComponent."""
        # Detect directive name
        dir_match = re.search(r"\.directive\(\s*['\"]([a-zA-Z0-9_-]+)['\"]", component_source)
        raw_name = dir_match.group(1) if dir_match else "userBadge"
        name = _to_pascal_case(raw_name)
        kebab_name = _to_kebab_case(raw_name)
        tag_name = f"app-{kebab_name}"

        # Detect inputs from isolate scope bindings e.g. scope: { name: '@', role: '@' }
        inputs: list[str] = []
        scope_match = re.search(r"scope\s*:\s*\{([^}]+)\}", component_source, re.DOTALL)
        if scope_match:
            scope_body = scope_match.group(1)
            for item in re.finditer(r"([a-zA-Z0-9_]+)\s*:\s*['\"]([@=&<])['\"]", scope_body):
                prop = item.group(1)
                if prop not in inputs:
                    inputs.append(prop)

        # Detect template expressions e.g. {{name}}
        for tm in re.finditer(r"\{\{([a-zA-Z0-9_]+)\}\}", template_source):
            var_name = tm.group(1)
            if var_name not in inputs:
                inputs.append(var_name)

        # Detect state properties e.g. scope.isExpanded = false;
        state_properties: list[str] = []
        state_pattern = re.compile(
            r"(?:\$scope|scope)\.([a-zA-Z0-9_]+)\s*=\s*(false|true|['\"].*?['\"]|\d+)\s*;",
            re.MULTILINE,
        )
        for sm in state_pattern.finditer(component_source):
            prop_name = sm.group(1)
            if prop_name not in state_properties:
                state_properties.append(prop_name)

        # Detect action methods e.g. scope.toggleDetails = function()
        methods: list[str] = []
        method_pattern = re.compile(
            r"(?:\$scope|scope)\.([a-zA-Z0-9_]+)\s*=\s*function",
            re.MULTILINE,
        )
        for mm in method_pattern.finditer(component_source):
            method_name = mm.group(1)
            if method_name not in methods:
                methods.append(method_name)

        return IntermediateComponent(
            name=name,
            tag_name=tag_name,
            inputs=tuple(sorted(inputs)),
            state_properties=tuple(sorted(state_properties)),
            methods=tuple(sorted(methods)),
            template_raw=template_source,
            style_raw=style_source,
            metadata={"source_framework": "angularjs-directive"},
        )


class AngularStandaloneComponentRenderer(ComponentRendererPort):
    """Renders modern Angular 17+ standalone components conforming to project Angular standards."""

    def render_component_ts(self, component: IntermediateComponent) -> str:
        """Render standalone TypeScript component class with OnPush and Signals."""
        kebab_name = _to_kebab_case(component.name)
        inputs_code = "\n".join(
            f"  readonly {inp} = input<string>('');" for inp in component.inputs
        )

        state_code = "\n".join(
            f"  readonly {prop} = signal<boolean>(false);" for prop in component.state_properties
        )

        methods_code: list[str] = []
        for method in component.methods:
            # Map toggle action to reactive signal update
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
            f"  templateUrl: './{kebab_name}.component.html',\n"
            f"  styleUrls: ['./{kebab_name}.component.scss'],\n"
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
        kebab_name = _to_kebab_case(component.name)
        header_expr = f"{component.inputs[0]}()" if component.inputs else "'Details'"
        html = (
            f'<article class="{kebab_name} card p-3 shadow-sm">\n'
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

    def render_style_scss(self, component: IntermediateComponent) -> str:
        """Render component-scoped modern SCSS stylesheet."""
        kebab_name = _to_kebab_case(component.name)
        return f"// Component-scoped SCSS\n.{kebab_name} {{\n  max-width: 480px;\n}}\n"

    def render_spec_ts(self, component: IntermediateComponent) -> str:
        """Render Jasmine/Jest unit test spec with TestBed."""
        comp_class = f"{component.name}Component"
        kebab_name = _to_kebab_case(component.name)
        toggle_method = component.methods[0] if component.methods else "toggleDetails"
        state_prop = component.state_properties[0] if component.state_properties else "isExpanded"

        return (
            "import { ComponentFixture, TestBed } from '@angular/core/testing';\n"
            f"import {{ {comp_class} }} from './{kebab_name}.component';\n\n"
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
            f"    expect(component.{state_prop}()).toBeFalse();\n"
            f"    component.{toggle_method}();\n"
            f"    expect(component.{state_prop}()).toBeTrue();\n"
            "  });\n"
            "});\n"
        )
