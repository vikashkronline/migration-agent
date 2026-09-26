"""Concrete adapters for external boundaries."""

from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter
from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.command_runner import FakeCommandRunner, SubprocessCommandRunner
from migration_agent.adapters.control_api import (
    InMemoryEventBroadcaster,
    LoopbackControlServer,
)
from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import (
    AngularAdapter,
    AngularJsDirectiveAdapter,
    EmberClassicAdapter,
)
from migration_agent.adapters.fullstack_adapters import (
    BackendApiAdapter,
    FrontendDomainAdapter,
    InfrastructureAdapter,
    SqlDatabaseAdapter,
    create_default_domain_adapters,
)
from migration_agent.adapters.fullstack_reporting import FullStackReportWriter
from migration_agent.adapters.gemini import GeminiRuntimeAdapter
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.adapters.reporting import AnalysisReportWriter, InventoryReportWriter
from migration_agent.adapters.transforms import (
    AngularJsDirectiveExtractor,
    AngularStandaloneComponentRenderer,
    EmberClassicComponentExtractor,
)
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.fullstack_service import CrossDomainLinker

__all__ = [
    "AnalysisReportWriter",
    "AngularAdapter",
    "AngularJsDirectiveAdapter",
    "AngularJsDirectiveExtractor",
    "AngularStandaloneComponentRenderer",
    "BackendApiAdapter",
    "CrossDomainLinker",
    "EmberClassicAdapter",
    "EmberClassicComponentExtractor",
    "FakeAgentRuntime",
    "FakeCommandRunner",
    "FrontendDomainAdapter",
    "FullStackReportWriter",
    "GeminiRuntimeAdapter",
    "GitGovernanceAdapter",
    "InMemoryEventBroadcaster",
    "InfrastructureAdapter",
    "InventoryReportWriter",
    "LocalWorkspaceAdapter",
    "LoopbackControlServer",
    "OpenAIAgentsRuntimeAdapter",
    "SafeFilesystemInspector",
    "SqlDatabaseAdapter",
    "SqliteCheckpointStore",
    "SubprocessCommandRunner",
    "create_default_domain_adapters",
]
