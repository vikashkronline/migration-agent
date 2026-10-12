"""Deterministic catalog of modern presets, library categories, and package translation mappings."""

from migration_agent.domain.stack import (
    LibraryCategory,
    PackageCoordinate,
    PackageMappingOutcome,
    ReplacementStrategy,
    TargetStackPreset,
)

ANGULAR_17_LTS_PRESET = TargetStackPreset(
    preset_id="angular-17-lts-bootstrap5",
    label="Angular 17.3 compatibility baseline with Bootstrap 5",
    description=(
        "Modern standalone components with Signals, Bootstrap 5.3 utilities, "
        "and Vitest test runner."
    ),
    target_framework="Angular 17.3.x (Standalone)",
    angular_version="17.3.12",
    typescript_version="~5.4.5",
    rxjs_version="~7.8.1",
    ui_library="Bootstrap 5.3.3 Utilities",
    test_framework="Vitest 1.6.x + Analog Angular adapter 1.6",
    directory_structure={
        "src/app/core": (
            "Singleton services, global guards, interceptors, and environment configuration."
        ),
        "src/app/shared": "Reusable dumb components, directives, pipes, and UI utilities.",
        "src/app/features": "Domain-specific routed feature modules and state.",
        "src/styles": "Global theme SCSS variables and Bootstrap utility imports.",
    },
    base_dependencies=(
        PackageCoordinate(name="@angular/animations", version_spec="17.3.12"),
        PackageCoordinate(name="@angular/common", version_spec="17.3.12"),
        PackageCoordinate(name="@angular/compiler", version_spec="17.3.12"),
        PackageCoordinate(name="@angular/core", version_spec="17.3.12"),
        PackageCoordinate(name="@angular/forms", version_spec="17.3.12"),
        PackageCoordinate(name="@angular/platform-browser", version_spec="17.3.12"),
        PackageCoordinate(name="@angular/platform-browser-dynamic", version_spec="17.3.12"),
        PackageCoordinate(name="@angular/router", version_spec="17.3.12"),
        PackageCoordinate(name="rxjs", version_spec="~7.8.1"),
        PackageCoordinate(name="tslib", version_spec="^2.3.0"),
        PackageCoordinate(name="zone.js", version_spec="~0.14.3"),
        PackageCoordinate(name="bootstrap", version_spec="^5.3.3"),
    ),
    base_dev_dependencies=(
        PackageCoordinate(
            name="@angular-devkit/build-angular", version_spec="17.3.12", is_dev=True
        ),
        PackageCoordinate(name="@angular/cli", version_spec="17.3.12", is_dev=True),
        PackageCoordinate(name="@angular/compiler-cli", version_spec="17.3.12", is_dev=True),
        PackageCoordinate(name="typescript", version_spec="~5.4.5", is_dev=True),
        PackageCoordinate(name="vitest", version_spec="^1.6.0", is_dev=True),
        PackageCoordinate(name="vite", version_spec="^5.2.0", is_dev=True),
        PackageCoordinate(name="jsdom", version_spec="^24.0.0", is_dev=True),
        PackageCoordinate(name="sass", version_spec="^1.77.0", is_dev=True),
        PackageCoordinate(name="@analogjs/vite-plugin-angular", version_spec="1.6.0", is_dev=True),
        PackageCoordinate(name="@analogjs/vitest-angular", version_spec="1.6.0", is_dev=True),
        PackageCoordinate(name="@types/node", version_spec="~20.14.0", is_dev=True),
        PackageCoordinate(name="eslint", version_spec="8.57.1", is_dev=True),
        PackageCoordinate(name="@typescript-eslint/parser", version_spec="7.18.0", is_dev=True),
    ),
)

ANGULAR_21_PRESET = TargetStackPreset(
    preset_id="angular-21-bootstrap5",
    label="Angular 21.2 (Standalone + Signals) with Bootstrap 5",
    description="Angular CLI Vitest testing, zoneless change detection and Bootstrap utilities.",
    target_framework="Angular 21.2.x (Standalone)",
    angular_version="21.2.25",
    typescript_version="~5.9.3",
    rxjs_version="~7.8.1",
    ui_library="Bootstrap 5.3 Utilities",
    test_framework="Vitest 4.x through Angular CLI",
    validation_catalog="node-angular-v21",
    directory_structure=ANGULAR_17_LTS_PRESET.directory_structure,
    base_dependencies=(
        *(
            PackageCoordinate(name=name, version_spec="21.2.25")
            for name in (
                "@angular/common",
                "@angular/compiler",
                "@angular/core",
                "@angular/forms",
                "@angular/platform-browser",
                "@angular/router",
            )
        ),
        PackageCoordinate(name="rxjs", version_spec="~7.8.1"),
        PackageCoordinate(name="tslib", version_spec="^2.3.0"),
        PackageCoordinate(name="bootstrap", version_spec="^5.3.3"),
    ),
    base_dev_dependencies=(
        PackageCoordinate(name="@angular/build", version_spec="21.2.25", is_dev=True),
        PackageCoordinate(name="@angular/cli", version_spec="21.2.25", is_dev=True),
        PackageCoordinate(name="@angular/compiler-cli", version_spec="21.2.25", is_dev=True),
        PackageCoordinate(name="typescript", version_spec="~5.9.3", is_dev=True),
        PackageCoordinate(name="vitest", version_spec="4.1.11", is_dev=True),
        PackageCoordinate(name="jsdom", version_spec="^27.0.1", is_dev=True),
        PackageCoordinate(name="eslint", version_spec="9.39.1", is_dev=True),
        PackageCoordinate(name="typescript-eslint", version_spec="8.48.0", is_dev=True),
        PackageCoordinate(name="@types/node", version_spec="^22.0.0", is_dev=True),
        PackageCoordinate(name="sass", version_spec="^1.77.0", is_dev=True),
    ),
)

