"""Application-owned port for allowlisted subprocess execution in staging."""

from pathlib import Path
from typing import Protocol

from migration_agent.domain import ValidationCommand, ValidationResult


class CommandRunnerPort(Protocol):
    """Boundary for executing allowlisted commands confined strictly within a staging workspace."""

    def run_command(
        self,
        command: ValidationCommand,
        working_dir: Path,
    ) -> ValidationResult:
        """Execute an allowlisted command with environment sanitization and bounded timeouts."""
