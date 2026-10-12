"""Typed non-secret configuration, constraints and effective-value provenance."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.execution import ValidationMode
from migration_agent.domain.redaction import RedactionPolicy


def unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("CONFIGURATION_DUPLICATE_KEY: duplicate JSON keys are forbidden.")
        result[name] = value
    return result


class ConfigurationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def public_values(self) -> Self:
        if RedactionPolicy().contains_secret(self.model_dump_json()):
            raise ValueError(
                "CONFIGURATION_SECRET_REJECTED: only public configuration is accepted."
            )
        return self


class RuntimeProfile(ConfigurationModel):
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    provider: Literal["gemini", "openai"]
    models: tuple[str, ...] = Field(min_length=1, max_length=32)
    default_model: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
    allowed_payloads: tuple[
        Literal["connectivity", "source_analysis", "planning", "contextual_qa", "browser_review"],
        ...,
    ] = ("connectivity",)

    @model_validator(mode="after")
    def supported_model_names(self) -> Self:
        import re

        if len(set(self.models)) != len(self.models) or self.default_model not in self.models:
            raise ValueError(
                "CONFIGURATION_MODEL_INVALID: unique models and an included default are required."
            )
        if not self.allowed_payloads or len(set(self.allowed_payloads)) != len(
            self.allowed_payloads
        ):
            raise ValueError(
                "CONFIGURATION_DISCLOSURE_INVALID: unique explicit payload purposes are required."
            )
        if any(
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model) or "://" in model
            for model in self.models
        ):
            raise ValueError("CONFIGURATION_MODEL_INVALID: model identifiers cannot be endpoints.")
        return self

    @property
    def endpoint(self) -> str:
        return (
            "https://generativelanguage.googleapis.com"
            if self.provider == "gemini"
            else "https://api.openai.com/v1"
        )


class ProjectConfiguration(ConfigurationModel):
    schema_version: Literal[1] = 1
    profiles: tuple[RuntimeProfile, ...] = Field(default=(), max_length=16)
    default_profile: str | None = Field(default=None, max_length=64)
    max_turns: int = Field(default=10, ge=1, le=30)
    max_step_files: int = Field(default=10, ge=1, le=100)
    allowed_validation_modes: tuple[ValidationMode, ...] = (ValidationMode.RESTRICTED,)
    browser_provider_export: bool = False
    target_preset_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len(self.model_dump_json().encode()) > 50000:
            raise ValueError(
                "CONFIGURATION_TOO_LARGE: shared settings exceed the public record budget."
            )
        identifiers = {p.profile_id for p in self.profiles}
        if len(identifiers) != len(self.profiles) or (
            self.default_profile is not None and self.default_profile not in identifiers
        ):
            raise ValueError(
                "CONFIGURATION_PROFILE_INVALID: unique profiles and a valid default are required."
            )
        if not self.allowed_validation_modes or len(set(self.allowed_validation_modes)) != len(
            self.allowed_validation_modes
        ):
            raise ValueError(
                "CONFIGURATION_MODE_INVALID: unique allowed validation modes are required."
            )
        return self

    @property
    def digest(self) -> str:
        return compute_canonical_digest(self)


class LocalConfiguration(ConfigurationModel):
    schema_version: Literal[1] = 1
    profile_id: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=128)
    max_turns: int | None = Field(default=None, ge=1, le=30)
    validation_mode: ValidationMode | None = None
    native_toolchain_root: str | None = Field(default=None, max_length=1024)
    native_dependencies_root: str | None = Field(default=None, max_length=1024)
    native_browser_path: str | None = Field(default=None, max_length=1024)
    browser_validation_plan: str | None = Field(default=None, max_length=1024)
    validation_image: str | None = Field(default=None, max_length=256)
    final_target_root: str | None = Field(default=None, max_length=1024)
    next_state_dir: str | None = Field(default=None, max_length=1024)
    next_staging_root: str | None = Field(default=None, max_length=1024)

    @property
    def digest(self) -> str:
        return compute_canonical_digest(self)


class ConfigurationDiagnostic(ConfigurationModel):
    field: str
    code: str
    severity: Literal["error", "prerequisite", "warning", "info"]
    message: str
    action: str = ""


class EffectiveField(ConfigurationModel):
    name: str
    value: str | int | bool | None
    origin: Literal["platform", "project", "local", "launcher"]
    scope: Literal["project", "workstation", "session"]
    update_mode: Literal["next_operation", "restart", "binding_read_only"] = "next_operation"


class ConfigurationSnapshot(ConfigurationModel):
    project_digest: str
    local_digest: str
    fields: tuple[EffectiveField, ...]
    diagnostics: tuple[ConfigurationDiagnostic, ...] = ()

    @property
    def digest(self) -> str:
        return compute_canonical_digest(self)


class ConfigurationFieldDescriptor(ConfigurationModel):
    name: str
    label: str
    section: str
    scope: Literal["project", "local", "binding"]
    kind: Literal["profiles", "text", "number", "boolean", "modes", "mode", "path", "readonly"]
    help: str
    minimum: int | None = None
    maximum: int | None = None
    options: tuple[str, ...] = ()


class ConfigurationRequest(ConfigurationModel):
    expected_revision: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ProjectConfigurationRequest(ConfigurationRequest):
    configuration: ProjectConfiguration


class LocalConfigurationRequest(ConfigurationRequest):
    configuration: LocalConfiguration


class ConfigurationProposal(ConfigurationModel):
    proposal_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    project_id: str
    principal_id: str
    base_access_digest: str
    base_file_digest: str | None
    configuration: ProjectConfiguration
    source_revision: str
    created_at: str
    request_id: str

    @property
    def digest(self) -> str:
        return compute_canonical_digest(self)


class ConfigurationView(ConfigurationModel):
    project_id: str
    revision: str
    access_digest: str
    principal_id: str
    capabilities: tuple[str, ...]
    is_owner: bool
    project: ProjectConfiguration
    local: LocalConfiguration
    effective: ConfigurationSnapshot
    bindings: dict[str, str]
    field_descriptors: tuple[ConfigurationFieldDescriptor, ...]
    restart_arguments: tuple[str, ...] = ()


class ConfigurationReceipt(ConfigurationModel):
    request_id: str
    status: str
    revision: str
    proposal_id: str | None = None
    message: str
    access_digest: str = ""


class ConfigurationReview(ConfigurationModel):
    proposal: ConfigurationProposal
    active: ProjectConfiguration
    diagnostics: tuple[ConfigurationDiagnostic, ...]
    impact: tuple[str, ...]
    signing_digest: str | None = None
    access_proposal_id: str | None = None
    review_command: tuple[str, ...] = ()


class CheckKind(StrEnum):
    OFFLINE = "offline"
    TOOLCHAIN = "toolchain"
    PROVIDER = "provider"


class ConfigurationCheckRequest(ConfigurationRequest):
    kind: CheckKind = CheckKind.OFFLINE
    configuration: LocalConfiguration
    project_configuration: ProjectConfiguration | None = None


class LauncherConfiguration(ConfigurationModel):
    provider: str | None = None
    model: str | None = None
    max_turns: int | None = None
    max_step_files: int | None = None
    validation_mode: ValidationMode | None = None
    browser_provider_export: bool | None = None
    paths: dict[str, str] = Field(default_factory=dict)


class ConfigurationCheckResult(ConfigurationModel):
    operation_id: str
    status: str
    request_id: str
    principal_id: str
    access_digest: str
    input_revision: str
    diagnostics: tuple[ConfigurationDiagnostic, ...] = ()


class ConfigurationSetupRequest(ConfigurationModel):
    source_root: str = Field(min_length=1, max_length=1024)
    governance_root: str = Field(min_length=1, max_length=1024)
    state_dir: str = Field(min_length=1, max_length=1024)
    staging_root: str = Field(min_length=1, max_length=1024)
    project_name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ConfigurationSetupPlan(ConfigurationModel):
    request: ConfigurationSetupRequest
    command_arguments: tuple[str, ...]
    message: str