_AVAILABLE_PRESETS: tuple[TargetStackPreset, ...] = (ANGULAR_21_PRESET, ANGULAR_17_LTS_PRESET)

_CURATED_MAPPINGS: dict[str, PackageMappingOutcome] = {
    "ember-source": PackageMappingOutcome(
        legacy_name="ember-source",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(
            PackageCoordinate(name="@angular/core", version_spec="17.3.12"),
            PackageCoordinate(name="@angular/common", version_spec="17.3.12"),
        ),
        rationale=(
            "Modern standalone components with Signals and Angular 17 control flow (@if, @for)."
        ),
        behavioral_notes="Replaces Ember Classic components, Glimmer templates, and runloops.",
    ),
    "ember-cli": PackageMappingOutcome(
        legacy_name="ember-cli",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(
            PackageCoordinate(name="@angular/cli", version_spec="17.3.12", is_dev=True),
            PackageCoordinate(
                name="@angular-devkit/build-angular", version_spec="17.3.12", is_dev=True
            ),
        ),
        rationale="Modern Angular CLI and esbuild/Vite application builder pipeline.",
    ),
    "ember-data": PackageMappingOutcome(
        legacy_name="ember-data",
        strategy=ReplacementStrategy.CUSTOM,
        target_packages=(),
        rationale=(
            "Ember Data identity map and record caching require custom typed REST services. "
            "Handled in feature phases."
        ),
        behavioral_notes="Do not introduce monolithic ORM clients during base foundation setup.",
    ),
    "ember-cli-bootstrap-sassy": PackageMappingOutcome(
        legacy_name="ember-cli-bootstrap-sassy",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(PackageCoordinate(name="bootstrap", version_spec="^5.3.3"),),
        rationale=(
            "Modern Flexbox/Grid CSS utility classes; drops jQuery and obsolete Bootstrap 3 CSS."
        ),
    ),
    "bootstrap-sass": PackageMappingOutcome(
        legacy_name="bootstrap-sass",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(PackageCoordinate(name="bootstrap", version_spec="^5.3.3"),),
        rationale=(
            "Migrate from Sass 3/Sass-Ruby port to official Bootstrap 5 Dart-Sass distribution."
        ),
    ),
    "moment": PackageMappingOutcome(
        legacy_name="moment",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(PackageCoordinate(name="date-fns", version_spec="^3.6.0"),),
        rationale=(
            "Pure, immutable, tree-shakeable functions replacing heavy mutable Moment instances."
        ),
    ),
    "ember-moment": PackageMappingOutcome(
        legacy_name="ember-moment",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(PackageCoordinate(name="date-fns", version_spec="^3.6.0"),),
        rationale=(
            "Replace template helpers with custom Angular pure pipes powered by "
            "date-fns or native Intl."
        ),
    ),
    "ember-concurrency": PackageMappingOutcome(
        legacy_name="ember-concurrency",
        strategy=ReplacementStrategy.NATIVE,
        target_packages=(PackageCoordinate(name="rxjs", version_spec="~7.8.1"),),
        rationale=(
            "Generator tasks translate cleanly to RxJS observable pipelines (takeUntilDestroyed) "
            "and Angular Signals."
        ),
        behavioral_notes=(
            "Explicitly retains rxjs in dependencies while replacing the ember-concurrency addon."
        ),
    ),
    "jquery": PackageMappingOutcome(
        legacy_name="jquery",
        strategy=ReplacementStrategy.REMOVE,
        target_packages=(),
        rationale=(
            "Direct DOM manipulation is prohibited in modern Angular OnPush architecture; "
            "state drives DOM."
        ),
    ),
    "ember-jquery": PackageMappingOutcome(
        legacy_name="ember-jquery",
        strategy=ReplacementStrategy.REMOVE,
        target_packages=(),
        rationale="Eliminate jQuery wrapper from modern Angular runtime.",
    ),
    "ember-qunit": PackageMappingOutcome(
        legacy_name="ember-qunit",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(PackageCoordinate(name="vitest", version_spec="^1.6.0", is_dev=True),),
        rationale="Fast in-memory unit testing with Vitest replacing browser-bound Testem/QUnit.",
    ),
    "qunit": PackageMappingOutcome(
        legacy_name="qunit",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(PackageCoordinate(name="vitest", version_spec="^1.6.0", is_dev=True),),
        rationale="Standardize on Vitest assertions and mock utilities.",
    ),
    "lodash": PackageMappingOutcome(
        legacy_name="lodash",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(PackageCoordinate(name="lodash-es", version_spec="^4.17.21"),),
        rationale="Tree-shakeable ES modules instead of CommonJS bundle overhead.",
    ),
    "ember-cli-sass": PackageMappingOutcome(
        legacy_name="ember-cli-sass",
        strategy=ReplacementStrategy.REPLACE,
        target_packages=(PackageCoordinate(name="sass", version_spec="^1.77.0", is_dev=True),),
        rationale="Modern Dart-Sass compiler for Angular component-scoped SCSS.",
    ),
    "ember-fetch": PackageMappingOutcome(
        legacy_name="ember-fetch",
        strategy=ReplacementStrategy.NATIVE,
        target_packages=(),
        rationale="Use Angular native provideHttpClient() with fetch API configuration.",
    ),
    "bower": PackageMappingOutcome(
        legacy_name="bower",
        strategy=ReplacementStrategy.REMOVE,
        target_packages=(),
        rationale="Bower is deprecated and obsolete; all packages resolved via npm.",
    ),
}

