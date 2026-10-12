"""Bounded validation using fixed executable templates, cancellation, and lease checks."""

import contextlib
import hashlib
import importlib
import os
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from migration_agent.domain.execution import ToolIdentity
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.validation import (
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
)

VALIDATION_COMMANDS: dict[ValidationProfile, tuple[ValidationCommand, ...]] = {
    ValidationProfile.LINT: (
        ValidationCommand(
            executable="npm",
            args=("run", "lint"),
            profile=ValidationProfile.LINT,
            timeout_seconds=60,
        ),
    ),
    ValidationProfile.TYPECHECK: (
        ValidationCommand(
            executable="tsc",
            args=("--noEmit",),
            profile=ValidationProfile.TYPECHECK,
            timeout_seconds=60,
        ),
    ),
    ValidationProfile.TEST: (
        ValidationCommand(
            executable="npm",
            args=("test", "--", "--watch=false", "--browsers=ChromeHeadless"),
            profile=ValidationProfile.TEST,
            timeout_seconds=60,
        ),
    ),
    ValidationProfile.BUILD: (
        ValidationCommand(
            executable="ng", args=("build",), profile=ValidationProfile.BUILD, timeout_seconds=60
        ),
    ),
}

VITEST_VALIDATION_COMMANDS = {
    **VALIDATION_COMMANDS,
    ValidationProfile.TYPECHECK: tuple(
        ValidationCommand(
            executable="tsc",
            args=("--project", config, "--noEmit"),
            profile=ValidationProfile.TYPECHECK,
            timeout_seconds=60,
        )
        for config in ("tsconfig.app.json", "tsconfig.spec.json")
    ),
    ValidationProfile.TEST: (
        ValidationCommand(
            executable="npm",
            args=("test", "--", "--run"),
            profile=ValidationProfile.TEST,
            timeout_seconds=60,
        ),
    ),
}
ANGULAR_21_VALIDATION_COMMANDS = {
    **VITEST_VALIDATION_COMMANDS,
    ValidationProfile.TEST: (
        ValidationCommand(
            executable="npm",
            args=("test", "--", "--watch=false"),
            profile=ValidationProfile.TEST,
            timeout_seconds=60,
        ),
    ),
}


def validation_commands(catalog: str) -> dict[ValidationProfile, tuple[ValidationCommand, ...]]:
    if catalog == "node-v1":
        return VALIDATION_COMMANDS
    if catalog == "node-vitest-v1":
        return VITEST_VALIDATION_COMMANDS
    if catalog == "node-angular-v21":
        return ANGULAR_21_VALIDATION_COMMANDS
    raise ValueError("VALIDATION_CATALOG_UNSUPPORTED: select an installed target preset.")


BROWSER_COMMAND = ValidationCommand(
    executable="node",
    args=("/agent/browser_worker.cjs", "/artifacts/request.json"),
    profile=ValidationProfile.BUILD,
)


class BrowserMounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    worker: ToolIdentity
    artifacts: str


