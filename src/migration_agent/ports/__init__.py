"""Application-owned ports implemented by outer adapters."""

from migration_agent.ports.agent_runtime import (
    AgentRuntimePort,
    AnalysisRequest,
    FileReaderPort,
    PlanningRequest,
)
from migration_agent.ports.checkpoints import (
    AuditEvent,
    AuditLogPort,
    CheckpointPort,
    OperationalCheckpoint,
)
from migration_agent.ports.command_runner import CommandRunnerPort
from migration_agent.ports.filesystem import FilesystemInspectorPort, InspectionPolicy
from migration_agent.ports.frameworks import FrameworkAdapter, FrameworkAdapterRegistry
from migration_agent.ports.governance import (
    GovernancePort,
    ProjectManifest,
    ProjectPolicy,
)
from migration_agent.ports.transformation import (
    ComponentExtractorPort,
    ComponentRendererPort,
    IntermediateComponent,
)
from migration_agent.ports.workspace import WorkspacePort

__all__ = [
    "AgentRuntimePort",
    "AnalysisRequest",
    "AuditEvent",
    "AuditLogPort",
    "CheckpointPort",
    "CommandRunnerPort",
    "ComponentExtractorPort",
    "ComponentRendererPort",
    "FileReaderPort",
    "FilesystemInspectorPort",
    "FrameworkAdapter",
    "FrameworkAdapterRegistry",
    "GovernancePort",
    "InspectionPolicy",
    "IntermediateComponent",
    "OperationalCheckpoint",
    "PlanningRequest",
    "ProjectManifest",
    "ProjectPolicy",
    "WorkspacePort",
]
