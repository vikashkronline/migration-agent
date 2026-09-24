from pathlib import Path

from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.ports import FrameworkAdapterRegistry, InspectionPolicy


def test_detects_ember_classic_with_inventory_backed_evidence() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    snapshot = SafeFilesystemInspector().inspect(fixture, InspectionPolicy())
    registry = FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter()))

    fingerprints = registry.detect(snapshot)

    assert len(fingerprints) == 1
    assert fingerprints[0].framework_id == "ember-classic"
    assert fingerprints[0].confidence == 1.0
    inventory_paths = {file.path for file in snapshot.files}
    assert {item.path for item in fingerprints[0].evidence} <= inventory_paths


def test_detects_angular_and_standalone_evidence(tmp_path: Path) -> None:
    repository = tmp_path / "angular-project"
    (repository / "src" / "app").mkdir(parents=True)
    (repository / "package.json").write_text(
        '{"dependencies":{"@angular/core":"^20.0.0"}}',
        encoding="utf-8",
    )
    (repository / "angular.json").write_text("{}", encoding="utf-8")
    (repository / "src" / "app" / "app.component.ts").write_text(
        "@Component({ standalone: true }) export class AppComponent {}",
        encoding="utf-8",
    )
    snapshot = SafeFilesystemInspector().inspect(repository, InspectionPolicy())

    fingerprint = AngularAdapter().detect(snapshot)

    assert fingerprint is not None
    assert fingerprint.framework_id == "angular"
    assert fingerprint.confidence == 1.0
    assert {evidence.kind for evidence in fingerprint.evidence} == {
        "build_configuration",
        "manifest_dependency",
        "standalone_component",
    }


def test_unknown_framework_returns_no_fingerprint(tmp_path: Path) -> None:
    repository = tmp_path / "unknown-project"
    repository.mkdir()
    (repository / "package.json").write_text('{"name":"unknown"}', encoding="utf-8")
    snapshot = SafeFilesystemInspector().inspect(repository, InspectionPolicy())
    registry = FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter()))

    assert registry.detect(snapshot) == ()


def test_registry_rejects_duplicate_framework_ids() -> None:
    try:
        FrameworkAdapterRegistry((AngularAdapter(), AngularAdapter()))
    except ValueError as error:
        assert str(error) == "framework adapter IDs must be unique"
    else:
        raise AssertionError("duplicate framework adapter IDs were accepted")
