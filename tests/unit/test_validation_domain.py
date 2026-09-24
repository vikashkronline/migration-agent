"""Tests for validation domain entities, enums, command templates, and reports."""

import pytest
from pydantic import ValidationError

from migration_agent.domain import (
    MigrationRunReport,
    RepairAttempt,
    RunStatus,
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
)


def test_validation_profile_values() -> None:
    assert ValidationProfile.LINT == "LINT"
    assert ValidationProfile.TYPECHECK == "TYPECHECK"
    assert ValidationProfile.TEST == "TEST"
    assert ValidationProfile.BUILD == "BUILD"


def test_validation_status_values() -> None:
    assert ValidationStatus.PASSED == "PASSED"
    assert ValidationStatus.FAILED == "FAILED"
    assert ValidationStatus.TIMED_OUT == "TIMED_OUT"
    assert ValidationStatus.DISALLOWED == "DISALLOWED"


def test_validation_command_rendering_and_immutability() -> None:
    cmd = ValidationCommand(
        executable="npm",
        args=("run", "lint"),
        profile=ValidationProfile.LINT,
        timeout_seconds=30,
        max_output_bytes=32768,
    )
    assert cmd.rendered_command == "npm run lint"
    assert cmd.executable == "npm"
    assert cmd.args == ("run", "lint")
    assert cmd.profile == ValidationProfile.LINT
    assert cmd.timeout_seconds == 30
    assert cmd.max_output_bytes == 32768

    with pytest.raises(ValidationError):
        # Immutable / frozen
        cmd.executable = "yarn"  # type: ignore[misc]


def test_validation_command_validation_rules() -> None:
    with pytest.raises(ValidationError):
        # Empty executable
        ValidationCommand(executable="", profile=ValidationProfile.LINT)

    with pytest.raises(ValidationError):
        # Invalid timeout
        ValidationCommand(
            executable="npm",
            profile=ValidationProfile.LINT,
            timeout_seconds=0,
        )


def test_validation_result_immutability_and_defaults() -> None:
    result = ValidationResult(
        command="npx tsc --noEmit",
        profile=ValidationProfile.TYPECHECK,
        status=ValidationStatus.PASSED,
        exit_code=0,
        duration_ms=250,
        sanitized_output="No errors found.",
        output_digest="sha256:abc12345",
        diagnostics=(),
    )
    assert result.status == ValidationStatus.PASSED
    assert result.exit_code == 0
    assert result.duration_ms == 250
    assert result.output_digest == "sha256:abc12345"

    with pytest.raises(ValidationError):
        result.status = ValidationStatus.FAILED  # type: ignore[misc]


def test_repair_attempt_model() -> None:
    attempt = RepairAttempt(
        attempt_index=1,
        cited_diagnostic="SyntaxError: Unexpected token",
        previous_changeset_digest="sha256:1111",
        new_changeset_digest="sha256:2222",
        status=ValidationStatus.PASSED,
        summary="Fixed unexpected token in component",
    )
    assert attempt.attempt_index == 1
    assert attempt.cited_diagnostic == "SyntaxError: Unexpected token"
    assert attempt.previous_changeset_digest == "sha256:1111"
    assert attempt.new_changeset_digest == "sha256:2222"
    assert attempt.status == ValidationStatus.PASSED


def test_migration_run_report_model() -> None:
    report = MigrationRunReport(
        run_id="run-001",
        plan_id="plan-001",
        source_root="/path/to/source",
        staging_root="/path/to/staging",
        status=RunStatus.SUCCESS,
        summary="Migration succeeded",
    )
    assert report.run_id == "run-001"
    assert report.status == RunStatus.SUCCESS
    assert report.validation_results == ()
    assert report.repair_attempts == ()
    assert report.applied_changeset_id is None
