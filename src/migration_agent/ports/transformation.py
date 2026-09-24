"""Application-owned ports for component transformation and code generation."""

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


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


class ComponentExtractorPort(Protocol):
    """Boundary for extracting component metadata from legacy frameworks."""

    def extract(
        self,
        component_source: str,
        template_source: str = "",
        style_source: str = "",
    ) -> IntermediateComponent:
        """Parse source files into an intermediate component representation."""


class ComponentRendererPort(Protocol):
    """Boundary for rendering modern target framework components."""

    def render_component_ts(self, component: IntermediateComponent) -> str:
        """Render modern TypeScript standalone component code."""

    def render_template_html(self, component: IntermediateComponent) -> str:
        """Render modern HTML template with native control flow."""

    def render_spec_ts(self, component: IntermediateComponent) -> str:
        """Render modern unit test spec."""
