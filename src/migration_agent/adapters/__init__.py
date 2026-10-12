"""Concrete adapters for external boundaries."""

from typing import TYPE_CHECKING

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.command_runner import FakeCommandRunner, SubprocessCommandRunner
from migration_agent.adapters.container_runner import ContainerizedCommandRunner
from migration_agent.adapters.control_api import (
    InMemoryEventBroadcaster,
    LoopbackControlServer,
)
from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.foundation_transformation import FoundationTransformationAdapter
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
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.adapters.knowledge import GitKnowledgeAdapter
from migration_agent.adapters.mcp import (
    DoctorResult,
    InventoryResult,
    PlanShowResult,
    ProjectBinding,
    RunStatusResult,
    StepPreviewResult,
    create_mcp_server,
    run_mcp_server,
)
from migration_agent.adapters.reporting import AnalysisReportWriter, InventoryReportWriter
from migration_agent.adapters.transforms import (
    AngularJsDirectiveExtractor,
    AngularJsServiceExtractor,
    AngularStandaloneComponentRenderer,
    AngularStandaloneServiceRenderer,
    EmberClassicComponentExtractor,
)
from migration_agent.adapters.trust_store import (
    CryptoSignatureVerifierAdapter,
    LocalTrustStoreAdapter,
)
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.fullstack_service import CrossDomainLinker

if TYPE_CHECKING:
    from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter
    from migration_agent.adapters.gemini import GeminiRuntimeAdapter


def __getattr__(name: str) -> object:
    if name == "OpenAIAgentsRuntimeAdapter":
        from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter

        return OpenAIAgentsRuntimeAdapter
    if name == "GeminiRuntimeAdapter":
        from migration_agent.adapters.gemini import GeminiRuntimeAdapter

        return GeminiRuntimeAdapter
    raise AttributeError(name)


__all__ = [
    "AnalysisReportWriter",
    "AngularAdapter",
    "AngularJsDirectiveAdapter",
    "AngularJsDirectiveExtractor",
    "AngularJsServiceExtractor",
    "AngularStandaloneComponentRenderer",
    "AngularStandaloneServiceRenderer",
    "BackendApiAdapter",
    "ContainerizedCommandRunner",
    "CrossDomainLinker",
    "CryptoSignatureVerifierAdapter",
    "DoctorResult",
    "EmberClassicAdapter",
    "EmberClassicComponentExtractor",
    "FakeAgentRuntime",
    "FakeCommandRunner",
    "FoundationTransformationAdapter",
    "FrontendDomainAdapter",
    "FullStackReportWriter",
    "GeminiRuntimeAdapter",
    "GitGovernanceAdapter",
    "GitKnowledgeAdapter",
    "InMemoryEventBroadcaster",
    "InfrastructureAdapter",
    "InventoryReportWriter",
    "InventoryResult",
    "LocalTrustStoreAdapter",
    "LocalWorkspaceAdapter",
    "LoopbackControlServer",
    "OpenAIAgentsRuntimeAdapter",
    "PlanShowResult",
    "ProjectBinding",
    "RunStatusResult",
    "SafeFilesystemInspector",
    "SqlDatabaseAdapter",
    "SqliteCheckpointStore",
    "StepPreviewResult",
    "SubprocessCommandRunner",
    "create_default_domain_adapters",
    "create_mcp_server",
    "run_mcp_server",
]
