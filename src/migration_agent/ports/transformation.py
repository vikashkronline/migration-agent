"""Application-owned ports for component transformation and code generation."""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.frameworks import (
    IntermediateService,
    SourceComponentBundle,
    SourceServiceBundle,
)


class IntermediateComponent(BaseModel):
    """Framework-neutral intermediate representation of a UI component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)  # e.g. "UserCard"
    tag_name: str = Field(min_length=1)  # e.g. "app-user-card"
    # Component inputs (e.g. "user", "title")
    inputs: tuple[str, ...] = Field(default_factory=tuple)
    # Local reactive state (e.g. "isExpanded")
    state_properties: tuple[str, ...] = Field(default_factory=tuple)
    # Action methods (e.g. "toggleExpanded")
    methods: tuple[str, ...] = Field(default_factory=tuple)
    template_raw: str = Field(default="")
    style_raw: str = Field(default="")
    injected_services: tuple[str, ...] = Field(default_factory=tuple)
    outputs: tuple[str, ...] = Field(default_factory=tuple)
    input_types: dict[str, str] = Field(default_factory=dict)
    state_types: dict[str, str] = Field(default_factory=dict)
    state_defaults: dict[str, str] = Field(default_factory=dict)
    method_bodies: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ComponentExtractorPort(Protocol):
    """Boundary for extracting component metadata from legacy frameworks."""

    def extract(
        self,
        component_source: str,
        template_source: str = "",
        style_source: str = "",
        *,
        component_name: str | None = None,
    ) -> IntermediateComponent:
        """Parse source files into an intermediate component representation."""

    def discover_components(self, source_root: Path) -> tuple[SourceComponentBundle, ...]:
        """Discover component source bundles in the repository eligible for extraction."""


@runtime_checkable
class ComponentRendererPort(Protocol):
    """Boundary for rendering modern target framework components."""

    def output_paths(self, name: str, namespace: str) -> tuple[str, str, str, str]:
        """Return exact target identities in TypeScript/template/style/spec order."""

    def render_component_ts(self, component: IntermediateComponent) -> str:
        """Render modern TypeScript standalone component code."""

    def render_template_html(self, component: IntermediateComponent) -> str:
        """Render modern HTML template with native control flow."""

    def render_style_scss(self, component: IntermediateComponent) -> str:
        """Render component-scoped modern SCSS stylesheet."""

    def render_spec_ts(self, component: IntermediateComponent) -> str:
        """Render modern unit test spec."""


@runtime_checkable
class ServiceExtractorPort(Protocol):
    """Boundary for extracting service/API client metadata from legacy frameworks."""

    def extract_service(self, service_source: str) -> IntermediateService:
        """Parse service source code into an IntermediateService representation."""

    def discover_services(self, source_root: Path) -> tuple[SourceServiceBundle, ...]:
        """Discover service source files in the repository."""


@runtime_checkable
class ServiceRendererPort(Protocol):
    """Boundary for rendering modern target framework services."""

    def output_paths(self, name: str) -> tuple[str, str]:
        """Return exact implementation/spec target identities."""

    def render_service_ts(self, service: IntermediateService) -> str:
        """Render modern Angular injectable service with inject(HttpClient)."""

    def render_spec_ts(self, service: IntermediateService) -> str:
        """Render service unit test spec with HttpTestingController."""


@runtime_checkable
class FoundationTransformationPort(Protocol):
    """Boundary for rendering modern target foundation manifests and workspace scaffolding."""

    def render_foundation_files(
        self,
        project_name: str,
        preset: Any = None,
        draft: Any = None,
    ) -> dict[str, str]:
        """Generate root workspace manifests and bootstrap template files."""
