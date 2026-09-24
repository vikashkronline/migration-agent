"""Tests for SubprocessCommandRunner confinement and FakeCommandRunner test double."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from migration_agent.adapters.command_runner import (
    FakeCommandRunner,
    SubprocessCommandRunner,
)
from migration_agent.domain import (
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
)


def test_command_runner_disallows_non_allowlisted_executable(tmp_path: Path) -> None:
    runner = SubprocessCommandRunner()
    cmd = ValidationCommand(
        executable="curl",
        args=("https://example.com",),
        profile=ValidationProfile.TEST,
    )
    result = runner.run_command(cmd, tmp_path)
    assert result.status == ValidationStatus.DISALLOWED
    assert "Executable 'curl' is not in the allowlist" in result.diagnostics[0]


def test_command_runner_disallows_shell_metacharacters(tmp_path: Path) -> None:
    runner = SubprocessCommandRunner()
    dangerous_args = [
        ("test", ";", "rm", "-rf", "/"),
        ("test", "&&", "evil"),
        ("test", "|", "cat"),
        ("test", "`id`"),
        ("test", "$SECRET"),
        ("test\nevil",),
    ]

    for args in dangerous_args:
        cmd = ValidationCommand(
            executable="npm",
            args=args,
            profile=ValidationProfile.TEST,
        )
        result = runner.run_command(cmd, tmp_path)
        assert result.status == ValidationStatus.DISALLOWED
        assert "Disallowed shell metacharacter" in result.diagnostics[0]


def test_command_runner_working_dir_outside_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "staging"
    allowed_root.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    runner = SubprocessCommandRunner(working_dir_root=allowed_root)
    cmd = ValidationCommand(
        executable="npm",
        args=("test",),
        profile=ValidationProfile.TEST,
    )
    result = runner.run_command(cmd, outside_dir)
    assert result.status == ValidationStatus.DISALLOWED
    assert "escapes allowed root" in result.diagnostics[0]


def test_environment_sanitization() -> None:
    runner = SubprocessCommandRunner()
    with patch.dict(
        "os.environ",
        {
            "PATH": "/usr/bin",
            "OPENAI_API_KEY": "sk-secret123",
            "GEMINI_API_KEY": "ai-secret456",
            "AWS_SECRET_ACCESS_KEY": "secret789",
            "GITHUB_TOKEN": "token_abc",
            "DATABASE_PASSWORD": "password123",
            "USER_AUTH_CREDENTIAL": "credential",
        },
        clear=True,
    ):
        sanitized = runner._sanitize_environment()
        assert "PATH" in sanitized
        assert "OPENAI_API_KEY" not in sanitized
        assert "GEMINI_API_KEY" not in sanitized
        assert "AWS_SECRET_ACCESS_KEY" not in sanitized
        assert "GITHUB_TOKEN" not in sanitized
        assert "DATABASE_PASSWORD" not in sanitized
        assert "USER_AUTH_CREDENTIAL" not in sanitized
        assert sanitized.get("NODE_ENV") == "test"


def test_subprocess_timeout_handling(tmp_path: Path) -> None:
    runner = SubprocessCommandRunner()
    cmd = ValidationCommand(
        executable="npm",
        args=("test",),
        profile=ValidationProfile.TEST,
        timeout_seconds=5,
    )

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["npm", "test"], timeout=5, output=b"Timed out partial output"
        )

        result = runner.run_command(cmd, tmp_path)
        assert result.status == ValidationStatus.TIMED_OUT
        assert "Command timed out after 5 seconds" in result.diagnostics[0]


def test_output_truncation_and_digest(tmp_path: Path) -> None:
    runner = SubprocessCommandRunner()
    cmd = ValidationCommand(
        executable="npm",
        args=("test",),
        profile=ValidationProfile.TEST,
        max_output_bytes=50,
    )

    long_output = b"A" * 200
    with patch("subprocess.run") as mock_run:
        mock_completed = MagicMock()
        mock_completed.stdout = long_output
        mock_completed.stderr = b""
        mock_completed.returncode = 0
        mock_run.return_value = mock_completed

        result = runner.run_command(cmd, tmp_path)
        assert result.status == ValidationStatus.PASSED
        assert "[TRUNCATED]" in result.sanitized_output
        assert result.output_digest.startswith("sha256:")
        assert len(result.output_digest.split("sha256:")[1]) == 64


def test_real_python_command_execution(tmp_path: Path) -> None:
    runner = SubprocessCommandRunner()
    cmd = ValidationCommand(
        executable="python",
        args=("-c", "print('validation-ok')"),
        profile=ValidationProfile.TEST,
    )
    result = runner.run_command(cmd, tmp_path)
    assert result.status == ValidationStatus.PASSED
    assert result.exit_code == 0
    assert "validation-ok" in result.sanitized_output
    assert result.output_digest != ""


def test_fake_command_runner() -> None:
    canned_res = ValidationResult(
        command="npm run lint",
        profile=ValidationProfile.LINT,
        status=ValidationStatus.PASSED,
        exit_code=0,
    )
    runner = FakeCommandRunner(
        canned_results={"npm run lint": canned_res},
        default_status=ValidationStatus.FAILED,
        default_exit_code=1,
        default_output="Lint error: missing semicolon",
        diagnostics=("missing semicolon",),
    )

    # Canned match
    cmd1 = ValidationCommand(executable="npm", args=("run", "lint"), profile=ValidationProfile.LINT)
    res1 = runner.run_command(cmd1, Path("/tmp"))
    assert res1.status == ValidationStatus.PASSED

    # Default fallback
    cmd2 = ValidationCommand(
        executable="npx", args=("tsc", "--noEmit"), profile=ValidationProfile.TYPECHECK
    )
    res2 = runner.run_command(cmd2, Path("/tmp"))
    assert res2.status == ValidationStatus.FAILED
    assert res2.exit_code == 1
    assert "Lint error" in res2.sanitized_output
    assert res2.diagnostics == ("missing semicolon",)

    assert len(runner.executed_commands) == 2
