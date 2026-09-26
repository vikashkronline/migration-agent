"""Unit tests for 'graph' and 'fullstack' CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from migration_agent.cli import app

runner = CliRunner()
FIXTURE_PATH = Path("tests/fixtures/fullstack-ecommerce-mini")


def test_cli_graph_command_json() -> None:
    result = runner.invoke(app, ["graph", str(FIXTURE_PATH), "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert "frontend" in payload["domains_detected"]
    assert "backend_api" in payload["domains_detected"]
    assert "database_schema" in payload["domains_detected"]
    assert "infrastructure" in payload["domains_detected"]
    assert len(payload["nodes"]) >= 5
    assert len(payload["edges"]) >= 3


def test_cli_graph_command_mermaid() -> None:
    result = runner.invoke(app, ["graph", str(FIXTURE_PATH), "--mermaid"])
    assert result.exit_code == 0
    assert "flowchart TD" in result.stdout
    assert "subgraph_frontend" in result.stdout
    assert "subgraph_backend_api" in result.stdout


def test_cli_graph_command_summary() -> None:
    result = runner.invoke(app, ["graph", str(FIXTURE_PATH), "--format", "summary"])
    assert result.exit_code == 0
    assert "Repository: fullstack-ecommerce-mini" in result.stdout
    assert "Domains detected:" in result.stdout
    assert "Total nodes:" in result.stdout


def test_cli_graph_command_impact_of() -> None:
    result = runner.invoke(app, ["graph", str(FIXTURE_PATH), "--impact-of", "db:users"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert "impact_analysis" in payload
    impact = payload["impact_analysis"]
    assert impact["target_node_id"] == "db:users"
    assert "api:GET:/api/users" in impact["dependents"]


def test_cli_graph_command_with_output_dir(tmp_path: Path) -> None:
    out_dir = tmp_path / "graph_reports"
    result = runner.invoke(
        app,
        ["graph", str(FIXTURE_PATH), "--output-dir", str(out_dir)],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert "reports" in payload
    assert Path(payload["reports"]["json_report"]).is_file()
    assert Path(payload["reports"]["mermaid_report"]).is_file()
    assert Path(payload["reports"]["markdown_report"]).is_file()


def test_cli_fullstack_alias() -> None:
    result = runner.invoke(app, ["fullstack", str(FIXTURE_PATH)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert "summary" in payload


def test_cli_graph_invalid_impact_node() -> None:
    result = runner.invoke(app, ["graph", str(FIXTURE_PATH), "--impact-of", "nonexistent:node"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert "not found" in payload["error"]
