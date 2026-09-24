from pathlib import Path

import pytest
from pydantic import ValidationError

from migration_agent.domain import MigrationRequest


def test_migration_request_is_framework_neutral_and_dry_by_default() -> None:
    request = MigrationRequest(
        source_path=Path("legacy-app"),
        source_framework=" Ember Classic ",
        target_framework="Angular standalone",
    )

    assert request.source_path == Path("legacy-app")
    assert request.source_framework == "Ember Classic"
    assert request.target_framework == "Angular standalone"
    assert request.dry_run is True


def test_migration_request_rejects_blank_framework_names() -> None:
    with pytest.raises(ValidationError):
        MigrationRequest(
            source_path=Path("legacy-app"),
            source_framework=" ",
            target_framework="Angular standalone",
        )
