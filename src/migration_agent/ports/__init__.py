"""Application-owned ports implemented by outer adapters."""

from migration_agent.ports.agent_runtime import (
    AgentRuntimePort,
    AnalysisRequest,
    FileReaderPort,
)
from migration_agent.ports.filesystem import FilesystemInspectorPort, InspectionPolicy
from migration_agent.ports.frameworks import FrameworkAdapter, FrameworkAdapterRegistry

__all__ = [
    "AgentRuntimePort",
    "AnalysisRequest",
    "FileReaderPort",
    "FilesystemInspectorPort",
    "FrameworkAdapter",
    "FrameworkAdapterRegistry",
    "InspectionPolicy",
]
