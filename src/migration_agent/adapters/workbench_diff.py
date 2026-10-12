"""Bounded exact-base review projection; neither source nor workflow state is changed."""

import difflib
import subprocess
from pathlib import Path

from migration_agent.adapters.project_evidence import LocalProjectEvidence
from migration_agent.application.workbench import DiffHunk, DiffLine, WorkFileDiff
from migration_agent.domain.changeset import (
    ChangeSet,
    FileChange,
    FileOperation,
    compute_changeset_digest,
)
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.ports.frameworks import FrameworkAdapterRegistry


def project_file_diff(
    root: Path, project: str, node: str, revision: str, changeset: ChangeSet, change: FileChange
) -> WorkFileDiff:
    result = WorkFileDiff(
        project_id=project,
        node_id=node,
        revision=revision,
        changeset_digest=changeset.changeset_digest,
        base_revision=changeset.base_revision,
        path=change.path,
        operation=change.operation.value,
        file_mode=change.file_mode.value,
    )
    try:
        if change.old_path is not None:
            raise ValueError("Unsupported rename; inspect this artifact with the CLI.")
        if changeset.destination:
            if compute_changeset_digest(changeset) != changeset.changeset_digest:
                raise ValueError("Destination base snapshot differs from the recorded digest.")
            old = (
                change.base_content_bytes.decode("utf-8")
                if change.base_content_bytes is not None
                else None
            )
            result = result.model_copy(update={"base_revision": changeset.destination.fingerprint})
        else:
            old = LocalProjectEvidence(root, FrameworkAdapterRegistry(())).read_base_text(
                changeset.base_revision, change.path
            )
        if (old is not None) == (change.operation == FileOperation.CREATE):
            raise ValueError("The operation does not match the recorded base file.")
        data = change.content_bytes or b""
        new = "" if change.operation == FileOperation.DELETE else data.decode("utf-8")
        if len(data) > 32768 or "\0" in new or RedactionPolicy().contains_secret(new):
            raise ValueError("Binary, protected or oversized proposed content is unavailable.")
        before, after = (old or "").splitlines(keepends=True), new.splitlines(keepends=True)
        if len(before) + len(after) > 4000:
            raise ValueError("This file exceeds the 4,000-line preview budget.")
        hunks = []
        for group in difflib.SequenceMatcher(
            None, before, after, autojunk=False
        ).get_grouped_opcodes(3):
            lines: list[DiffLine] = []
            for tag, i, end_i, j, end_j in group:
                if tag == "equal":
                    lines.extend(
                        DiffLine(
                            kind="context", old_line=k + 1, new_line=j + k - i + 1, text=before[k]
                        )
                        for k in range(i, end_i)
                    )
                else:
                    lines.extend(
                        DiffLine(kind="remove", old_line=k + 1, text=before[k])
                        for k in range(i, end_i)
                    )
                    lines.extend(
                        DiffLine(kind="add", new_line=k + 1, text=after[k]) for k in range(j, end_j)
                    )
            hunks.append(
                DiffHunk(
                    old_start=group[0][1] + (1 if group[-1][2] > group[0][1] else 0),
                    old_count=group[-1][2] - group[0][1],
                    new_start=group[0][3] + (1 if group[-1][4] > group[0][3] else 0),
                    new_count=group[-1][4] - group[0][3],
                    lines=tuple(lines),
                )
            )
        return result.model_copy(update={"hunks": tuple(hunks)})
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError):
        return result.model_copy(
            update={
                "available": False,
                "reason": "Exact base or supported text content is unavailable. Preview limits are "
                "32 KiB per side and 4,000 combined lines. Inspect this artifact with the CLI/IDE.",
            }
        )
