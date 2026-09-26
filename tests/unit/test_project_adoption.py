"""Unit tests for ProjectAdoptionService and init/adopt CLI commands (Phase 12)."""

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from migration_agent.adapters import (
    AngularAdapter,
    AngularJsDirectiveAdapter,
    EmberClassicAdapter,
    GitGovernanceAdapter,
    SafeFilesystemInspector,
    create_default_domain_adapters,
)
from migration_agent.application import (
    FullStackDiscoveryService,
    InventoryService,
    ProjectAdoptionService,
)
from migration_agent.cli import app
from migration_agent.ports import FrameworkAdapterRegistry

runner = CliRunner()


def _make_adoption_service() -> ProjectAdoptionService:
    governance = GitGovernanceAdapter()
    inspector = SafeFilesystemInspector()
    registry = FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )
    inv_svc = InventoryService(inspector, registry)
    fullstack_svc = FullStackDiscoveryService(inspector, create_default_domain_adapters())
    return ProjectAdoptionService(governance, inv_svc, fullstack_svc)


def test_init_creates_governance_layout(tmp_path: Path) -> None:
    svc = _make_adoption_service()
    project_dir = tmp_path / "new_project"

    manifest = svc.init(project_dir, project_id="test-proj")
    assert manifest.project_id == "test-proj"
    assert manifest.schema_version == 1

    agent_dir = project_dir / ".agent"
    assert (agent_dir / "manifest.json").is_file()
    assert (agent_dir / "policy.json").is_file()
    assert (agent_dir / "config.json").is_file()
    assert (agent_dir / "access" / "roles.json").is_file()
    assert (agent_dir / "access" / "principals.json").is_file()
    assert (agent_dir / "plans").is_dir()
    assert (agent_dir / "workflows").is_dir()
    assert (agent_dir / "challenges").is_dir()
    assert (agent_dir / "solutions").is_dir()
    assert (agent_dir / "learnings").is_dir()
    assert (agent_dir / "decisions").is_dir()
    assert (agent_dir / ".gitignore").is_file()


def test_adopt_existing_project(tmp_path: Path) -> None:
    repo = tmp_path / "legacy_repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps(
            {
                "name": "legacy-app",
                "dependencies": {
                    "ember-source": "~3.28.0",
                },
            }
        ),
        encoding="utf-8",
    )
    (repo / "app").mkdir()
    (repo / "app" / "component.js").write_text(
        "export default Component.extend({});\n", encoding="utf-8"
    )

    svc = _make_adoption_service()
    report = svc.adopt(repo, allow_dirty=True)

    assert report.project_id == "legacy_repo"
    assert "ember-classic" in report.detected_frameworks
    assert report.eligible_files_count >= 2

    # Check generated docs
    arch_doc = Path(report.architecture_doc_path)
    assert arch_doc.is_file()
    content = arch_doc.read_text(encoding="utf-8")
    assert "Architecture Overview" in content
    assert "ember-classic" in content

    mermaid_doc = Path(report.mermaid_diagram_path)
    assert mermaid_doc.is_file()
    assert "graph" in mermaid_doc.read_text(
        encoding="utf-8"
    ) or "flowchart" in mermaid_doc.read_text(encoding="utf-8")

    # Check .agent layout
    assert (repo / ".agent" / "manifest.json").is_file()


def test_adopt_dirty_repo_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "dirty_repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "file.txt").write_text("content", encoding="utf-8")

    svc = _make_adoption_service()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = " M file.txt\n"

        import pytest

        with pytest.raises(RuntimeError, match="uncommitted dirty changes"):
            svc.adopt(repo, allow_dirty=False)


def test_cli_init_command(tmp_path: Path) -> None:
    target = tmp_path / "cli_init_target"
    result = runner.invoke(app, ["init", str(target), "--id", "custom-cli-id"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "initialized"
    assert data["project_id"] == "custom-cli-id"
    assert (target / ".agent" / "manifest.json").is_file()


def test_cli_adopt_command(tmp_path: Path) -> None:
    target = tmp_path / "cli_adopt_target"
    target.mkdir()
    (target / "package.json").write_text('{"name":"cli-app"}', encoding="utf-8")

    result = runner.invoke(app, ["adopt", str(target), "--allow-dirty"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "adopted"
    assert (target / "docs" / "architecture" / "architecture.md").is_file()
