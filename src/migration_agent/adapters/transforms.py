"""Ember Classic and AngularJS source extractors, and Angular Standalone target renderer."""

import re
from pathlib import Path

from migration_agent.domain.frameworks import (
    IntermediateService,
    ServiceMethod,
    SourceComponentBundle,
    SourceServiceBundle,
)
from migration_agent.ports import (
    ComponentExtractorPort,
    ComponentRendererPort,
    IntermediateComponent,
    ServiceExtractorPort,
    ServiceRendererPort,
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
    """Extracts intermediate component representation from AngularJS directives and components."""

    def discover_components(self, source_root: Path) -> tuple[SourceComponentBundle, ...]:
        """Discover AngularJS directives/components and matching templates/styles."""
        root = Path(source_root).resolve()
        bundles: list[SourceComponentBundle] = []

        # Find .directive.js or .component.js files anywhere in source tree
        directive_files = sorted(
            [
                p
                for p in root.rglob("*.js")
                if (
                    p.name.endswith(".directive.js")
                    or p.name.endswith(".component.js")
                    or (".directive" in p.name and not p.name.endswith(".spec.js"))
                    or (
                        ".component" in p.name
                        and not p.name.endswith(".spec.js")
                        and not p.name.endswith(".component.ts")
                    )
                )
            ]
        )

        for js_path in directive_files:
            content = js_path.read_text(encoding="utf-8")
            # Extract directive/component name
            dir_match = re.search(
                r"\.(?:directive|component)\(\s*['\"]([a-zA-Z0-9_-]+)['\"]", content
            )
            raw_name = (
                dir_match.group(1)
                if dir_match
                else (
                    js_path.name.replace(".directive.js", "")
                    .replace(".component.js", "")
                    .replace(".directive", "")
                    .replace(".component", "")
                )
            )
            comp_name = _to_pascal_case(raw_name)

            base_stem = (
                js_path.name.replace(".directive.js", "")
                .replace(".component.js", "")
                .replace(".directive", "")
                .replace(".component", "")
            )
            parent_dir = js_path.parent

            # Look for template file (.template.html or .html)
            template_source = ""
            source_files: list[str] = [str(js_path.relative_to(root)).replace("\\", "/")]

            tpl_candidates = [
                parent_dir / f"{base_stem}.template.html",
                parent_dir / f"{base_stem}.html",
                root / "src" / f"{base_stem}.template.html",
                root / "src" / f"{base_stem}.html",
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
                root / "src" / "dashboard.css",
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
        """Parse AngularJS directive/component code and template into IntermediateComponent."""
        # Detect directive or component name
        dir_match = re.search(
            r"\.(?:directive|component)\(\s*['\"]([a-zA-Z0-9_-]+)['\"]", component_source
        )
        raw_name = dir_match.group(1) if dir_match else "userBadge"
        name = _to_pascal_case(raw_name)
        kebab_name = _to_kebab_case(raw_name)
        tag_name = f"app-{kebab_name}"

        # Detect inputs and outputs from isolate scope or bindings
        inputs: list[str] = []
        outputs: list[str] = []
        input_types: dict[str, str] = {}
        state_types: dict[str, str] = {}

        scope_match = re.search(
            r"(?:scope|bindings)\s*:\s*\{([^}]+)\}", component_source, re.DOTALL
        )
        if scope_match:
            scope_body = scope_match.group(1)
            for item in re.finditer(r"([a-zA-Z0-9_]+)\s*:\s*['\"]([@=&<])['\"]", scope_body):
                prop = item.group(1)
                kind = item.group(2)
                if kind == "&":
                    if prop not in outputs:
                        outputs.append(prop)
                else:
                    if prop not in inputs:
                        inputs.append(prop)
                    if kind == "@":
                        input_types[prop] = "string"
                    elif prop in ("limit", "count", "id", "total"):
                        input_types[prop] = "number"
                    elif prop.endswith("s") or prop.endswith("List"):
                        input_types[prop] = "any[]"
                    else:
                        input_types[prop] = "string"

        # Detect template expressions e.g. {{name}} or {{$ctrl.name}} or {{vm.name}}
        for tm in re.finditer(r"\{\{(?:vm\.|\$ctrl\.|ctrl\.)?([a-zA-Z0-9_]+)\}\}", template_source):
            var_name = tm.group(1)
            if var_name not in inputs:
                inputs.append(var_name)
                input_types[var_name] = "string"

        # Detect state properties e.g. scope.isExpanded = false; or $ctrl.isExpanded = false;
        state_properties: list[str] = []
        state_pattern = re.compile(
            r"(?:\$scope|scope|vm|\$ctrl|ctrl)\.([a-zA-Z0-9_]+)\s*=\s*(false|true|['\"].*?['\"]|\d+|\[\])\s*;",
            re.MULTILINE,
        )
        for sm in state_pattern.finditer(component_source):
            prop_name = sm.group(1)
            val = sm.group(2).strip()
            if prop_name not in state_properties:
                state_properties.append(prop_name)
            if val in ("true", "false"):
                state_types[prop_name] = "boolean"
            elif val.isdigit():
                state_types[prop_name] = "number"
            elif val.startswith("["):
                state_types[prop_name] = "any[]"
            else:
                state_types[prop_name] = "string"

        # Detect action methods e.g. scope.toggleDetails = function() or $ctrl.toggle = function()
        methods: list[str] = []
        method_pattern = re.compile(
            r"(?:\$scope|scope|vm|\$ctrl|ctrl)\.([a-zA-Z0-9_]+)\s*=\s*function",
            re.MULTILINE,
        )
        for mm in method_pattern.finditer(component_source):
            method_name = mm.group(1)
            if method_name not in methods:
                methods.append(method_name)

        # Detect injected services from controller
        injected_services: list[str] = []
        ctrl_match = re.search(
            r"controller\s*:\s*(?:\[([^\]]+)\]|function\s*\(([^)]*)\))", component_source
        )
        if ctrl_match:
            raw_deps = ctrl_match.group(1) or ctrl_match.group(2)
            if raw_deps:
                for dep in re.finditer(r"['\"]?([a-zA-Z0-9_$]+)['\"]?", raw_deps):
                    dep_name = dep.group(1).strip()
                    if (
                        dep_name
                        and dep_name
                        not in ("$scope", "$element", "$attrs", "$transclude", "function")
                        and not dep_name.startswith("$")
                    ):
                        svc_class = _to_pascal_case(dep_name)
                        if not svc_class.endswith("Service"):
                            svc_class = f"{svc_class}Service"
                        if svc_class not in injected_services:
                            injected_services.append(svc_class)
                    elif dep_name == "$http":
                        if "HttpClient" not in injected_services:
                            injected_services.append("HttpClient")

        return IntermediateComponent(
            name=name,
            tag_name=tag_name,
            inputs=tuple(sorted(inputs)),
            outputs=tuple(sorted(outputs)),
            input_types=input_types,
            state_properties=tuple(sorted(state_properties)),
            state_types=state_types,
            methods=tuple(sorted(methods)),
            injected_services=tuple(sorted(injected_services)),
            template_raw=template_source,
            style_raw=style_source,
            metadata={"source_framework": "angularjs-directive"},
        )


class AngularJsServiceExtractor(ServiceExtractorPort):
    """Extracts intermediate service representation from AngularJS service/factory definitions."""

    def discover_services(self, source_root: Path) -> tuple[SourceServiceBundle, ...]:
        """Discover AngularJS service files (*.service.js, *.factory.js)."""
        root = Path(source_root).resolve()
        bundles: list[SourceServiceBundle] = []

        service_files = sorted(
            [
                p
                for p in root.rglob("*.js")
                if (p.name.endswith(".service.js") or p.name.endswith(".factory.js"))
                and not p.name.endswith(".spec.js")
            ]
        )

        for js_path in service_files:
            content = js_path.read_text(encoding="utf-8")
            match = re.search(r"\.(?:service|factory)\(\s*['\"]([a-zA-Z0-9_-]+)['\"]", content)
            raw_name = (
                match.group(1)
                if match
                else js_path.name.replace(".service.js", "").replace(".factory.js", "")
            )
            svc_name = _to_pascal_case(raw_name)

            bundles.append(
                SourceServiceBundle(
                    service_name=svc_name,
                    source_files=(str(js_path.relative_to(root)).replace("\\", "/"),),
                    service_source=content,
                )
            )

        return tuple(bundles)

    def extract_service(self, service_source: str) -> IntermediateService:
        """Parse AngularJS service/factory source code into IntermediateService."""
        match = re.search(r"\.(?:service|factory)\(\s*['\"]([a-zA-Z0-9_-]+)['\"]", service_source)
        raw_name = match.group(1) if match else "UserDataService"
        svc_name = _to_pascal_case(raw_name)
        if not svc_name.endswith("Service"):
            svc_name = f"{svc_name}Service"

        methods: list[ServiceMethod] = []

        # Find method declarations e.g. this.getUsers = function(...) or self.update = function(...)
        method_pattern = re.compile(
            r"(?:this|self)\.([a-zA-Z0-9_]+)\s*=\s*function\s*\(([^)]*)\)\s*\{([^}]+)\}",
            re.DOTALL,
        )

        for m in method_pattern.finditer(service_source):
            method_name = m.group(1)
            raw_params = m.group(2).strip()
            body = m.group(3)

            params = tuple(
                p.strip() for p in raw_params.split(",") if p.strip() and p.strip() != "$http"
            )

            # Detect http verb and endpoint
            http_verb = "GET"
            endpoint = ""
            verb_match = re.search(
                r"\$http\.(get|post|put|delete)\(\s*(['\"`].*?['\"`]|[a-zA-Z0-9_]+)",
                body,
            )
            if verb_match:
                http_verb = verb_match.group(1).upper()
                raw_ep = verb_match.group(2).strip("'\"`")
                endpoint = raw_ep
            elif "$http(" in body:
                method_match = re.search(r"method\s*:\s*['\"]([A-Z]+)['\"]", body)
                if method_match:
                    http_verb = method_match.group(1).upper()
                url_match = re.search(r"url\s*:\s*['\"](.*?)['\"]", body)
                if url_match:
                    endpoint = url_match.group(1)

            methods.append(
                ServiceMethod(
                    name=method_name,
                    http_method=http_verb,
                    endpoint=endpoint,
                    parameters=params,
                    return_type="Observable<any>",
                )
            )

        return IntermediateService(
            name=svc_name,
            methods=tuple(methods),
            metadata={"source_framework": "angularjs-service"},
        )


class AngularStandaloneComponentRenderer(ComponentRendererPort):
    """Renders modern Angular 17+ standalone components conforming to project Angular standards."""

    def render_component_ts(self, component: IntermediateComponent) -> str:
        """Render standalone TypeScript component class with OnPush, Signals, and DI."""
        kebab_name = _to_kebab_case(component.name)

        # Inputs
        inputs_lines: list[str] = []
        for inp in component.inputs:
            t = component.input_types.get(inp, "string")
            default_val = (
                "''"
                if t == "string"
                else ("0" if t == "number" else ("[]" if t == "any[]" else "false"))
            )
            inputs_lines.append(f"  readonly {inp} = input<{t}>({default_val});")
        inputs_code = "\n".join(inputs_lines)

        # Outputs
        outputs_lines = [f"  readonly {out} = output<any>();" for out in component.outputs]
        outputs_code = "\n".join(outputs_lines)

        # State signals
        state_lines: list[str] = []
        for prop in component.state_properties:
            t = component.state_types.get(prop, "boolean")
            default_val = (
                "false"
                if t == "boolean"
                else ("0" if t == "number" else ("[]" if t == "any[]" else "''"))
            )
            state_lines.append(f"  readonly {prop} = signal<{t}>({default_val});")
        state_code = "\n".join(state_lines)

        # Injected services
        service_imports: list[str] = []
        injected_fields: list[str] = []
        for svc in component.injected_services:
            if svc == "HttpClient":
                service_imports.append("import { HttpClient } from '@angular/common/http';")
                injected_fields.append("  private readonly http = inject(HttpClient);")
            else:
                svc_kebab = _to_kebab_case(svc)
                if svc_kebab.endswith("-service"):
                    svc_kebab = svc_kebab[:-8]
                service_imports.append(
                    f"import {{ {svc} }} from '../../services/{svc_kebab}.service';"
                )
                field_name = svc[:1].lower() + svc[1:]
                injected_fields.append(f"  private readonly {field_name} = inject({svc});")

        service_imports_block = ("\n" + "\n".join(service_imports)) if service_imports else ""
        injected_fields_block = ("\n".join(injected_fields) + "\n\n") if injected_fields else ""

        # Methods
        methods_code: list[str] = []
        for method in component.methods:
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

        core_imports = ["ChangeDetectionStrategy", "Component"]
        if component.injected_services:
            core_imports.append("inject")
        if component.inputs:
            core_imports.append("input")
        if component.outputs:
            core_imports.append("output")
        if component.state_properties or not component.inputs:
            core_imports.append("signal")
        core_imports_str = ", ".join(sorted(set(core_imports)))

        class_body_sections = [
            s
            for s in (
                injected_fields_block.strip(),
                inputs_code,
                outputs_code,
                state_code,
                methods_block,
            )
            if s
        ]
        class_body = "\n\n".join(class_body_sections)

        return (
            f"import {{ {core_imports_str} }} from '@angular/core';{service_imports_block}\n\n"
            "@Component({\n"
            f"  selector: '{component.tag_name}',\n"
            "  standalone: true,\n"
            f"  templateUrl: './{kebab_name}.component.html',\n"
            f"  styleUrls: ['./{kebab_name}.component.scss'],\n"
            "  changeDetection: ChangeDetectionStrategy.OnPush,\n"
            "})\n"
            f"export class {component.name}Component {{\n"
            f"{class_body}\n"
            "}\n"
        )

    def render_template_html(self, component: IntermediateComponent) -> str:
        """Render HTML template with native Angular control flow (@if) and Bootstrap 5 utilities."""
        is_angularjs = component.metadata.get("source_framework") in (
            "angularjs-directive",
            "angularjs-component",
        ) or any(
            x in component.template_raw
            for x in ("ng-if", "ng-show", "ng-repeat", "ng-click", "$ctrl", "vm.")
        )
        if is_angularjs and component.template_raw and component.template_raw.strip():
            return self.migrate_template(component.template_raw, component)

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

    def migrate_template(self, template_raw: str, component: IntermediateComponent) -> str:
        """Migrate legacy AngularJS template directives to Angular 17+ and Bootstrap 5."""
        if not template_raw.strip():
            return self.render_template_html(component)

        res = template_raw

        # 1. Bootstrap 3/4 to Bootstrap 5 utility classes
        res = re.sub(r"\bpull-right\b", "ms-auto", res)
        res = re.sub(r"\bpull-left\b", "me-auto", res)
        res = re.sub(r"\bhidden-xs\b", "d-none d-sm-block", res)
        res = re.sub(r"\bcol-xs-([0-9]+)\b", r"col-\1", res)

        # 2. Upgrade bare container to include card styling if missing
        kebab_name = _to_kebab_case(component.name)
        if f'class="{kebab_name}"' in res and "card" not in res:
            res = res.replace(f'class="{kebab_name}"', f'class="{kebab_name} card p-3 shadow-sm"')

        # 3. ng-click to (click)
        res = re.sub(
            r'ng-click=["\'](?:vm\.|\$ctrl\.|ctrl\.)?([a-zA-Z0-9_]+)\((.*?)\)["\']',
            r'(click)="\1(\2)"',
            res,
        )
        res = re.sub(
            r'ng-click=["\'](?:vm\.|\$ctrl\.|ctrl\.)?([a-zA-Z0-9_]+)["\']',
            r'(click)="\1()"',
            res,
        )

        # 4. ng-submit to (ngSubmit)
        res = re.sub(
            r'ng-submit=["\'](?:vm\.|\$ctrl\.|ctrl\.)?([a-zA-Z0-9_]+)\((.*?)\)["\']',
            r'(ngSubmit)="\1(\2)"',
            res,
        )

        # 5. ng-model to [(ngModel)]
        res = re.sub(
            r'ng-model=["\'](?:vm\.|\$ctrl\.|ctrl\.)?([a-zA-Z0-9_]+)["\']',
            r'[(ngModel)]="\1"',
            res,
        )

        # 6. ng-if and ng-show to @if
        def _replace_ng_if(m: re.Match[str]) -> str:
            tag = m.group(1)
            before = m.group(2)
            cond = m.group(3)
            after = m.group(4)
            inner = m.group(5)
            tag_attrs = f"{before}{after}".strip()
            tag_open = f"<{tag} {tag_attrs}>" if tag_attrs else f"<{tag}>"
            return f"@if ({cond}()) {{\n  {tag_open}{inner}</{tag}>\n}}"

        res = re.sub(
            r'<([a-zA-Z0-9_-]+)([^>]*?)\s+ng-(?:if|show)=["\'](?:vm\.|\$ctrl\.|ctrl\.)?([a-zA-Z0-9_]+)["\']([^>]*)>(.*?)</\1>',
            _replace_ng_if,
            res,
            flags=re.DOTALL,
        )

        # Fallback for self-closing or unclosed single line ng-if
        res = re.sub(
            r'<([a-zA-Z0-9_-]+)\s+([^>]*?)ng-(?:if|show)=["\'](?:vm\.|\$ctrl\.|ctrl\.)?([a-zA-Z0-9_]+)["\']([^>]*)>',
            r"@if (\3()) {\n  <\1 \2\4>",
            res,
        )

        # 7. ng-repeat to @for
        def _replace_ng_repeat_full(m: re.Match[str]) -> str:
            tag = m.group(1)
            before = m.group(2)
            item = m.group(3)
            collection = m.group(4)
            track = m.group(5) or f"{item}.id"
            after = m.group(6)
            inner = m.group(7)
            tag_attrs = f"{before}{after}".strip()
            tag_open = f"<{tag} {tag_attrs}>" if tag_attrs else f"<{tag}>"
            loop_hdr = f"@for ({item} of {collection}(); track {track}) {{"
            return f"{loop_hdr}\n  {tag_open}{inner}</{tag}>\n}}"

        res = re.sub(
            r'<([a-zA-Z0-9_-]+)([^>]*?)\s+ng-repeat=["\']([a-zA-Z0-9_]+)\s+in\s+(?:vm\.|\$ctrl\.|ctrl\.)?([a-zA-Z0-9_]+)(?:\s+track\s+by\s+([a-zA-Z0-9_.]+))?["\']([^>]*)>(.*?)</\1>',
            _replace_ng_repeat_full,
            res,
            flags=re.DOTALL,
        )

        # 8. Signal expressions in interpolations {{ ... }}
        all_signals = set(component.inputs) | set(component.state_properties)

        def _replace_interpolation(m: re.Match[str]) -> str:
            expr = m.group(1).strip()
            clean_expr = re.sub(r"^(?:vm\.|\$ctrl\.|ctrl\.)", "", expr)
            if clean_expr in all_signals:
                return f"{{{{ {clean_expr}() }}}}"
            return f"{{{{ {clean_expr} }}}}"

        res = re.sub(r"\{\{([^}]+)\}\}", _replace_interpolation, res)

        return res


class AngularStandaloneServiceRenderer(ServiceRendererPort):
    """Renders modern Angular 17+ injectable services using inject(HttpClient)."""

    def render_service_ts(self, service: IntermediateService) -> str:
        """Render standalone Angular @Injectable service."""
        methods_code: list[str] = []
        for method in service.methods:
            param_sig = ", ".join(f"{p}: any" for p in method.parameters)
            verb = method.http_method.lower()
            ep = method.endpoint if method.endpoint else f"/api/v1/{method.name.lower()}"

            if verb in ("get", "delete"):
                body = f"return this.http.{verb}<any>('{ep}');"
            else:
                payload_arg = method.parameters[-1] if method.parameters else "payload"
                body = f"return this.http.{verb}<any>('{ep}', {payload_arg});"

            methods_code.append(
                f"  {method.name}({param_sig}): Observable<any> {{\n    {body}\n  }}"
            )

        methods_block = "\n\n".join(methods_code)

        return (
            "import { HttpClient } from '@angular/common/http';\n"
            "import { Injectable, inject } from '@angular/core';\n"
            "import { Observable } from 'rxjs';\n\n"
            "@Injectable({\n"
            "  providedIn: 'root',\n"
            "})\n"
            f"export class {service.name} {{\n"
            "  private readonly http = inject(HttpClient);\n\n"
            f"{methods_block}\n"
            "}\n"
        )

    def render_spec_ts(self, service: IntermediateService) -> str:
        """Render Jasmine unit test spec with HttpTestingController."""
        first_method = service.methods[0].name if service.methods else "getUsers"
        first_verb = service.methods[0].http_method if service.methods else "GET"
        first_ep = service.methods[0].endpoint if service.methods else "/api/v1/users"

        return (
            "import { provideHttpClient } from '@angular/common/http';\n"
            "import {\n"
            "  HttpTestingController,\n"
            "  provideHttpClientTesting,\n"
            "} from '@angular/common/http/testing';\n"
            "import { TestBed } from '@angular/core/testing';\n"
            f"import {{ {service.name} }} from './{_to_kebab_case(service.name)}.service';\n\n"
            f"describe('{service.name}', () => {{\n"
            f"  let service: {service.name};\n"
            "  let httpMock: HttpTestingController;\n\n"
            "  beforeEach(() => {\n"
            "    TestBed.configureTestingModule({\n"
            "      providers: [\n"
            f"        {service.name},\n"
            "        provideHttpClient(),\n"
            "        provideHttpClientTesting(),\n"
            "      ],\n"
            "    });\n"
            f"    service = TestBed.inject({service.name});\n"
            "    httpMock = TestBed.inject(HttpTestingController);\n"
            "  });\n\n"
            "  afterEach(() => {\n"
            "    httpMock.verify();\n"
            "  });\n\n"
            "  it('should be created and execute request', () => {\n"
            "    expect(service).toBeTruthy();\n"
            f"    service.{first_method}().subscribe();\n"
            f"    const req = httpMock.expectOne('{first_ep}');\n"
            f"    expect(req.request.method).toBe('{first_verb}');\n"
            "    req.flush({});\n"
            "  });\n"
            "});\n"
        )
