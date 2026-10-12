"""Deterministic foundation rendering for registered, owner-approved Angular presets."""

import json
import re
from pathlib import Path
from typing import Any

from migration_agent.adapters.access_rules import governance_rule_digests, rule_text_digest
from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.filesystem import read_repository_text
from migration_agent.adapters.knowledge import GitKnowledgeAdapter
from migration_agent.domain.access import AccessPolicy, AccessProposal, GovernanceFileChange
from migration_agent.domain.changeset import (
    FileChange,
    FileMode,
    FileOperation,
    compute_file_sha256,
)
from migration_agent.domain.knowledge import ArchitecturalDecisionRecord, DecisionStatus
from migration_agent.domain.stack import (
    ArchitectureManifest,
    ReplacementStrategy,
    StackRecommendationDraft,
    TargetStackPreset,
    compute_draft_digest,
)
from migration_agent.domain.stack_catalog import get_default_target_preset, get_target_preset
from migration_agent.ports.filesystem import InspectionPolicy
from migration_agent.ports.transformation import FoundationTransformationPort


class BoundFoundationTransformationAdapter(FoundationTransformationPort):
    """Render only the current draft confirmed by the project's foundation ADRs."""

    configuration_paths = (
        "package.json",
        "angular.json",
        "tsconfig.json",
        "tsconfig.app.json",
        "tsconfig.spec.json",
        "eslint.config.mjs",
        "vite.config.ts",
        "src/test-setup.ts",
    )

    def __init__(self, authorization: ProjectAuthorization) -> None:
        self.authorization = authorization

    def confirmed_draft(
        self, draft: StackRecommendationDraft | None = None
    ) -> StackRecommendationDraft:
        self.authorization.require("project.read")
        governance = Path(self.authorization.service().store.binding.governance_root)
        if draft is None:
            draft = StackRecommendationDraft.model_validate_json(
                read_repository_text(
                    governance,
                    ".agent/drafts/stack_recommendation.json",
                    policy=InspectionPolicy(max_text_file_bytes=65536),
                )
            )
        if draft.content_digest != compute_draft_digest(draft):
            raise ValueError("FOUNDATION_DRAFT_INVALID: regenerate the exact bounded draft.")
        if get_target_preset(draft.preset.preset_id) != draft.preset:
            raise ValueError("FOUNDATION_PRESET_UNSUPPORTED: select an installed adapter preset.")
        if any(mapping.strategy == ReplacementStrategy.CUSTOM for mapping in draft.mappings):
            raise ValueError(
                "FOUNDATION_MAPPING_REQUIRED: resolve or explicitly defer unmapped packages."
            )
        manifest = verified_architecture(self.authorization, draft)
        decisions = [
            GitKnowledgeAdapter._deserialize_document(
                read_repository_text(governance, path), ArchitecturalDecisionRecord
            )
            for path in sorted(manifest.decision_digests)
        ]
        scopes = {
            d.metadata.get("scope")
            for d in decisions
            if d.status == DecisionStatus.ACCEPTED
            and d.metadata.get("draft_digest") == draft.content_digest
        }
        if not {"target_framework", "ui_styling", "reactivity_state"} <= scopes:
            raise ValueError(
                "FOUNDATION_ARCHITECTURE_REQUIRED: confirm this exact draft's "
                "foundation ADRs first."
            )
        return draft

    def contract_digest(self) -> str:
        return self.confirmed_draft().content_digest

    def render_foundation_files(
        self,
        project_name: str,
        preset: TargetStackPreset | None = None,
        draft: StackRecommendationDraft | None = None,
    ) -> dict[str, str]:
        self.authorization.require("changeset.stage")
        draft = self.confirmed_draft(draft)
        if preset is not None and preset != draft.preset:
            raise ValueError(
                "FOUNDATION_ARCHITECTURE_CONFLICT: preset differs from accepted architecture."
            )
        return FoundationTransformationAdapter().render_foundation_files(project_name, draft=draft)


