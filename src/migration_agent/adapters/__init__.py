"""Concrete adapters for external boundaries."""

from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter
from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.adapters.gemini import GeminiRuntimeAdapter
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.adapters.reporting import AnalysisReportWriter, InventoryReportWriter

__all__ = [
    "AnalysisReportWriter",
    "AngularAdapter",
    "EmberClassicAdapter",
    "FakeAgentRuntime",
    "GeminiRuntimeAdapter",
    "GitGovernanceAdapter",
    "InventoryReportWriter",
    "OpenAIAgentsRuntimeAdapter",
    "SafeFilesystemInspector",
    "SqliteCheckpointStore",
]
