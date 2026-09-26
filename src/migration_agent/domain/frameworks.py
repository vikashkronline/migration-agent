"""Framework capabilities, component bundles, and pair negotiation domain models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.validation import ValidationProfile


class FrameworkCapability(StrEnum):
    """Core capabilities that framework adapters can negotiate and advertise."""

    INVENTORY = "inventory"
    VALIDATION = "validation"
    SOURCE_TRANSFORMATION = "source_transformation"
    TARGET_TRANSFORMATION = "target_transformation"


class FrameworkCapabilities(BaseModel):
    """Declared capabilities and profile bounds for a framework adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supports_inventory: bool = True
    supports_validation: bool = False
    supports_source_transformation: bool = False
    supports_target_transformation: bool = False
    supported_validation_profiles: tuple[ValidationProfile, ...] = Field(default_factory=tuple)
    supported_target_frameworks: tuple[str, ...] = Field(default_factory=tuple)

    def has_capability(self, capability: FrameworkCapability) -> bool:
        """Check whether the adapter supports a specific capability."""
        if capability == FrameworkCapability.INVENTORY:
            return self.supports_inventory
        if capability == FrameworkCapability.VALIDATION:
            return self.supports_validation
        if capability == FrameworkCapability.SOURCE_TRANSFORMATION:
            return self.supports_source_transformation
        if capability == FrameworkCapability.TARGET_TRANSFORMATION:
            return self.supports_target_transformation
        return False


class SourceComponentBundle(BaseModel):
    """A discovered legacy component bundle eligible for intermediate extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    component_name: str = Field(min_length=1)
    source_files: tuple[str, ...] = Field(default_factory=tuple)
    component_source: str = Field(default="")
    template_source: str = Field(default="")
    style_source: str = Field(default="")


class ServiceMethod(BaseModel):
    """A remote or business method exposed by a shared service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    http_method: str = Field(default="GET")
    endpoint: str = Field(default="")
    parameters: tuple[str, ...] = Field(default_factory=tuple)
    return_type: str = Field(default="Observable<any>")


class SourceServiceBundle(BaseModel):
    """A discovered legacy service bundle eligible for extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_name: str = Field(min_length=1)
    source_files: tuple[str, ...] = Field(default_factory=tuple)
    service_source: str = Field(default="")


class IntermediateService(BaseModel):
    """Framework-neutral intermediate representation of a shared business/API service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    methods: tuple[ServiceMethod, ...] = Field(default_factory=tuple)
    metadata: dict[str, object] = Field(default_factory=dict)


class NegotiationResult(BaseModel):
    """Result of negotiating an end-to-end migration pair between source and target frameworks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supported: bool
    source_framework: str
    target_framework: str
    validation_commands_available: bool = False
    reason: str | None = None
