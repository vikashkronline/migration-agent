"""Unit tests for containerized sandboxed command execution and fallback."""

from pathlib import Path

from migration_agent.adapters import ContainerizedCommandRunner, FakeCommandRunner
from migration_agent.domain import ValidationCommand, ValidationProfile, ValidationStatus


def test_container_runner_disallowed_executable(tmp_path: Path) -> None:
    runner = ContainerizedCommandRunner()
    cmd = ValidationCommand(
        executable="bash", args=("-c", "rm -rf /"), profile=ValidationProfile.TEST
    )
    res = runner.run_command(cmd, tmp_path)
    assert res.status == ValidationStatus.DISALLOWED
    assert "not in the allowlist" in res.diagnostics[0]


def test_container_runner_disallowed_metacharacters(tmp_path: Path) -> None:
    runner = ContainerizedCommandRunner()
    cmd = ValidationCommand(
        executable="npm", args=("test;", "malicious"), profile=ValidationProfile.TEST
    )
    res = runner.run_command(cmd, tmp_path)
    assert res.status == ValidationStatus.DISALLOWED
    assert "Disallowed shell metacharacter" in res.diagnostics[0]


def test_container_runner_fallback_to_fake_runner(tmp_path: Path) -> None:
    fake = FakeCommandRunner(
        default_status=ValidationStatus.PASSED,
        default_output="PASS all tests",
        default_exit_code=0,
    )
    runner = ContainerizedCommandRunner(enabled=False, fallback_runner=fake)

    cmd = ValidationCommand(executable="npm", args=("test",), profile=ValidationProfile.TEST)
    res = runner.run_command(cmd, tmp_path)
    assert res.status == ValidationStatus.PASSED
    assert res.exit_code == 0
    assert "PASS all tests" in res.sanitized_output


def test_container_runner_is_container_available() -> None:
    runner_disabled = ContainerizedCommandRunner(enabled=False)
    assert runner_disabled.is_container_available() is False

    runner_nonexistent = ContainerizedCommandRunner(
        container_engine="nonexistent-engine-binary-12345",
        enabled=True,
    )
    assert runner_nonexistent.is_container_available() is False
