from pathlib import Path

from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.application import InventoryService
from migration_agent.domain import DependencyScope
from migration_agent.ports import FrameworkAdapterRegistry


def _service() -> InventoryService:
    return InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
    )


def test_fixture_inventory_is_deterministic() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"

    first = _service().inventory(fixture)
    second = _service().inventory(fixture)

    assert first == second
    assert first.schema_version == 1
    assert [framework.framework_id for framework in first.frameworks] == ["ember-classic"]
    assert {(item.name, item.scope) for item in first.dependencies} == {
        ("ember-cli", DependencyScope.DEVELOPMENT),
        ("ember-source", DependencyScope.RUNTIME),
        ("qunit", DependencyScope.DEVELOPMENT),
    }
    assert [boundary.path for boundary in first.package_boundaries] == ["."]


def test_minimal_monorepo_boundaries_and_workspace_membership(tmp_path: Path) -> None:
    repository = tmp_path / "monorepo"
    package = repository / "packages" / "widget"
    package.mkdir(parents=True)
    (repository / "package.json").write_text(
        '{"name":"root","workspaces":["packages/*"]}',
        encoding="utf-8",
    )
    (package / "package.json").write_text(
        '{"name":"widget","dependencies":{"example":"1.0.0"}}',
        encoding="utf-8",
    )

    inventory = _service().inventory(repository)

    assert [(item.path, item.declared_workspace) for item in inventory.package_boundaries] == [
        (".", False),
        ("packages/widget", True),
    ]
    assert inventory.dependencies[0].manifest_path == "packages/widget/package.json"


def test_invalid_manifest_becomes_a_non_fatal_issue(tmp_path: Path) -> None:
    repository = tmp_path / "invalid-manifest"
    repository.mkdir()
    (repository / "package.json").write_text("{not-json", encoding="utf-8")

    inventory = _service().inventory(repository)

    assert inventory.dependencies == ()
    assert inventory.issues[0].code == "invalid_package_manifest"
    assert inventory.issues[0].path == "package.json"
