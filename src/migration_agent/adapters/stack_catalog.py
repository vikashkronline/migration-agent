"""Deterministic catalog of modern presets, library categories, and package translation mappings."""

from migration_agent.domain.stack_catalog import (
    ANGULAR_17_LTS_PRESET,
    ANGULAR_21_PRESET,
    PACKAGE_MAPPINGS,
    categorize_dependency,
    get_available_target_presets,
    get_default_target_preset,
    get_target_preset,
    lookup_package_mapping,
)

__all__ = [
    "ANGULAR_17_LTS_PRESET",
    "ANGULAR_21_PRESET",
    "PACKAGE_MAPPINGS",
    "categorize_dependency",
    "get_available_target_presets",
    "get_default_target_preset",
    "get_target_preset",
    "lookup_package_mapping",
]
