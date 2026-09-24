from pathlib import Path

import pytest

from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.domain import FileCategory
from migration_agent.ports import InspectionPolicy


def test_inspector_classifies_fixture_files() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"

    snapshot = SafeFilesystemInspector().inspect(fixture, InspectionPolicy())

    categories = {file.path: file.category for file in snapshot.files}
    assert categories == {
        "app/components/user-card.js": FileCategory.SOURCE,
        "app/styles/app.css": FileCategory.STYLE,
        "app/templates/components/user-card.hbs": FileCategory.TEMPLATE,
        "ember-cli-build.js": FileCategory.BUILD_CONFIG,
        "package.json": FileCategory.MANIFEST,
        "tests/integration/components/user-card-test.js": FileCategory.TEST,
    }


def test_inspector_aggregates_unsafe_and_ineligible_files(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / "src").mkdir(parents=True)
    (repository / "node_modules").mkdir()
    (repository / "src" / "main.js").write_text("export default 1;", encoding="utf-8")
    (repository / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
    (repository / ".env.local").write_text("TOKEN=secret", encoding="utf-8")
    (repository / "src" / "binary.js").write_bytes(b"const x = \x00;")
    (repository / "src" / "oversized.js").write_text("x" * 40, encoding="utf-8")

    snapshot = SafeFilesystemInspector().inspect(
        repository,
        InspectionPolicy(max_text_file_bytes=32),
    )

    assert [file.path for file in snapshot.files] == ["src/main.js"]
    assert snapshot.exclusions.ignored_entries == 1
    assert snapshot.exclusions.secret_like_files == 1
    assert snapshot.exclusions.binary_files == 1
    assert snapshot.exclusions.oversized_files == 1


def test_inspector_does_not_follow_symlink_escape(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    repository.mkdir()
    outside.mkdir()
    (outside / "package.json").write_text(
        '{"dependencies":{"ember-source":"1.0.0"}}',
        encoding="utf-8",
    )
    link = repository / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symbolic links are unavailable on this host: {error}")

    snapshot = SafeFilesystemInspector().inspect(repository, InspectionPolicy())

    assert snapshot.files == ()
    assert snapshot.exclusions.symlink_entries == 1


def test_inspector_rejects_a_file_as_repository_root(tmp_path: Path) -> None:
    source_file = tmp_path / "not-a-directory"
    source_file.write_text("text", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a directory"):
        SafeFilesystemInspector().inspect(source_file, InspectionPolicy())