class FencedValidationRunner:
    def __init__(
        self,
        staging_root: Path,
        permitted: tuple[ValidationCommand, ...] | None = None,
        container_image: str | None = None,
        source_root: Path | None = None,
    ) -> None:
        self.staging_root = staging_root.resolve()
        self.container_image = container_image
        self.fixture_execution = permitted is not None
        self.source_root = source_root.resolve() if source_root else None
        self.permitted = permitted or tuple(
            command
            for catalog in (
                VALIDATION_COMMANDS,
                VITEST_VALIDATION_COMMANDS,
                ANGULAR_21_VALIDATION_COMMANDS,
            )
            for commands in catalog.values()
            for command in commands
        )

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            if process.poll() is not None:
                return
            try:
                subprocess.run(
                    [
                        str(
                            Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
                            / "System32"
                            / "taskkill.exe"
                        ),
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ],
                    capture_output=True,
                    shell=False,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
        else:
            with contextlib.suppress(ProcessLookupError):
                posix_os = importlib.import_module("os")
                posix_signal = importlib.import_module("signal")
                posix_os.killpg(process.pid, posix_signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)

    def run(
        self,
        command: ValidationCommand,
        working_dir: Path,
        fence: Callable[[], None],
        engine_identity: ToolIdentity | None = None,
        browser_mounts: BrowserMounts | None = None,
    ) -> ValidationResult:
        if (
            (command != BROWSER_COMMAND if browser_mounts else command not in self.permitted)
            or (command.executable not in {"tsc", "ng", "npm", "pytest"} and not browser_mounts)
            or (browser_mounts is not None and self.fixture_execution)
            or command.timeout_seconds > 60
            or command.max_output_bytes > 65536
            or working_dir.resolve().parent != self.staging_root
            or working_dir.is_symlink()
            or working_dir.is_junction()
        ):
            raise ValueError(
                "COMMAND_REJECTED: only configured staging validation templates may run."
            )
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        env.update(
            {"NODE_ENV": "test", "npm_config_offline": "true", "npm_config_ignore_scripts": "true"}
        )
        container_name = f"migration-validation-{uuid.uuid4().hex}"
        engine = ""
        if not self.fixture_execution:
            import re

            if not self.container_image or not re.fullmatch(
                r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", self.container_image
            ):
                raise ValueError("ISOLATION_REQUIRED: configure a locally installed pinned image.")
            executable = (
                engine_identity.path
                if engine_identity
                else shutil.which("docker", path=env.get("PATH"))
            )
            if not executable:
                raise ValueError("ISOLATION_REQUIRED: install a trusted local Docker engine.")
            path = Path(executable).resolve()
            if engine_identity:
                with path.open("rb") as handle:
                    observed_digest = hashlib.file_digest(handle, "sha256").hexdigest()
                if str(path) != engine_identity.path or observed_digest != engine_identity.sha256:
                    raise ValueError(
                        "EXECUTABLE_UNTRUSTED: pinned Docker executable identity changed."
                    )
            if path.is_relative_to(self.staging_root) or (
                self.source_root and path.is_relative_to(self.source_root)
            ):
                raise ValueError(
                    "EXECUTABLE_UNTRUSTED: validation cannot launch a repository engine."
                )
            engine = str(path)
            extra_mounts: list[str] = []
            if browser_mounts:
                from migration_agent.adapters.validation_backend import file_digest, safe_path

                worker = safe_path(Path(browser_mounts.worker.path))
                artifacts = safe_path(Path(browser_mounts.artifacts))
                if (
                    file_digest(worker) != browser_mounts.worker.sha256
                    or not artifacts.is_dir()
                    or artifacts.is_relative_to(self.staging_root)
                    or (self.source_root and artifacts.is_relative_to(self.source_root))
                    or any("," in str(p) for p in (worker, artifacts))
                ):
                    raise ValueError(
                        "BROWSER_MOUNT_INVALID: verified worker and separate capture root required."
                    )
                extra_mounts = [
                    "--mount",
                    f"type=bind,source={worker},target=/agent/browser_worker.cjs,readonly",
                    "--mount",
                    f"type=bind,source={artifacts},target=/artifacts",
                ]
            launch = [
                engine,
                "run",
                "--rm",
                "--pull=never",
                "--name",
                container_name,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=128",
                "--memory=512m",
                "--cpus=1",
                "--user=65534:65534",
                "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
                "--mount",
                f"type=bind,source={working_dir.resolve()},target=/workspace,readonly",
                "--workdir=/workspace",
                "--env=NODE_ENV=test",
                "--env=npm_config_offline=true",
                "--env=npm_config_ignore_scripts=true",
                "--env=HOME=/tmp",
                *extra_mounts,
                self.container_image,
                command.executable,
                *command.args,
            ]
            if "," in str(working_dir.resolve()):
                raise ValueError("STAGING_PATH_INVALID: container mount path contains a delimiter.")
        else:
            launch = [command.executable, *command.args]
            env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        fence()
        start = time.monotonic()
        process: subprocess.Popen[bytes] | None = None
        output = bytearray()
        digest = hashlib.sha256()
        mutex = threading.Lock()
        timed_out = False
        try:
            process = subprocess.Popen(
                launch,
                cwd=working_dir,
                env=env,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name != "nt",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )

            def drain(stream: object) -> None:
                if stream is None:
                    return
                from typing import BinaryIO, cast

                handle = cast(BinaryIO, stream)
                for chunk in iter(lambda: handle.read(4096), b""):
                    with mutex:
                        digest.update(chunk)
                        remaining = command.max_output_bytes - len(output)
                        if remaining > 0:
                            output.extend(chunk[:remaining])
                handle.close()

            threads = [
                threading.Thread(target=drain, args=(stream,), daemon=True)
                for stream in (process.stdout, process.stderr)
            ]
            for thread in threads:
                thread.start()
            while process.poll() is None:
                fence()
                if time.monotonic() - start >= command.timeout_seconds:
                    timed_out = True
                    self._stop(process)
                    break
                time.sleep(0.1)
            for thread in threads:
                thread.join(timeout=2)
            if any(thread.is_alive() for thread in threads):
                self._stop(process)
                raise ValueError("CHILD_PROCESS_UNQUIESCENT: validation retained output handles.")
            code = process.wait(timeout=2)
            text = RedactionPolicy().redact_text(bytes(output).decode("utf-8", errors="replace"))
            status = (
                ValidationStatus.TIMED_OUT
                if timed_out
                else ValidationStatus.PASSED
                if code == 0
                else ValidationStatus.FAILED
            )
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=status,
                exit_code=code,
                duration_ms=int((time.monotonic() - start) * 1000),
                sanitized_output=text,
                output_digest=f"sha256:{digest.hexdigest()}",
                diagnostics=tuple(
                    line[:512]
                    for line in text.splitlines()
                    if any(word in line.lower() for word in ("error", "fail", "exception"))
                )[:10],
            )
        except OSError:
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=ValidationStatus.FAILED,
                exit_code=None,
                diagnostics=(
                    "Validation executable unavailable; install local toolchain in staging.",
                ),
            )
        finally:
            cleanup_error = False
            if not self.fixture_execution:
                try:
                    cleaned = subprocess.run(
                        [engine, "rm", "--force", container_name],
                        capture_output=True,
                        shell=False,
                        timeout=5,
                        env=env,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    cleanup_error = bool(cleaned.returncode) and (
                        b"no such container" not in cleaned.stderr.lower()
                    )
                except (OSError, subprocess.TimeoutExpired):
                    cleanup_error = True
            if process:
                self._stop(process)
            if cleanup_error:
                raise ValueError("CONTAINER_CLEANUP_UNVERIFIED: inspect the validation container.")
