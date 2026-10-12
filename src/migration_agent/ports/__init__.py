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
from migration_agent.ports.control_api import (
    ControlApiServerPort,
    EventBroadcasterPort,
)
from migration_agent.ports.filesystem import FilesystemInspectorPort, InspectionPolicy
from migration_agent.ports.frameworks import FrameworkAdapter, FrameworkAdapterRegistry
from migration_agent.ports.fullstack import (
    DatabaseInspectorPort,
    DomainDiscoveryAdapterPort,
)
from migration_agent.ports.governance import (
    GovernancePort,
    ProjectManifest,
    ProjectPolicy,
)
from migration_agent.ports.knowledge import KnowledgePort
from migration_agent.ports.specialists import SpecialistRuntimePort
from migration_agent.ports.transformation import (
    ComponentExtractorPort,
    ComponentRendererPort,
    FoundationTransformationPort,
    IntermediateComponent,
    ServiceExtractorPort,
    ServiceRendererPort,
)
from migration_agent.ports.trust import SignatureVerifierPort, TrustStorePort
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
    "ControlApiServerPort",
    "DatabaseInspectorPort",
    "DomainDiscoveryAdapterPort",
    "EventBroadcasterPort",
    "FileReaderPort",
    "FilesystemInspectorPort",
    "FoundationTransformationPort",
    "FrameworkAdapter",
    "FrameworkAdapterRegistry",
    "GovernancePort",
    "InspectionPolicy",
    "IntermediateComponent",
    "KnowledgePort",
    "OperationalCheckpoint",
    "PlanningRequest",
    "ProjectManifest",
    "ProjectPolicy",
    "ServiceExtractorPort",
    "ServiceRendererPort",
    "SignatureVerifierPort",
    "SpecialistRuntimePort",
    "TrustStorePort",
    "WorkspacePort",
]
