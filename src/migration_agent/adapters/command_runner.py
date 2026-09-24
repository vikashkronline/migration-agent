"""Concrete command runner adapters implementing CommandRunnerPort."""

import os
import subprocess
import time
from pathlib import Path

from migration_agent.domain import (
    ValidationCommand,
    ValidationResult,
    ValidationStatus,
    compute_file_sha256,
)
from migration_agent.ports import CommandRunnerPort

_ALLOWLISTED_EXECUTABLES = {
    "git",
    "ng",
    "node",
    "npm",
    "npx",
    "pytest",
    "python",
    "tsc",
    "uv",
}

_SENSITIVE_ENV_SUBSTRINGS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "CREDENTIAL",
    "AUTH",
    "OPENAI",
    "GEMINI",
)


class SubprocessCommandRunner(CommandRunnerPort):
    """Executes allowlisted subprocess commands strictly confined within a staging workspace."""

    def __init__(
        self,
        allowlist: set[str] | None = None,
        working_dir_root: Path | str | None = None,
    ) -> None:
        self.allowlist = set(allowlist) if allowlist is not None else set(_ALLOWLISTED_EXECUTABLES)
        self.working_dir_root = Path(working_dir_root) if working_dir_root is not None else None

    def _sanitize_environment(self) -> dict[str, str]:
        """Strip sensitive credentials, API keys, and tokens from subprocess environment."""
        sanitized: dict[str, str] = {}
        for key, val in os.environ.items():
            key_upper = key.upper()
            if any(sub in key_upper for sub in _SENSITIVE_ENV_SUBSTRINGS):
                continue
            sanitized[key] = val
        # Ensure NODE_ENV is set safely
        sanitized.setdefault("NODE_ENV", "test")
        return sanitized

    def run_command(
        self,
        command: ValidationCommand,
        working_dir: Path,
    ) -> ValidationResult:
        """Execute an allowlisted command with confinement, sanitization, and timeouts."""
        exec_name = command.executable.strip().lower()
        if exec_name not in self.allowlist:
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=ValidationStatus.DISALLOWED,
                exit_code=None,
                duration_ms=0,
                sanitized_output="",
                output_digest="",
                diagnostics=(
                    f"Executable '{command.executable}' is not in the allowlist. "
                    f"Permitted: {sorted(self.allowlist)}",
                ),
            )

        # Check for shell metacharacters in arguments
        disallowed_chars = {";", "&", "|", "`", "$", "\n", "\r"}
        for arg in command.args:
            if any(ch in arg for ch in disallowed_chars):
                return ValidationResult(
                    command=command.rendered_command,
                    profile=command.profile,
                    status=ValidationStatus.DISALLOWED,
                    exit_code=None,
                    duration_ms=0,
                    sanitized_output="",
                    output_digest="",
                    diagnostics=(f"Disallowed shell metacharacter detected in argument: '{arg}'.",),
                )

        target_dir = Path(working_dir).resolve()
        if self.working_dir_root is not None:
            root_resolved = self.working_dir_root.resolve()
            if not str(target_dir).startswith(str(root_resolved)):
                return ValidationResult(
                    command=command.rendered_command,
                    profile=command.profile,
                    status=ValidationStatus.DISALLOWED,
                    exit_code=None,
                    duration_ms=0,
                    sanitized_output="",
                    output_digest="",
                    diagnostics=(
                        f"Working directory '{target_dir}' escapes allowed root '{root_resolved}'.",
                    ),
                )

        if not target_dir.is_dir():
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=ValidationStatus.FAILED,
                exit_code=1,
                duration_ms=0,
                sanitized_output="",
                output_digest="",
                diagnostics=(f"Working directory '{target_dir}' does not exist.",),
            )

        cmd_args = [command.executable, *command.args]
        env = self._sanitize_environment()
        start_time = time.perf_counter()

        try:
            completed = subprocess.run(
                cmd_args,
                cwd=target_dir,
                env=env,
                shell=False,
                capture_output=True,
                timeout=command.timeout_seconds,
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            raw_output = completed.stdout + completed.stderr
            output_digest = compute_file_sha256(raw_output)

            # Bound output to max_output_bytes
            truncated_bytes = raw_output[: command.max_output_bytes]
            sanitized_text = truncated_bytes.decode("utf-8", errors="replace")
            if len(raw_output) > command.max_output_bytes:
                sanitized_text += "\n... [TRUNCATED]"

            # Extract basic diagnostic lines on failure
            diagnostics: list[str] = []
            if completed.returncode != 0:
                for line in sanitized_text.splitlines():
                    lower_line = line.lower()
                    if any(
                        keyword in lower_line
                        for keyword in ("error", "fail", "exception", "cannot find")
                    ):
                        diagnostics.append(line.strip())
                if not diagnostics:
                    diagnostics.append(f"Command exited with non-zero code {completed.returncode}.")

            status = (
                ValidationStatus.PASSED if completed.returncode == 0 else ValidationStatus.FAILED
            )

            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=status,
                exit_code=completed.returncode,
                duration_ms=duration_ms,
                sanitized_output=sanitized_text,
                output_digest=output_digest,
                diagnostics=tuple(diagnostics[:10]),
            )

        except subprocess.TimeoutExpired as timeout_err:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            timeout_output = (timeout_err.stdout or b"") + (timeout_err.stderr or b"")
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=ValidationStatus.TIMED_OUT,
                exit_code=None,
                duration_ms=duration_ms,
                sanitized_output=timeout_output.decode("utf-8", errors="replace"),
                output_digest=compute_file_sha256(timeout_output),
                diagnostics=(f"Command timed out after {command.timeout_seconds} seconds.",),
            )
        except OSError as os_err:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=ValidationStatus.FAILED,
                exit_code=1,
                duration_ms=duration_ms,
                sanitized_output=str(os_err),
                output_digest=compute_file_sha256(str(os_err).encode()),
                diagnostics=(f"Process execution error: {os_err}",),
            )


class FakeCommandRunner(CommandRunnerPort):
    """Deterministic offline test adapter for command execution."""

    def __init__(
        self,
        canned_results: dict[str, ValidationResult] | None = None,
        default_status: ValidationStatus = ValidationStatus.PASSED,
        default_exit_code: int | None = None,
        default_output: str = "Mock execution output",
        diagnostics: tuple[str, ...] | None = None,
    ) -> None:
        self.canned_results = canned_results or {}
        self.default_status = default_status
        self.default_exit_code = (
            default_exit_code
            if default_exit_code is not None
            else (0 if default_status == ValidationStatus.PASSED else 1)
        )
        self.default_output = default_output
        self.diagnostics = (
            diagnostics
            if diagnostics is not None
            else (() if default_status == ValidationStatus.PASSED else ("Mock error",))
        )
        self.executed_commands: list[tuple[ValidationCommand, Path]] = []

    def run_command(
        self,
        command: ValidationCommand,
        working_dir: Path,
    ) -> ValidationResult:
        """Return configured or canned validation outcome."""
        self.executed_commands.append((command, working_dir))
        key = command.rendered_command
        if key in self.canned_results:
            return self.canned_results[key]

        return ValidationResult(
            command=command.rendered_command,
            profile=command.profile,
            status=self.default_status,
            exit_code=self.default_exit_code,
            duration_ms=10,
            sanitized_output=self.default_output,
            output_digest="sha256:fake-output-digest",
            diagnostics=self.diagnostics,
        )
