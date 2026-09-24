import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.adapters.reporting import InventoryReportWriter
from migration_agent.application import InventoryService
from migration_agent.cli import app
from migration_agent.ports import FrameworkAdapterRegistry

runner = CliRunner()


def _inventory(source: Path):
    service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
    )
    return service.inventory(source)


def test_reports_are_stable_and_have_versioned_json_schema(tmp_path: Path) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    output = tmp_path / "reports"
    inventory = _inventory(fixture)
    writer = InventoryReportWriter()

    json_path, markdown_path = writer.write(inventory, output)
    first_json = json_path.read_text(encoding="utf-8")
    writer.write(inventory, output)

    assert json_path.read_text(encoding="utf-8") == first_json
    payload = json.loads(first_json)
    assert list(sorted(payload)) == [
        "dependencies",
        "exclusions",
        "files",
        "frameworks",
        "issues",
        "package_boundaries",
        "repository",
        "schema_version",
    ]
    assert payload["schema_version"] == 1
    assert "ember-classic" in markdown_path.read_text(encoding="utf-8")


def test_report_output_must_not_overlap_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="must not overlap"):
        InventoryReportWriter().write(_inventory(source), source / "reports")


def test_cli_inventory_writes_json_and_markdown(tmp_path: Path) -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    output = tmp_path / "cli-reports"

    result = runner.invoke(app, ["inventory", str(fixture), "--output", str(output)])

    assert result.exit_code == 0
    command_result = json.loads(result.stdout)
    assert command_result["status"] == "ok"
    assert command_result["frameworks"] == ["ember-classic"]
    assert (output / "inventory.json").is_file()
    assert (output / "inventory.md").is_file()


def test_report_does_not_disclose_excluded_secret_filename(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    secret_name = ".env.production"
    (source / secret_name).write_text("TOKEN=do-not-report", encoding="utf-8")
    (source / "package.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "reports"

    json_path, markdown_path = InventoryReportWriter().write(_inventory(source), output)

    assert secret_name not in json_path.read_text(encoding="utf-8")
    assert secret_name not in markdown_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["exclusions"]["secret_like_files"] == 1
