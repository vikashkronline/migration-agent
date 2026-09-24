import os
from pathlib import Path

import pytest

from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.adapters.gemini import GeminiRuntimeAdapter
from migration_agent.application.analysis import SnapshotFileReader
from migration_agent.application.inventory import InventoryService
from migration_agent.ports import AnalysisRequest, FrameworkAdapterRegistry, InspectionPolicy


def test_gemini_adapter_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    adapter = GeminiRuntimeAdapter()
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    filesystem = SafeFilesystemInspector()
    frameworks = FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter()))
    service = InventoryService(filesystem=filesystem, frameworks=frameworks)

    snapshot = filesystem.inspect(fixture_path, InspectionPolicy())
    inventory = service.inventory(fixture_path)
    file_reader = SnapshotFileReader(snapshot)

    request = AnalysisRequest(
        inventory=inventory,
        provider="gemini",
        model="gemini-2.5-pro",
    )

    with pytest.raises(ValueError, match="Neither GEMINI_API_KEY nor GOOGLE_API_KEY"):
        adapter.analyze(request, file_reader)


@pytest.mark.live
def test_gemini_adapter_live_call() -> None:
    if not os.getenv("MIGRATION_AGENT_RUN_LIVE_TESTS"):
        pytest.skip("Opt-in live model tests disabled by default.")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        pytest.skip("No Gemini API key available for live test.")

    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    filesystem = SafeFilesystemInspector()
    frameworks = FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter()))
    service = InventoryService(filesystem=filesystem, frameworks=frameworks)

    snapshot = filesystem.inspect(fixture_path, InspectionPolicy())
    inventory = service.inventory(fixture_path)
    file_reader = SnapshotFileReader(snapshot)

    adapter = GeminiRuntimeAdapter(api_key=api_key)
    request = AnalysisRequest(
        inventory=inventory,
        provider="gemini",
        model="gemini-2.5-pro",
    )
    result = adapter.analyze(request, file_reader)
    assert len(result.findings) > 0
    assert result.provider == "gemini"
