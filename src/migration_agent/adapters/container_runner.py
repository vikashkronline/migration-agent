"""Sandboxed containerized command runner adapter implementing CommandRunnerPort."""

import shutil
import time
from pathlib import Path

from migration_agent.adapters.command_runner import SubprocessCommandRunner
from migration_agent.domain import (
    ValidationCommand,
    ValidationResult,
    ValidationStatus,
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


class ContainerizedCommandRunner(CommandRunnerPort):
    """Executes validation commands inside an isolated container sandbox with fallback."""

    def __init__(
        self,
        container_engine: str = "docker",
        container_image: str = "node:20-alpine",
        enabled: bool = False,
        allowlist: set[str] | None = None,
        fallback_runner: CommandRunnerPort | None = None,
    ) -> None:
        self.container_engine = container_engine
        self.container_image = container_image
        self.enabled = enabled
        self.allowlist = set(allowlist) if allowlist is not None else set(_ALLOWLISTED_EXECUTABLES)
        self.fallback_runner = (
            fallback_runner
            if fallback_runner is not None
            else SubprocessCommandRunner(allowlist=self.allowlist)
        )

    def is_container_available(self) -> bool:
        """Check whether the container engine is available on the host."""
        if not self.enabled:
            return False
        return shutil.which(self.container_engine) is not None

    def run_command(
        self,
        command: ValidationCommand,
        working_dir: Path,
    ) -> ValidationResult:
        """Run command inside container sandbox if enabled and available, else fallback."""
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

        # Check for shell metacharacters
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

        if not self.is_container_available():
            # Gracefully delegate to subprocess fallback runner
            return self.fallback_runner.run_command(command, working_dir)

        # If container available, render container execution
        start_time = time.perf_counter()
        target_dir = Path(working_dir).resolve()
        posix_path = str(target_dir).replace("\\", "/")

        container_cmd = [
            self.container_engine,
            "run",
            "--rm",
            "--network",
            "none",
            "-v",
            f"{posix_path}:/workspace",
            "-w",
            "/workspace",
            self.container_image,
            command.executable,
            *command.args,
        ]

        # Execute container command via fallback runner infrastructure
        fake_val_cmd = ValidationCommand(
            executable=self.container_engine,
            args=tuple(container_cmd[1:]),
            profile=command.profile,
        )
        runner = SubprocessCommandRunner(allowlist={self.container_engine})
        res = runner.run_command(fake_val_cmd, working_dir)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        return ValidationResult(
            command=f"[SANDBOX:{self.container_engine}] {command.rendered_command}",
            profile=command.profile,
            status=res.status,
            exit_code=res.exit_code,
            duration_ms=duration_ms,
            sanitized_output=res.sanitized_output,
            output_digest=res.output_digest,
            diagnostics=res.diagnostics,
        )
