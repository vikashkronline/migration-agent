"""Application-owned ports for agent runtimes."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain import AnalysisResult, MigrationStep, ProjectInventory


class AnalysisRequest(BaseModel):
    """Execution parameters for an analysis agent run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inventory: ProjectInventory
    provider: str = "gemini"
    model: str = Field(min_length=1)
    max_turns: int = Field(default=15, ge=1)
    max_tool_chars: int = Field(default=20_000, ge=100)
    dry_run: bool = True


class PlanningRequest(BaseModel):
    """Execution parameters for a migration planner agent run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    inventory: ProjectInventory
    analysis: AnalysisResult
    provider: str = "gemini"
    model: str = Field(min_length=1)
    max_turns: int = Field(default=10, ge=1)
    dry_run: bool = True


class FileReaderPort(Protocol):
    """Boundary for reading eligible repository text files."""

    def read_file(self, path: str) -> str:
        """Read the full text content of an eligible file by relative POSIX path."""


class AgentRuntimePort(Protocol):
    """Boundary for executing migration analysis and planning agents."""

    def analyze(
        self,
        request: AnalysisRequest,
        file_reader: FileReaderPort,
    ) -> AnalysisResult:
        """Run analysis on the given inventory and return a typed result."""

    def plan(
        self,
        request: PlanningRequest,
    ) -> list[MigrationStep]:
        """Generate candidate migration steps from analysis and inventory."""
