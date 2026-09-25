"""Ports for specialized migration subagent runtimes."""

from typing import Protocol, runtime_checkable

from migration_agent.domain import (
    InventoryInterpretation,
    InventoryInterpretationRequest,
    MigrationAnalysisOutput,
    MigrationAnalystRequest,
    PlanCriticRequest,
    PlanCritique,
    RepairDiagnosis,
    RepairDiagnosticianRequest,
)
from migration_agent.ports.agent_runtime import FileReaderPort


@runtime_checkable
class SpecialistRuntimePort(Protocol):
    """Execution boundary for specialized subagent personas."""

    def interpret_inventory(
        self,
        request: InventoryInterpretationRequest,
    ) -> InventoryInterpretation:
        """Synthesize high-level domain insights and framework notes from repository inventory."""

    def analyze_migration(
        self,
        request: MigrationAnalystRequest,
        file_reader: FileReaderPort,
    ) -> MigrationAnalysisOutput:
        """Perform deep code-level migration analysis against eligible repository files."""

    def criticize_plan(
        self,
        request: PlanCriticRequest,
    ) -> PlanCritique:
        """Audit candidate migration plan for risk, missing dependencies, and quality issues."""

    def diagnose_repair(
        self,
        request: RepairDiagnosticianRequest,
    ) -> RepairDiagnosis:
        """Diagnose validation command failure and propose targeted, in-scope repair guidance."""
