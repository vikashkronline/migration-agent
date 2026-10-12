"""Shared CLI/API composition and pinned runtime settings from verified configuration."""

import json
from pathlib import Path

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.configuration_store import ConfigurationRepository
from migration_agent.application.configuration import ConfigurationService, resolve_configuration
from migration_agent.config import Settings
from migration_agent.domain.configuration import (
    ConfigurationDiagnostic,
    LocalConfiguration,
    ProjectConfiguration,
)
from migration_agent.domain.execution import ValidationMode


class ConfigurationFacade:
    def __init__(self, authorization: ProjectAuthorization, settings: Settings) -> None:
        self.authorization = authorization
        self.repository = ConfigurationRepository(authorization, settings)
        self.service = ConfigurationService(self.repository, authorization, self.repository.access)

    def runtime_settings(self, *, model_operation: bool = False) -> Settings:
        self.authorization.require("project.read")
        if model_operation:
            self.authorization.require("provider.use")
        project = self.repository.project()
        local = self.repository.local()
        snapshot = resolve_configuration(project, local, self.repository.launcher())
        provider_fields = {"provider", "model", "profile_id", "max_turns"}
        errors = [
            d
            for d in snapshot.diagnostics
            if d.severity == "error" and (model_operation or d.field not in provider_fields)
        ]
        if errors:
            raise ValueError(
                "CONFIGURATION_BLOCKED: requested settings violate approved "
                "constraints; inspect agent config show."
            )
        values = {field.name: field.value for field in snapshot.fields}
        if model_operation and not values["model"]:
            if project.profiles:
                raise ValueError(
                    "CONFIGURATION_PROFILE_SELECTION_REQUIRED: choose an approved "
                    "personal runtime profile."
                )
            raise ValueError(
                "CONFIGURATION_OWNER_SETUP_REQUIRED: activate an approved runtime "
                "profile before provider use."
            )
        updates: dict[str, object] = {}
        if model_operation or values["browser_provider_export"]:
            self.authorization.require("provider.use")
        if values["browser_provider_export"]:
            profile = next(
                (p for p in project.profiles if p.profile_id == values["profile_id"]), None
            )
            if not profile or "browser_review" not in profile.allowed_payloads:
                raise ValueError(
                    "CONFIGURATION_DISCLOSURE_REQUIRED: browser export requires an "
                    "approved browser review profile."
                )
        if values["provider"]:
            updates["runtime_provider"] = values["provider"]
            updates["runtime_model"] = values["model"]
        # Preserve separately consented legacy execution settings until typed adoption.
        legacy = self.repository._project_text()
        if legacy is not None and json.loads(legacy) != {"version": 1, "workflows": {}}:
            updates.update(
                validation_mode=ValidationMode(str(values["validation_mode"])),
                max_step_files=values["max_step_files"],
                browser_provider_export=values["browser_provider_export"],
            )
        for name in (
            "final_target_root",
            "native_toolchain_root",
            "native_dependencies_root",
            "native_browser_path",
            "browser_validation_plan",
        ):
            if values[name]:
                updates[name] = Path(str(values[name]))
        if values["validation_image"]:
            updates["validation_image"] = values["validation_image"]
        return self.repository.settings.model_copy(update=updates)

    def offline_checks(
        self, project: ProjectConfiguration, local: LocalConfiguration
    ) -> tuple[ConfigurationDiagnostic, ...]:
        snapshot = resolve_configuration(project, local, self.repository.launcher())
        values = {field.name: field.value for field in snapshot.fields}
        effective_local = LocalConfiguration.model_validate_json(
            json.dumps(
                {
                    **local.model_dump(mode="json"),
                    **{
                        name: value
                        for name, value in values.items()
                        if name in LocalConfiguration.model_fields and name != "schema_version"
                    },
                }
            )
        )
        diagnostics = list(self.repository.diagnostics(project, effective_local))
        mode = str(values["validation_mode"])
        if mode == "restricted":
            diagnostics.append(
                ConfigurationDiagnostic(
                    field="validation_mode",
                    code="EXECUTION_BACKEND_REQUIRED",
                    severity="prerequisite",
                    message=(
                        "Restricted mode supports inspection; real validation needs an "
                        "approved backend and its prerequisites."
                    ),
                )
            )
        if mode == "native":
            for name in ("native_toolchain_root", "native_dependencies_root"):
                if not values[name]:
                    diagnostics.append(
                        ConfigurationDiagnostic(
                            field=name,
                            code="EXTERNAL_PREREQUISITE_REQUIRED",
                            severity="prerequisite",
                            message="Native validation needs this installed external prerequisite.",
                        )
                    )
            diagnostics.append(
                ConfigurationDiagnostic(
                    field="validation_mode",
                    code="EXECUTION_CONSENT_REQUIRED",
                    severity="prerequisite",
                    message=(
                        "Each actual native validation step still requires its exact "
                        "human execution consent."
                    ),
                )
            )
        if not values["browser_validation_plan"]:
            diagnostics.append(
                ConfigurationDiagnostic(
                    field="browser_validation_plan",
                    code="BROWSER_COVERAGE_REQUIRED",
                    severity="prerequisite",
                    message=(
                        "Applicable browser validation requires a coverage plan and real evidence."
                    ),
                )
            )
        return (*snapshot.diagnostics, *diagnostics)


def configured_settings(
    source: Path, settings: Settings, *, model_operation: bool = False
) -> Settings:
    authorization = ProjectAuthorization(source, settings)
    decision = authorization.require("project.read")
    if not decision.access_digest:
        if model_operation:
            authorization.require("provider.use")
        return settings
    return ConfigurationFacade(authorization, settings).runtime_settings(
        model_operation=model_operation
    )
