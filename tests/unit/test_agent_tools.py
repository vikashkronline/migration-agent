import json
from pathlib import Path

from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.application.analysis import SnapshotFileReader
from migration_agent.application.inventory import InventoryService
from migration_agent.ports import FrameworkAdapterRegistry, InspectionPolicy


def test_agent_tools_bounded_and_secure() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    filesystem = SafeFilesystemInspector()
    frameworks = FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter()))
    service = InventoryService(filesystem=filesystem, frameworks=frameworks)

    snapshot = filesystem.inspect(fixture_path, InspectionPolicy())
    inventory = service.inventory(fixture_path)
    file_reader = SnapshotFileReader(snapshot)

    # Create agent to extract bounded tool callables
    agent = OpenAIAgentsRuntimeAdapter.create_analysis_agent(
        inventory=inventory,
        file_reader=file_reader,
        model="gpt-4o",
        max_tool_chars=500,
    )

    tools_by_name = {tool.name: tool for tool in agent.tools}
    assert "query_inventory" in tools_by_name
    assert "read_repository_file" in tools_by_name

    query_tool = tools_by_name["query_inventory"]
    read_tool = tools_by_name["read_repository_file"]
    query_fn = query_tool.__wrapped__
    read_fn = read_tool.__wrapped__

    # 1. query_inventory tests
    summary_res = query_fn(section="summary")
    parsed_summary = json.loads(summary_res)
    assert parsed_summary["repository"] == "ember-classic-mini"
    assert parsed_summary["eligible_files_count"] == 6

    deps_res = query_fn(section="dependencies")
    parsed_deps = json.loads(deps_res)
    assert len(parsed_deps) == 3

    unknown_res = query_fn(section="unknown_section")
    assert "Error: Unknown section" in unknown_res

    # Test truncation when exceeding max_tool_chars
    files_res = query_fn(section="files")
    assert len(files_res) <= 600
    assert "Truncated" in files_res or len(files_res) <= 500

    # 2. read_repository_file tests
    # Valid file read
    content = read_fn(path="app/components/user-card.js", start_line=1, line_count=10)
    assert "1: import Component from '@ember/component';" in content
    assert "Component.extend" in content

    # Non-eligible path rejected
    rejected = read_fn(path="secret_or_missing.js")
    assert "Access denied" in rejected or "Error: Path" in rejected

    # Path traversal rejected
    traversal = read_fn(path="../../etc/passwd")
    assert "Access denied" in traversal or "Error: Path" in traversal

    # Windows backslash path normalized and read
    backslash_read = read_fn(path="app\\components\\user-card.js")
    assert "Component.extend" in backslash_read