def verified_architecture(
    authorization: ProjectAuthorization, draft: StackRecommendationDraft
) -> ArchitectureManifest:
    authorization.require("project.read")
    policy = authorization.service().store.read()
    governance = Path(policy.binding.governance_root)
    if ".agent/architecture.json" not in policy.rules:
        raise ValueError(
            "FOUNDATION_ARCHITECTURE_REQUIRED: prepare and sign the exact architecture "
            "proposal in the owner terminal."
        )
    manifest = ArchitectureManifest.model_validate_json(
        read_repository_text(governance, ".agent/architecture.json")
    )
    from migration_agent.adapters.mcp.tools import _create_default_framework_registry
    from migration_agent.adapters.project_evidence import LocalProjectEvidence

    base = LocalProjectEvidence(
        Path(policy.binding.source_root), _create_default_framework_registry(), authorization
    ).repository_state()
    if (
        not base.clean
        or base.revision != manifest.source_revision
        or base.fingerprint != manifest.source_fingerprint
    ):
        raise ValueError("BASE_CHANGED: regenerate architecture for the clean current source.")
    if (
        manifest.draft_digest != draft.content_digest
        or manifest.preset_id != draft.preset.preset_id
        or manifest.source_revision != draft.source_revision
    ):
        raise ValueError(
            "ARCHITECTURE_CHANGED: the current draft differs from the owner-signed architecture."
        )
    for path, digest in manifest.decision_digests.items():
        if (
            rule_text_digest(path, read_repository_text(governance, path)) != digest
            or policy.rules.get(path) != digest
        ):
            raise ValueError(
                "ARCHITECTURE_CHANGED: decision bytes differ from the owner-signed architecture."
            )
    return manifest


def prepare_architecture(
    authorization: ProjectAuthorization, draft: StackRecommendationDraft
) -> AccessProposal:
    authorization.require("knowledge.approve")
    service = authorization.service()
    policy = service.view()
    governance = Path(policy.binding.governance_root)
    from migration_agent.adapters.mcp.tools import _create_default_framework_registry
    from migration_agent.adapters.project_evidence import LocalProjectEvidence

    base = LocalProjectEvidence(
        Path(policy.binding.source_root), _create_default_framework_registry(), authorization
    ).repository_state()
    if not base.clean or base.revision != draft.source_revision:
        raise ValueError("BASE_CHANGED: regenerate architecture for the clean current source.")
    decisions = [
        decision
        for decision in GitKnowledgeAdapter().list_decisions(str(governance))
        if decision.status == DecisionStatus.ACCEPTED
        and decision.metadata.get("draft_digest") == draft.content_digest
    ]
    digests = {
        f".agent/decisions/{decision.decision_id}.md": rule_text_digest(
            f".agent/decisions/{decision.decision_id}.md",
            read_repository_text(governance, f".agent/decisions/{decision.decision_id}.md"),
        )
        for decision in decisions
    }
    manifest = ArchitectureManifest(
        source_revision=base.revision,
        source_fingerprint=base.fingerprint,
        draft_digest=draft.content_digest,
        preset_id=draft.preset.preset_id,
        decision_digests=digests,
    )
    rules = governance_rule_digests(governance)
    existing = governance / ".agent/architecture.json"
    if existing.exists():
        old = ArchitectureManifest.model_validate_json(
            read_repository_text(governance, ".agent/architecture.json")
        )
        for path in old.decision_digests:
            rules.pop(path, None)
    content = manifest.model_dump_json(indent=2) + "\n"
    rules.update(digests)
    rules[".agent/architecture.json"] = rule_text_digest(".agent/architecture.json", content)
    candidate = AccessPolicy.model_validate_json(
        policy.model_copy(
            update={
                "revision": policy.revision + 1,
                "previous_digest": policy.digest,
                "rules": rules,
            }
        ).model_dump_json()
    )
    return service.propose(
        candidate,
        (
            GovernanceFileChange(
                path=".agent/architecture.json",
                previous_digest=compute_file_sha256(existing.read_bytes())
                if existing.exists()
                else None,
                content=content,
            ),
        ),
    )


def sanitize_project_name(raw_name: str) -> str:
    """Sanitize project name into a valid npm and Angular identifier."""
    name = raw_name.strip().lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "modern-app"


