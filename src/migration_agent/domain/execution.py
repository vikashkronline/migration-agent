"""Execution trust and immutable validation evidence, independent of host frameworks."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import DestinationBinding
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.validation import ValidationProfile


class ValidationMode(StrEnum):
    RESTRICTED = "restricted"
    NATIVE = "native"
    CONTAINER = "container"


class ExecutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ValidationSetupDiagnostics(ExecutionModel):
    """Configuration prerequisites, not proof of successful execution or validation."""

    mode: ValidationMode
    native_toolchain_configured: bool
    native_dependencies_configured: bool
    container_image_configured: bool
    native_consent_required: Literal[True] = True
    native_is_security_sandbox: Literal[False] = False
    native_platform_supported: bool
    repository_code_executed: Literal[False] = False
    missing_prerequisites: tuple[str, ...]
    browser_ui_ux_required: Literal[True] = True
    browser_plan_configured: bool
    browser_review_mode: Literal["host", "provider"]
    browser_provider_export_enabled: bool


class BrowserProviderDisclosure(ExecutionModel):
    provider: Literal["openai", "gemini"]
    model: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
    endpoint: Literal["https://api.openai.com/v1", "https://generativelanguage.googleapis.com"]
    payload: Literal["browser-visual-v1"] = "browser-visual-v1"
    max_cases: Literal[64] = 64
    max_image_bytes_per_case: Literal[10485760] = 10485760
    max_metadata_bytes_per_case: Literal[131072] = 131072
    max_output_tokens_per_case: Literal[8192] = 8192
    timeout_seconds_per_case: Literal[30] = 30

    @model_validator(mode="after")
    def fixed_destination(self) -> "BrowserProviderDisclosure":
        if "://" in self.model:
            raise ValueError(
                "BROWSER_PROVIDER_CONFIGURATION_INVALID: a model identifier is required."
            )
        expected = (
            "https://api.openai.com/v1"
            if self.provider == "openai"
            else "https://generativelanguage.googleapis.com"
        )
        if self.endpoint != expected:
            raise ValueError("BROWSER_PROVIDER_DESTINATION_INVALID: provider endpoint mismatch.")
        return self


class ExecutionPolicy(ExecutionModel):
    mode: ValidationMode
    project_policy_digest: str
    minimum_assurance: AssuranceLevel = AssuranceLevel.MODE_B
    network: Literal["host", "none"]
    filesystem: Literal["host", "container"]
    output_directories: tuple[str, ...] = (".angular", "coverage", "dist")
    catalog_version: Literal["node-v1", "node-vitest-v1", "node-angular-v21"] = "node-v1"
    environment_policy: Literal["positive-fresh-home-v1", "container-minimal-v1"] = (
        "positive-fresh-home-v1"
    )
    timeout_seconds: Literal[60] = 60
    max_output_bytes: Literal[65536] = 65536
    process_limit: int | None = None
    memory_bytes: int | None = None
    cpu_seconds: int | None = None
    cpu_count: float | None = None
    supervision: str
    browser_plan_digest: str | None = None
    browser_catalog: Literal["browser-v1"] | None = None
    browser_worker_digest: str | None = None
    browser_provider_disclosure: BrowserProviderDisclosure | None = None
    browser_environment_policy: (
        Literal[
            "windows-known-folders-fresh-browser-v1",
            "positive-fresh-home-v1",
            "container-minimal-v1",
        ]
        | None
    ) = None

    @property
    def digest(self) -> str:
        return compute_canonical_digest(self.model_dump(mode="json"))

    @model_serializer(mode="wrap")
    def compatible_serialization(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = cast(dict[str, Any], handler(self))
        for key in (
            "browser_plan_digest",
            "browser_catalog",
            "browser_worker_digest",
            "browser_provider_disclosure",
            "browser_environment_policy",
        ):
            if data.get(key) is None:
                data.pop(key, None)
        return data


class ToolIdentity(ExecutionModel):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExecutionProvenance(ExecutionModel):
    backend: ValidationMode
    policy: ExecutionPolicy
    policy_digest: str
    consent_id: str | None = None
    toolchain: tuple[ToolIdentity, ...] = ()
    dependency_digest: str = ""
    input_digest: str
    cleanup_verified: bool = False

    @model_validator(mode="after")
    def bound_policy(self) -> "ExecutionProvenance":
        if self.policy.mode != self.backend or self.policy.digest != self.policy_digest:
            raise ValueError("EXECUTION_POLICY_INVALID: backend and policy must match.")
        if self.backend == ValidationMode.NATIVE and not self.consent_id:
            raise ValueError("NATIVE_CONSENT_REQUIRED: native evidence requires consent.")
        return self


class NativeExecutionConsent(ExecutionModel):
    schema_version: Literal[1] = 1
    consent_id: str
    project_id: str
    source_root: str
    root_commit: str
    base_revision: str
    worktree_fingerprint: str
    plan_id: str
    step_id: str
    initial_changeset_id: str
    policy_digest: str
    profiles: tuple[ValidationProfile, ...] = Field(min_length=1)
    toolchain: tuple[ToolIdentity, ...] = Field(min_length=1)
    dependency_digest: str
    immutable_input_digest: str
    approved_scope: tuple[str, ...] = Field(min_length=1)
    repair_budget: int = Field(default=0, ge=0, le=10)
    actor: str
    principal_id: str | None = None
    access_digest: str | None = None
    assurance_level: AssuranceLevel
    key_fingerprint: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    signature: str = ""
    destination: DestinationBinding | None = None

    @model_validator(mode="after")
    def lifetime(self) -> "NativeExecutionConsent":
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("CONSENT_EXPIRY_INVALID: timestamps require an explicit timezone.")
        if not 0 < (self.expires_at - self.created_at).total_seconds() <= 3600:
            raise ValueError("CONSENT_EXPIRY_INVALID: lifetime must be at most one hour.")
        if self.assurance_level == AssuranceLevel.MODE_C:
            raise ValueError("ASSURANCE_REQUIRED: execution consent requires Mode B or A.")
        return self

    @property
    def signing_digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"signature"})
        if self.destination is None:
            payload.pop("destination", None)
        return compute_canonical_digest(payload)
