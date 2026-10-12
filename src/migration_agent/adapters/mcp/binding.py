"""Project root binding and identity containment for MCP server."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.domain.redaction import RedactionPolicy


class ProjectBinding:
    """Encapsulates safe binding to a single authoritative source project root."""

    def __init__(self, project_root: str | Path) -> None:
        raw_path = Path(project_root) if isinstance(project_root, str) else project_root
        try:
            resolved = raw_path.resolve()
        except (OSError, RuntimeError) as err:
            raise ValueError(f"Cannot resolve project root '{project_root}': {err}") from err

        if not resolved.exists():
            raise ValueError(f"Project root does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"Project root is not a directory: {resolved}")

        self._project_root = resolved
        self._project_id = self._determine_project_id(resolved)

    @property
    def project_root(self) -> Path:
        """Absolute canonical path to the bound project root."""
        return self._project_root

    @property
    def project_id(self) -> str:
        """Authoritative project identifier bound to this server instance."""
        return self._project_id

    @staticmethod
    def _determine_project_id(root: Path) -> str:
        manifest = GitGovernanceAdapter().get_manifest(str(root))
        if manifest is not None:
            validate_identifier(manifest.project_id, "manifest project_id")
        name = re.sub(r"[^a-zA-Z0-9_-]", "-", root.name).strip("-")[:24] or "project"
        if RedactionPolicy().contains_secret(name):
            name = "project"
        digest = hashlib.sha256(os.path.normcase(str(root)).encode("utf-8")).hexdigest()[:24]
        return f"{name}-{digest}"

    def validate_record_root(self, source_root: str) -> None:
        """Reject foreign records without returning their root or contents."""
        if not Path(source_root).is_absolute() or Path(source_root).resolve() != self.project_root:
            raise ValueError("PROJECT_MISMATCH: record does not belong to the bound repository.")

    def validate_storage_roots(self, state_dir: Path, staging_root: Path | None = None) -> Path:
        """Reject overlap before operational writers are constructed."""
        state = state_dir.expanduser().resolve()
        roots = [self.project_root, state]
        if staging_root is not None:
            roots.append(staging_root.expanduser().resolve())
        for index, first in enumerate(roots):
            for second in roots[index + 1 :]:
                if first.is_relative_to(second) or second.is_relative_to(first):
                    raise ValueError(
                        "UNSAFE_ROOT_OVERLAP: source, state, and staging must be distinct."
                    )
        return state

    def validate_project_id(self, project_id: str) -> None:
        """Validate that the provided project_id matches the bound project."""
        if not project_id or not isinstance(project_id, str):
            raise ValueError("project_id must be a non-empty string.")

        cleaned = project_id.strip()
        if not cleaned:
            raise ValueError("project_id must not be blank.")

        if ".." in cleaned or "/" in cleaned or "\\" in cleaned or "\x00" in cleaned:
            raise ValueError(
                f"Invalid project_id '{project_id}': "
                "path traversal and separator characters are prohibited."
            )

        if cleaned != self._project_id:
            raise ValueError(
                f"Project ID mismatch: requested '{cleaned}', but server is bound "
                f"to project '{self._project_id}' at '{self._project_root}'."
            )

    def resolve_in_project(self, relative_path: str) -> Path:
        """Resolve and verify that a relative path stays confined within the project root."""
        if not relative_path or not relative_path.strip():
            raise ValueError("relative_path must be a non-empty string.")

        if "\x00" in relative_path:
            raise ValueError("Path contains null bytes.")

        target = (self._project_root / relative_path).resolve()
        if not target.is_relative_to(self._project_root):
            raise ValueError(
                f"Path traversal detected: path '{relative_path}' "
                f"escapes project root '{self._project_root}'."
            )

        return target


def validate_identifier(value: str, label: str) -> str:
    """Validate bounded opaque identifiers; they are never interpreted as paths."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"INVALID_ID: {label} must be a non-empty string.")
    if ".." in cleaned or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", cleaned):
        raise ValueError(f"INVALID_ID: {label} contains prohibited traversal characters or length.")
    return cleaned
