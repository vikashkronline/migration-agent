"""Application services that coordinate domain models and ports."""

from migration_agent.application.adoption import AdoptionReport, ProjectAdoptionService
from migration_agent.application.analysis import AnalysisService, SnapshotFileReader
from migration_agent.application.control_service import ControlApiService
from migration_agent.application.diagnostics import (
    DiagnosticCategory,
    StructuredDiagnostic,
    parse_diagnostics,
)
from migration_agent.application.evaluation import EvaluationService
from migration_agent.application.fullstack_service import (
    CrossDomainLinker,
    FullStackDiscoveryService,
)
from migration_agent.application.inventory import InventoryService
from migration_agent.application.knowledge import KnowledgeService
from migration_agent.application.orchestration import ResumableExecutionService
from migration_agent.application.planning import PlanningService
from migration_agent.application.qa import ContextualQAService
from migration_agent.application.repair_strategies import (
    AutoImportRepairStrategy,
    DeterministicRepairEngine,
    RepairStrategy,
    SignalCallRepairStrategy,
    SpecTestBedRepairStrategy,
    SyntaxLintRepairStrategy,
)
from migration_agent.application.specialists import (
    DeterministicPlanCriticAggregator,
    DeterministicRepairDiagnosticianAggregator,
    SpecialistCoordinator,
)
from migration_agent.application.transformation import TransformationService
from migration_agent.application.validation import (
    BoundedRepairService,
    ReportService,
    ValidationService,
)
from migration_agent.application.validator import PlanValidationResult, RuleBasedPlanValidator

__all__ = [
    "AdoptionReport",
    "AnalysisService",
    "AutoImportRepairStrategy",
    "BoundedRepairService",
    "ContextualQAService",
    "ControlApiService",
    "CrossDomainLinker",
    "DeterministicPlanCriticAggregator",
    "DeterministicRepairDiagnosticianAggregator",
    "DeterministicRepairEngine",
    "DiagnosticCategory",
    "EvaluationService",
    "FullStackDiscoveryService",
    "InventoryService",
    "KnowledgeService",
    "PlanValidationResult",
    "PlanningService",
    "ProjectAdoptionService",
    "RepairStrategy",
    "ReportService",
    "ResumableExecutionService",
    "RuleBasedPlanValidator",
    "SignalCallRepairStrategy",
    "SnapshotFileReader",
    "SpecTestBedRepairStrategy",
    "SpecialistCoordinator",
    "StructuredDiagnostic",
    "SyntaxLintRepairStrategy",
    "TransformationService",
    "ValidationService",
    "parse_diagnostics",
]
