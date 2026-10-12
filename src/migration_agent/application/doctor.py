"""System setup and diagnostic collection application service."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

from migration_agent.config import Settings
from migration_agent.domain.execution import ValidationMode, ValidationSetupDiagnostics

_MINIMUM_PYTHON = (3, 12)
_RUNTIME_DISTRIBUTIONS = (
    "google-genai",
    "mcp",
    "openai-agents",
    "pydantic",
    "pydantic-settings",
    "typer",
)


def _installed_runtime_versions() -> dict[str, str | None]:
    installed: dict[str, str | None] = {}
    for distribution in _RUNTIME_DISTRIBUTIONS:
        try:
            installed[distribution] = version(distribution)
        except PackageNotFoundError:
            installed[distribution] = None
    return installed


def validation_setup_diagnostics(configured_settings: Settings) -> ValidationSetupDiagnostics:
    """Inspect configuration presence without running tools or repository scripts."""
    mode = configured_settings.effective_validation_mode
    missing: list[str] = []
    if mode == ValidationMode.RESTRICTED:
        missing.append("execution_backend_selection")
    elif mode == ValidationMode.NATIVE:
        if (
            configured_settings.native_toolchain_root is None
            or not configured_settings.native_toolchain_root.is_dir()
        ):
            missing.append("external_native_toolchain")
        if (
            configured_settings.native_dependencies_root is None
            or not configured_settings.native_dependencies_root.is_dir()
        ):
            missing.append("external_offline_dependencies")
        if sys.platform not in {"win32", "linux"}:
            missing.append("supported_native_process_supervision")
        missing.append("per_step_human_execution_consent")
    elif mode == ValidationMode.CONTAINER and not configured_settings.validation_image:
        missing.append("locally_installed_pinned_image")
    if (
        configured_settings.browser_validation_plan is None
        or not configured_settings.browser_validation_plan.is_file()
    ):
        missing.append("browser_validation_plan")

    return ValidationSetupDiagnostics(
        mode=mode,
        native_toolchain_configured=configured_settings.native_toolchain_root is not None,
        native_dependencies_configured=configured_settings.native_dependencies_root is not None,
        container_image_configured=bool(configured_settings.validation_image),
        native_platform_supported=sys.platform in {"win32", "linux"},
        missing_prerequisites=tuple(missing),
        browser_plan_configured=configured_settings.browser_validation_plan is not None,
        browser_review_mode=configured_settings.browser_review_mode,
        browser_provider_export_enabled=configured_settings.browser_provider_export,
    )


def collect_diagnostics(
    *,
    python_version: tuple[int, int, int] | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    """Return diagnostics without reading secrets or contacting external services."""
    actual_python = python_version or (
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    )
    configured_settings = settings or Settings()
    runtime_versions = _installed_runtime_versions()
    python_ok = actual_python[:2] >= _MINIMUM_PYTHON
    dependencies_ok = all(value is not None for value in runtime_versions.values())
    overall_ok = python_ok and dependencies_ok

    return {
        "checks": [
            {
                "details": {
                    "actual": ".".join(str(part) for part in actual_python),
                    "minimum": ".".join(str(part) for part in _MINIMUM_PYTHON),
                },
                "name": "python",
                "status": "pass" if python_ok else "fail",
            },
            {
                "details": runtime_versions,
                "name": "runtime_dependencies",
                "status": "pass" if dependencies_ok else "fail",
            },
            {
                "details": validation_setup_diagnostics(configured_settings).model_dump(
                    mode="json"
                ),
                "name": "validation_backend",
                "status": "pass",
            },
            {
                "details": {
                    "configured": bool(
                        configured_settings.effective_model
                        and configured_settings.effective_model.strip()
                    ),
                    "required_for_doctor": False,
                },
                "name": "model_configuration",
                "status": "pass",
            },
        ],
        "schema_version": 1,
        "status": "ok" if overall_ok else "error",
    }
