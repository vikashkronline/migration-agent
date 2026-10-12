"""Installed OpenSSH tools and a bounded signing environment shared by human channels."""

import os
from pathlib import Path

from migration_agent.adapters.os_identity import (
    windows_program_data_directory,
    windows_system_directory,
)


def ssh_keygen() -> str:
    candidates = [Path("/usr/bin/ssh-keygen"), Path("/bin/ssh-keygen")]
    if os.name == "nt":
        candidates = [windows_system_directory() / "OpenSSH/ssh-keygen.exe"]
    executable = next((path.resolve() for path in candidates if path.is_file()), None)
    if executable is None:
        raise ValueError("SSH_AGENT_REQUIRED: install OpenSSH and enroll your public signing key.")
    return str(executable)


def signing_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "SSH_AUTH_SOCK"}
    }
    if os.name == "nt":
        environment["PROGRAMDATA"] = str(windows_program_data_directory())
    return environment
