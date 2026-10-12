"""Unit tests for ProjectAdoptionService and init/adopt CLI commands (Phase 12)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
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


def test_cli_external_init_is_read_only_and_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "source.js").write_bytes(b"untouched\r\n")
    project = tmp_path / "project"
    args = [
        "init",
        str(project),
        "--source",
        str(source),
        "--state-dir",
        str(tmp_path / "state"),
        "--staging-root",
        str(tmp_path / "staging"),
        "--id",
        "pilot",
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["migration_session"]["source_root"] == str(source.resolve())
    binding = project / ".agent" / "migration-session.json"
    original = binding.read_bytes()
    assert b"\r" not in original
    assert runner.invoke(app, args).exit_code == 0
    assert binding.read_bytes() == original
    assert list(source.iterdir()) == [source / "source.js"]
    assert (source / "source.js").read_bytes() == b"untouched\r\n"
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / "staging").exists()


@pytest.mark.parametrize("other", ["project", "state", "staging"])
@pytest.mark.parametrize("relation", ["same", "child", "parent"])
def test_external_init_rejects_source_overlap_before_writes(
    tmp_path: Path, other: str, relation: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    paths = {name: tmp_path / name for name in ("project", "state", "staging")}
    paths[other] = {"same": source, "child": source / "nested", "parent": tmp_path}[relation]
    with pytest.raises(ValueError, match="UNSAFE_PATHS"):
        _make_adoption_service().init_migration(
            paths["project"], source, paths["staging"], paths["state"]
        )
    assert not list(source.iterdir())
    assert not (tmp_path / "project").exists()


@pytest.mark.parametrize("other", ["state", "staging"])
def test_external_init_rejects_project_artifact_overlap(tmp_path: Path, other: str) -> None:
    source = tmp_path / "source"
    source.mkdir()
    paths = {name: tmp_path / name for name in ("project", "state", "staging")}
    paths[other] = paths["project"] / other
    with pytest.raises(ValueError, match="UNSAFE_PATHS"):
        _make_adoption_service().init_migration(
            paths["project"], source, paths["staging"], paths["state"]
        )
    assert not paths["project"].exists()


def test_external_init_refuses_rebinding(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    project = tmp_path / "project"
    service = _make_adoption_service()
    service.init_migration(project, source, tmp_path / "staging", tmp_path / "state")
    before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="SESSION_CONFLICT"):
        service.init_migration(project, source, tmp_path / "staging2", tmp_path / "state")
    assert before == {
        p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()
    }


def test_external_init_requires_existing_source(tmp_path: Path) -> None:
    project = tmp_path / "project"
    result = runner.invoke(app, ["init", str(project), "--source", str(tmp_path / "missing")])
    assert result.exit_code == 1
    assert not project.exists()


def test_init_artifact_options_require_source(tmp_path: Path) -> None:
    project = tmp_path / "project"
    result = runner.invoke(app, ["init", str(project), "--state-dir", str(tmp_path / "state")])
    assert result.exit_code == 1
    assert "MISSING_SOURCE" in result.output
    assert not project.exists()


def test_cli_adopt_command(tmp_path: Path) -> None:
    target = tmp_path / "cli_adopt_target"
    target.mkdir()
    (target / "package.json").write_text('{"name":"cli-app"}', encoding="utf-8")

    result = runner.invoke(app, ["adopt", str(target), "--allow-dirty"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "adopted"
    assert (target / "docs" / "architecture" / "architecture.md").is_file()
