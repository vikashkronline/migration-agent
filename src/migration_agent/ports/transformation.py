"""Application-owned ports for component transformation and code generation."""

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.frameworks import SourceComponentBundle


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
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ComponentExtractorPort(Protocol):
    """Boundary for extracting component metadata from legacy frameworks."""

    def extract(
        self,
        component_source: str,
        template_source: str = "",
        style_source: str = "",
    ) -> IntermediateComponent:
        """Parse source files into an intermediate component representation."""

    def discover_components(self, source_root: Path) -> tuple[SourceComponentBundle, ...]:
        """Discover component source bundles in the repository eligible for extraction."""


@runtime_checkable
class ComponentRendererPort(Protocol):
    """Boundary for rendering modern target framework components."""

    def render_component_ts(self, component: IntermediateComponent) -> str:
        """Render modern TypeScript standalone component code."""

    def render_template_html(self, component: IntermediateComponent) -> str:
        """Render modern HTML template with native control flow."""

    def render_style_scss(self, component: IntermediateComponent) -> str:
        """Render component-scoped modern SCSS stylesheet."""

    def render_spec_ts(self, component: IntermediateComponent) -> str:
        """Render modern unit test spec."""
