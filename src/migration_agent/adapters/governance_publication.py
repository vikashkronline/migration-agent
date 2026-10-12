"""Read immutable Git objects for a trusted external pre-receive/required-check runner."""

import os
import re
import shutil
import subprocess
from pathlib import Path

from migration_agent.adapters.access_rules import SECURITY_FILES, SECURITY_FOLDERS, rule_text_digest
from migration_agent.adapters.access_store import AccessPointer
from migration_agent.domain.access import AccessDenied, AccessRevision
from migration_agent.domain.governance_publication import GovernancePublication
from migration_agent.domain.redaction import RedactionPolicy


class GitPublicationReader:
    def __init__(self, governance: Path) -> None:
        self.root = governance.resolve()
        executable = shutil.which("git")
        if not executable or Path(executable).resolve().is_relative_to(self.root):
            raise ValueError(
                "TRUSTED_GIT_REQUIRED: use an installed Git outside candidate directories."
            )
        self.executable = str(Path(executable).resolve())

    def _git(self, *args: str) -> bytes:
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="")
        result = subprocess.run(
            [
                self.executable,
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(self.root),
                *args,
            ],
            capture_output=True,
            env=env,
            shell=False,
            timeout=20,
        )
        if result.returncode or len(result.stdout) > 2_000_000:
            raise AccessDenied("PUBLICATION_UNAVAILABLE: bounded Git objects are required.")
        return result.stdout

    def read(self, commit_id: str) -> GovernancePublication:
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit_id):
            raise ValueError("PUBLICATION_REF_INVALID: supply an exact immutable commit ID.")
        entries: dict[str, str] = {}
        for entry in self._git("ls-tree", "-rz", commit_id, "--", ".agent").split(b"\0"):
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, blob = metadata.split()
            path = raw_path.decode("utf-8")
            controlled = (
                path in SECURITY_FILES
                or path.startswith(".agent/decisions/")
                or path.startswith(".agent/access/")
                or any(path.startswith(folder + "/") for folder in SECURITY_FOLDERS)
            )
            if controlled:
                if (
                    mode not in {b"100644", b"100755"}
                    or kind != b"blob"
                    or RedactionPolicy.is_sensitive_path(Path(path))
                ):
                    raise AccessDenied(
                        "PUBLICATION_PATH_INVALID: governance needs regular public files."
                    )
                entries[path] = blob.decode("ascii")
            if len(entries) > 11000:
                raise AccessDenied(
                    "PUBLICATION_TOO_LARGE: protected governance exceeds its file budget."
                )

        def read(path: str) -> str:
            blob = entries.get(path)
            if not blob or int(self._git("cat-file", "-s", blob)) > 2_000_000:
                raise AccessDenied("PUBLICATION_INCOMPLETE: a bounded signed record is missing.")
            text = self._git("cat-file", "blob", blob).decode("utf-8")
            if RedactionPolicy().contains_secret(text):
                raise AccessDenied(
                    "PUBLICATION_SECRET_REJECTED: governance cannot contain credentials."
                )
            return text

        pointer = AccessPointer.model_validate_json(read(".agent/access/current.json"))
        revisions: dict[str, AccessRevision] = {}
        for path in sorted(entries):
            if re.fullmatch(
                r"\.agent/access/revisions/rev-[0-9a-f]{16}(?:[0-9a-f]{8}){0,2}/manifest\.json",
                path,
            ):
                revision = AccessRevision.model_validate_json(read(path))
                if path.split("/")[3] != revision.proposal.revision_locator:
                    raise AccessDenied(
                        "PUBLICATION_LOCATOR_INVALID: revision path differs from exact approval."
                    )
                digest = revision.proposal.candidate.digest
                if digest in revisions:
                    raise AccessDenied(
                        "PUBLICATION_DUPLICATE: revision digest has multiple records."
                    )
                revisions[digest] = revision
        chain: list[AccessRevision] = []
        current_digest: str | None = pointer.digest
        while current_digest:
            current_revision = revisions.get(current_digest)
            if not current_revision or len(chain) >= 10000:
                raise AccessDenied(
                    "PUBLICATION_INCOMPLETE: signed revision chain is missing or cyclic."
                )
            chain.append(current_revision)
            current_digest = current_revision.proposal.candidate.previous_digest
        if (
            chain[0].proposal.candidate.revision != pointer.revision
            or chain[0].proposal.revision_locator != pointer.locator
        ):
            raise AccessDenied(
                "PUBLICATION_POINTER_INVALID: active pointer differs from the signed revision."
            )
        rules = {
            path: rule_text_digest(path, read(path))
            for path in sorted(entries)
            if path in SECURITY_FILES
            or any(path.startswith(folder + "/") for folder in SECURITY_FOLDERS)
        }
        if ".agent/architecture.json" in rules:
            from migration_agent.domain.stack import ArchitectureManifest

            manifest = ArchitectureManifest.model_validate_json(read(".agent/architecture.json"))
            for path in manifest.decision_digests:
                if not re.fullmatch(r"\.agent/decisions/[A-Za-z0-9_-]+\.md", path):
                    raise AccessDenied("PUBLICATION_PATH_INVALID: unsafe sealed decision path.")
                rules[path] = rule_text_digest(path, read(path))
        return GovernancePublication(
            commit_id=commit_id, revisions=tuple(reversed(chain)), rule_digests=rules
        )
