"""Unit tests for stack catalog, presets, and domain models."""

import pytest

from migration_agent.adapters.stack_catalog import (
    ANGULAR_17_LTS_PRESET,
    categorize_dependency,
    get_available_target_presets,
    get_default_target_preset,
    lookup_package_mapping,
)
from migration_agent.domain.stack import (
    LibraryCategory,
    ReplacementStrategy,
    StackRecommendationDraft,
    compute_draft_digest,
)


def test_default_target_preset() -> None:
    preset = get_default_target_preset()
    assert preset.preset_id == "angular-21-bootstrap5"
    assert preset.angular_version == "21.2.25"
    assert preset.typescript_version == "~5.9.3"
    assert preset.rxjs_version == "~7.8.1"
    assert "src/app/core" in preset.directory_structure

    # Verify base dependencies
    dep_names = {dep.name for dep in preset.base_dependencies}
    assert "@angular/core" in dep_names
    assert "@angular/common" in dep_names
    assert "bootstrap" in dep_names
    assert "rxjs" in dep_names

    # Verify dev dependencies
    dev_names = {dep.name for dep in preset.base_dev_dependencies}
    assert "@angular/cli" in dev_names
    assert "typescript" in dev_names
    assert "vitest" in dev_names


def test_available_target_presets() -> None:
    presets = get_available_target_presets()
    assert len(presets) >= 1
    assert ANGULAR_17_LTS_PRESET in presets


def test_lookup_package_mapping_ember_source() -> None:
    outcome = lookup_package_mapping("ember-source")
    assert outcome is not None
    assert outcome.strategy == ReplacementStrategy.REPLACE
    assert any(pkg.name == "@angular/core" for pkg in outcome.target_packages)
    assert any(pkg.name == "@angular/common" for pkg in outcome.target_packages)


def test_lookup_package_mapping_ember_concurrency() -> None:
    outcome = lookup_package_mapping("ember-concurrency")
    assert outcome is not None
    assert outcome.strategy == ReplacementStrategy.NATIVE
    assert any(pkg.name == "rxjs" for pkg in outcome.target_packages)
    assert outcome.behavioral_notes is not None


def test_lookup_package_mapping_jquery() -> None:
    outcome = lookup_package_mapping("jquery")
    assert outcome is not None
    assert outcome.strategy == ReplacementStrategy.REMOVE
    assert len(outcome.target_packages) == 0


def test_lookup_package_mapping_ember_data() -> None:
    outcome = lookup_package_mapping("ember-data")
    assert outcome is not None
    assert outcome.strategy == ReplacementStrategy.CUSTOM
    assert len(outcome.target_packages) == 0


def test_lookup_package_mapping_bootstrap_sassy() -> None:
    outcome = lookup_package_mapping("ember-cli-bootstrap-sassy")
    assert outcome is not None
    assert outcome.strategy == ReplacementStrategy.REPLACE
    assert any(
        pkg.name == "bootstrap" and pkg.version_spec == "^5.3.3" for pkg in outcome.target_packages
    )


def test_lookup_package_mapping_moment() -> None:
    outcome = lookup_package_mapping("moment")
    assert outcome is not None
    assert outcome.strategy == ReplacementStrategy.REPLACE
    assert any(pkg.name == "date-fns" for pkg in outcome.target_packages)


def test_lookup_package_mapping_unknown() -> None:
    assert lookup_package_mapping("obscure-custom-legacy-lib") is None


@pytest.mark.parametrize(
    ("name", "is_dev", "expected"),
    [
        ("ember-source", False, LibraryCategory.FRAMEWORK),
        ("ember-data", False, LibraryCategory.DATA_LAYER),
        ("ember-cli-bootstrap-sassy", False, LibraryCategory.UI_STYLING),
        ("ember-cli", True, LibraryCategory.BUILD_TOOL),
        ("ember-qunit", True, LibraryCategory.TEST_RUNNER),
        ("moment", False, LibraryCategory.UTILITY),
        ("custom-tool", True, LibraryCategory.BUILD_TOOL),
        ("random-package", False, LibraryCategory.OTHER),
    ],
)
def test_categorize_dependency(name: str, is_dev: bool, expected: LibraryCategory) -> None:
    assert categorize_dependency(name, is_dev=is_dev) == expected


def test_compute_draft_digest_deterministic() -> None:
    preset = get_default_target_preset()
    mapping = lookup_package_mapping("ember-source")
    assert mapping is not None

    draft1 = StackRecommendationDraft(
        draft_id="draft-001",
        project_id="test-project",
        source_revision="rev-abc1",
        governance_revision="gov-xyz1",
        preset=preset,
        mappings=(mapping,),
        unmapped_count=0,
        created_at="2026-10-10T00:00:00Z",
        updated_at="2026-10-10T00:00:00Z",
        content_digest="",
    )
    digest1 = compute_draft_digest(draft1)
    digest2 = compute_draft_digest(draft1)

    assert digest1.startswith("sha256:")
    assert digest1 == digest2

    # Mutating a field must change digest
    draft2 = StackRecommendationDraft(
        draft_id="draft-001",
        project_id="test-project",
        source_revision="rev-abc1",
        governance_revision="gov-xyz1",
        preset=preset,
        mappings=(),
        unmapped_count=1,
        created_at="2026-10-10T00:00:00Z",
        updated_at="2026-10-10T00:00:00Z",
        content_digest="",
    )
    assert compute_draft_digest(draft2) != digest1