_CATEGORY_KEYWORDS: dict[str, LibraryCategory] = {
    "framework": LibraryCategory.FRAMEWORK,
    "ember-source": LibraryCategory.FRAMEWORK,
    "angular": LibraryCategory.FRAMEWORK,
    "react": LibraryCategory.FRAMEWORK,
    "vue": LibraryCategory.FRAMEWORK,
    "router": LibraryCategory.ROUTING,
    "routing": LibraryCategory.ROUTING,
    "data": LibraryCategory.DATA_LAYER,
    "store": LibraryCategory.DATA_LAYER,
    "concurrency": LibraryCategory.DATA_LAYER,
    "bootstrap": LibraryCategory.UI_STYLING,
    "sass": LibraryCategory.UI_STYLING,
    "css": LibraryCategory.UI_STYLING,
    "style": LibraryCategory.UI_STYLING,
    "font": LibraryCategory.UI_STYLING,
    "icon": LibraryCategory.UI_STYLING,
    "moment": LibraryCategory.UTILITY,
    "date": LibraryCategory.UTILITY,
    "lodash": LibraryCategory.UTILITY,
    "underscore": LibraryCategory.UTILITY,
    "jquery": LibraryCategory.UTILITY,
    "cli": LibraryCategory.BUILD_TOOL,
    "build": LibraryCategory.BUILD_TOOL,
    "webpack": LibraryCategory.BUILD_TOOL,
    "babel": LibraryCategory.BUILD_TOOL,
    "qunit": LibraryCategory.TEST_RUNNER,
    "test": LibraryCategory.TEST_RUNNER,
    "mocha": LibraryCategory.TEST_RUNNER,
    "jasmine": LibraryCategory.TEST_RUNNER,
    "karma": LibraryCategory.TEST_RUNNER,
    "jest": LibraryCategory.TEST_RUNNER,
    "vitest": LibraryCategory.TEST_RUNNER,
}


PACKAGE_MAPPINGS = _CURATED_MAPPINGS


def get_default_target_preset() -> TargetStackPreset:
    """Return the default production-tested modern target preset."""
    return ANGULAR_21_PRESET


def get_available_target_presets() -> tuple[TargetStackPreset, ...]:
    """Return all supported target architecture presets."""
    return _AVAILABLE_PRESETS


def get_target_preset(preset_id: str) -> TargetStackPreset | None:
    """Return target preset matching preset_id, or None."""
    for p in _AVAILABLE_PRESETS:
        if p.preset_id == preset_id:
            return p
    return None


def lookup_package_mapping(
    legacy_name: str, declared_version: str | None = None
) -> PackageMappingOutcome | None:
    """Lookup deterministic mapping outcome for a legacy package name.

    Returns:
        PackageMappingOutcome if a curated rule exists, else None.
    """
    normalized = legacy_name.strip().lower()
    return _CURATED_MAPPINGS.get(normalized)


def categorize_dependency(name: str, is_dev: bool = False) -> LibraryCategory:
    """Deterministically categorize a dependency by name and dev flag."""
    normalized = name.strip().lower()
    for keyword, cat in _CATEGORY_KEYWORDS.items():
        if keyword in normalized:
            return cat
    if is_dev:
        return LibraryCategory.BUILD_TOOL
    return LibraryCategory.OTHER