class FoundationTransformationAdapter(FoundationTransformationPort):
    """Generates the foundational configuration and bootstrap code for the modern target stack."""

    def __init__(self, default_preset: TargetStackPreset | None = None) -> None:
        self.preset = default_preset or get_default_target_preset()

    def render_foundation_files(
        self,
        project_name: str,
        preset: TargetStackPreset | None = None,
        draft: StackRecommendationDraft | None = None,
    ) -> dict[str, str]:
        """Render all foundational target files as relative path -> UTF-8 string mappings."""
        active_preset = preset or (draft.preset if draft else self.preset)
        modern = active_preset.validation_catalog == "node-angular-v21"
        pkg_name = sanitize_project_name(project_name)

        # 1. Compile dependencies and devDependencies
        deps: dict[str, str] = {
            pkg.name: pkg.version_spec for pkg in active_preset.base_dependencies
        }
        dev_deps: dict[str, str] = {
            pkg.name: pkg.version_spec for pkg in active_preset.base_dev_dependencies
        }

        # Include mapped package replacements from draft if present
        if draft is not None:
            for mapping in draft.mappings:
                if mapping.strategy == ReplacementStrategy.REPLACE:
                    for target_pkg in mapping.target_packages:
                        if modern and target_pkg.name == "@angular-devkit/build-angular":
                            continue
                        if target_pkg.is_dev:
                            dev_deps[target_pkg.name] = target_pkg.version_spec
                        else:
                            deps[target_pkg.name] = target_pkg.version_spec
        deps.update({pkg.name: pkg.version_spec for pkg in active_preset.base_dependencies})
        dev_deps.update({pkg.name: pkg.version_spec for pkg in active_preset.base_dev_dependencies})

        # 2. Render package.json
        pkg_data: dict[str, Any] = {
            "name": pkg_name,
            "version": "0.0.0",
            "private": True,
            "scripts": {
                "ng": "ng",
                "start": "ng serve",
                "build": "ng build",
                "watch": "ng build --watch --configuration development",
                "test": "vitest run",
                "lint": "eslint src",
            },
            "dependencies": dict(sorted(deps.items())),
            "devDependencies": dict(sorted(dev_deps.items())),
        }
        package_json_str = json.dumps(pkg_data, indent=2) + "\n"

        # 3. Render tsconfig.json
        tsconfig_data: dict[str, Any] = {
            "compileOnSave": False,
            "compilerOptions": {
                "baseUrl": "./",
                "outDir": "./dist/out-tsc",
                "forceConsistentCasingInFileNames": True,
                "strict": True,
                "noImplicitOverride": True,
                "noPropertyAccessFromIndexSignature": True,
                "noImplicitReturns": True,
                "noFallthroughCasesInSwitch": True,
                "sourceMap": True,
                "declaration": False,
                "downlevelIteration": True,
                "experimentalDecorators": True,
                "moduleResolution": "node",
                "importHelpers": True,
                "target": "ES2022",
                "module": "ES2022",
                "useDefineForClassFields": False,
                "lib": ["ES2022", "dom"],
            },
            "angularCompilerOptions": {
                "enableI18nLegacyMessageIdFormat": False,
                "strictInjectionParameters": True,
                "strictInputAccessModifiers": True,
                "strictTemplates": True,
            },
        }
        tsconfig_json_str = json.dumps(tsconfig_data, indent=2) + "\n"

        # 4. Render tsconfig.app.json
        tsconfig_app_data: dict[str, Any] = {
            "extends": "./tsconfig.json",
            "compilerOptions": {
                "outDir": "./out-tsc/app",
                "types": [],
            },
            "files": ["src/main.ts"],
            "include": ["src/**/*.ts"],
            "exclude": ["src/**/*.spec.ts", "src/test-setup.ts"],
        }
        tsconfig_app_json_str = json.dumps(tsconfig_app_data, indent=2) + "\n"

        # 5. Render angular.json
        angular_json_data: dict[str, Any] = {
            "$schema": "./node_modules/@angular/cli/lib/config/schema.json",
            "version": 1,
            "newProjectRoot": "projects",
            "projects": {
                pkg_name: {
                    "projectType": "application",
                    "schematics": {
                        "@schematics/angular:component": {
                            "style": "scss",
                            "standalone": True,
                            "changeDetection": "OnPush",
                        }
                    },
                    "root": "",
                    "sourceRoot": "src",
                    "prefix": "app",
                    "architect": {
                        "build": {
                            "builder": "@angular-devkit/build-angular:application",
                            "options": {
                                "outputPath": f"dist/{pkg_name}",
                                "index": "src/index.html",
                                "browser": "src/main.ts",
                                "polyfills": ["zone.js"],
                                "tsConfig": "tsconfig.app.json",
                                "inlineStyleLanguage": "scss",
                                "assets": [
                                    {
                                        "glob": "**/*",
                                        "input": "public",
                                    }
                                ],
                                "styles": ["src/styles.scss"],
                                "scripts": [],
                            },
                            "configurations": {
                                "production": {
                                    "budgets": [
                                        {
                                            "type": "initial",
                                            "maximumWarning": "1MB",
                                            "maximumError": "2MB",
                                        }
                                    ],
                                    "outputHashing": "all",
                                },
                                "development": {
                                    "optimization": False,
                                    "extractLicenses": False,
                                    "sourceMap": True,
                                },
                            },
                            "defaultConfiguration": "production",
                        },
                        "serve": {
                            "builder": "@angular-devkit/build-angular:dev-server",
                            "configurations": {
                                "production": {
                                    "buildTarget": f"{pkg_name}:build:production",
                                },
                                "development": {
                                    "buildTarget": f"{pkg_name}:build:development",
                                },
                            },
                            "defaultConfiguration": "development",
                        },
                    },
                }
            },
        }
        angular_json_str = json.dumps(angular_json_data, indent=2) + "\n"

        # 6. Render src/index.html
        index_html_str = (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8">\n'
            f"  <title>{pkg_name}</title>\n"
            '  <base href="/">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "</head>\n"
            "<body>\n"
            "  <app-root></app-root>\n"
            "</body>\n"
            "</html>\n"
        )

        # 7. Render src/main.ts
        main_ts_str = (
            "import { bootstrapApplication } from '@angular/platform-browser';\n"
            "import { appConfig } from './app/app.config';\n"
            "import { AppComponent } from './app/app.component';\n\n"
            "bootstrapApplication(AppComponent, appConfig).catch((err) => con"
            "sole.error(err));\n"
        )

        # 8. Render src/app/app.config.ts
        app_config_ts_str = (
            "import { ApplicationConfig } from '@angular/core';\n"
            "import { provideRouter } from '@angular/router';\n"
            "import { routes } from './app.routes';\n\n"
            "export const appConfig: ApplicationConfig = {\n"
            "  providers: [provideRouter(routes)],\n"
            "};\n"
        )

        # 9. Render src/app/app.routes.ts
        app_routes_ts_str = (
            "import { Routes } from '@angular/router';\n\nexport const routes: Routes = [];\n"
        )

        # 10. Render src/app/app.component.ts
        app_component_ts_str = (
            "import { ChangeDetectionStrategy, Component } from '@angular/core';\n"
            "import { RouterOutlet } from '@angular/router';\n\n"
            "@Component({\n"
            "  selector: 'app-root',\n"
            "  standalone: true,\n"
            "  imports: [RouterOutlet],\n"
            '  template: \'<main class="container py-4"><h1>Application</h1>'
            "<router-outlet></router-outlet></main>',\n"
            "  changeDetection: ChangeDetectionStrategy.OnPush,\n"
            "})\n"
            "export class AppComponent {\n"
            f"  title = '{pkg_name}';\n"
            "}\n"
        )

        # 11. Render src/styles.scss
        styles_scss_str = (
            "// Modern Bootstrap 5.3.3 utilities and reset\n"
            '@import "bootstrap/scss/functions";\n'
            '@import "bootstrap/scss/variables";\n'
            '@import "bootstrap/scss/maps";\n'
            '@import "bootstrap/scss/mixins";\n'
            '@import "bootstrap/scss/utilities";\n'
            '@import "bootstrap/scss/reboot";\n'
            '@import "bootstrap/scss/utilities/api";\n\n'
            ":root {\n"
            '  --app-font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;\n'
            "}\n\n"
            "html, body {\n"
            "  height: 100%;\n"
            "  margin: 0;\n"
            "  font-family: var(--app-font-family);\n"
            "}\n"
        )

        files = {
            "package.json": package_json_str,
            "tsconfig.json": tsconfig_json_str,
            "tsconfig.app.json": tsconfig_app_json_str,
            "angular.json": angular_json_str,
            "src/index.html": index_html_str,
            "src/main.ts": main_ts_str,
            "src/app/app.config.ts": app_config_ts_str,
            "src/app/app.routes.ts": app_routes_ts_str,
            "src/app/app.component.ts": app_component_ts_str,
            "src/styles.scss": styles_scss_str,
            "eslint.config.mjs": (
                "import parser from '@typescript-eslint/parser';\n"
                "export default [{ files: ['src/**/*.ts'],\n"
                "  languageOptions: { parser, ecmaVersion: 2022, sourceType: 'module' },\n"
                "  rules: { 'no-debugger': 'error', 'no-duplicate-imports': 'error' } }];\n"
            ),
            "tsconfig.spec.json": json.dumps(
                {
                    "extends": "./tsconfig.json",
                    "compilerOptions": {
                        "outDir": "./out-tsc/spec",
                        "types": ["vitest/globals", "node"],
                    },
                    "files": ["src/test-setup.ts"],
                    "include": ["src/**/*.ts"],
                },
                indent=2,
            )
            + "\n",
            "vite.config.ts": (
                "import { fileURLToPath } from 'node:url';\n"
                "import { defineConfig } from 'vitest/config';\n"
                "import angular from '@analogjs/vite-plugin-angular';\n\n"
                "export default defineConfig({\n"
                "  plugins: [angular({ tsconfig: fileURLToPath(new URL('./tsconfi"
                "g.spec.json', import.meta.url)) })],\n"
                "  test: { globals: true, environment: 'jsdom',\n"
                "    setupFiles: ['src/test-setup.ts'], include: ['src/**/*.spec.ts'],\n"
                "    pool: 'forks', poolOptions: { forks: { singleFork: true } } },\n"
                "});\n"
            ),
            "src/test-setup.ts": (
                "import '@angular/compiler';\n"
                "import '@analogjs/vitest-angular/setup-zone';\n"
                "import { getTestBed } from '@angular/core/testing';\n"
                "import { BrowserDynamicTestingModule, platformBrowserDynamicTesting } "
                "from '@angular/platform-browser-dynamic/testing';\n\n"
                "getTestBed().initTestEnvironment(BrowserDynamicTestingModule,\n"
                "  platformBrowserDynamicTesting(), { teardown: { destroyAfterEach: true } });\n"
            ),
            "src/app/app.component.spec.ts": (
                "import { TestBed } from '@angular/core/testing';\n"
                "import { provideRouter } from '@angular/router';\n"
                "import { AppComponent } from './app.component';\n\n"
                "describe('Application foundation', () => {\n"
                "  it('renders its shell', async () => {\n"
                "    await TestBed.configureTestingModule({ imports: [AppComponent],\n"
                "      providers: [provideRouter([])] }).compileComponents();\n"
                "    const fixture = TestBed.createComponent(AppComponent);\n"
                "    fixture.detectChanges();\n"
                "    expect(fixture.nativeElement.querySelector('h1')?.textConten"
                "t).toBe('Application');\n"
                "  });\n"
                "});\n"
            ),
        }
        if modern:
            pkg_data["scripts"]["test"] = "ng test"
            files["package.json"] = json.dumps(pkg_data, indent=2) + "\n"
            architect = angular_json_data["projects"][pkg_name]["architect"]
            architect["build"]["builder"] = "@angular/build:application"
            architect["build"]["options"]["polyfills"] = []
            architect["serve"]["builder"] = "@angular/build:dev-server"
            architect["test"] = {
                "builder": "@angular/build:unit-test",
                "options": {
                    "runner": "vitest",
                    "runnerConfig": "vite.config.ts",
                    "watch": False,
                    "tsConfig": "tsconfig.spec.json",
                    "buildTarget": f"{pkg_name}:build:development",
                },
            }
            files["angular.json"] = json.dumps(angular_json_data, indent=2) + "\n"
            files["vite.config.ts"] = (
                "import { defineConfig } from 'vitest/config';\n"
                "export default defineConfig({ test: { pool: 'threads', maxWorkers: 1, "
                "fileParallelism: false } });\n"
            )
            files["src/test-setup.ts"] = "export {};\n"
            files["eslint.config.mjs"] = (
                "import tseslint from 'typescript-eslint';\n"
                "export default [{ files: ['src/**/*.ts'],\n"
                "  languageOptions: { parser: tseslint.parser, ecmaVersion: 2022, "
                "sourceType: 'module' },\n"
                "  rules: { 'no-debugger': 'error', 'no-duplicate-imports': 'error' } }];\n"
            )
        return files

    def render_foundation_changes(
        self,
        project_name: str,
        preset: TargetStackPreset | None = None,
        draft: StackRecommendationDraft | None = None,
    ) -> list[FileChange]:
        """Render all foundational target files as FileChange records for ChangeSet.

        Materializes all skeleton files deterministically.
        """
        files = self.render_foundation_files(project_name, preset=preset, draft=draft)
        changes: list[FileChange] = []

        for rel_path, content_str in sorted(files.items()):
            content_bytes = content_str.encode("utf-8")
            digest = compute_file_sha256(content_bytes)
            changes.append(
                FileChange(
                    path=rel_path,
                    operation=FileOperation.CREATE,
                    file_mode=FileMode.STANDARD,
                    content_digest=digest,
                    content_bytes=content_bytes,
                )
            )

        return changes
