import os
from pathlib import Path

import pytest
from agents import tracing

from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.application.analysis import SnapshotFileReader
from migration_agent.application.inventory import InventoryService
from migration_agent.ports import AnalysisRequest, FrameworkAdapterRegistry, InspectionPolicy


def test_openai_runtime_adapter_disables_tracing() -> None:
    OpenAIAgentsRuntimeAdapter()
    # Verify tracing is disabled by default
    assert tracing.get_trace_provider()._disabled is True


@pytest.mark.live
def test_openai_agent_runtime_live_call() -> None:
    if not os.getenv("MIGRATION_AGENT_RUN_LIVE_TESTS"):
        pytest.skip("Opt-in live model tests disabled by default.")

    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("No OpenAI API key available for live test.")

    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    filesystem = SafeFilesystemInspector()
    frameworks = FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter()))
    service = InventoryService(filesystem=filesystem, frameworks=frameworks)

    snapshot = filesystem.inspect(fixture_path, InspectionPolicy())
    inventory = service.inventory(fixture_path)
    file_reader = SnapshotFileReader(snapshot)

    adapter = OpenAIAgentsRuntimeAdapter()
    request = AnalysisRequest(
        inventory=inventory,
        provider="openai",
        model="gpt-4o",
    )
    result = adapter.analyze(request, file_reader)
    assert len(result.findings) > 0
    assert result.provider == "openai"
