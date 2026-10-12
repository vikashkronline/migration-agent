"""Guarded evidence reads and bounded Git metadata collection."""

import os
import re
import shutil
import subprocess
from pathlib import Path

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.filesystem import SafeFilesystemInspector, read_repository_text
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.application.inventory import InventoryService
from migration_agent.domain.changeset import compute_worktree_fingerprint
from migration_agent.domain.host_workflow import RepositoryState, normalized_path
from migration_agent.domain.inventory import ProjectInventory
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.ports.frameworks import FrameworkAdapterRegistry
from migration_agent.ports.governance import ProjectPolicy


class LocalProjectEvidence:
    def __init__(
        self,
        root: Path,
        registry: FrameworkAdapterRegistry,
        authorization: ProjectAuthorization | None = None,
    ) -> None:
        self.root = root.resolve()
        self.registry = registry
        self.authorization = authorization
        self._root_commits: dict[str, str] = {}

    def inventory(self) -> ProjectInventory:
        return InventoryService(SafeFilesystemInspector(), self.registry).inventory(self.root)

    def read_text(self, path: str) -> str:
        return read_repository_text(self.root, path)

    def _git_bytes(self, *args: str) -> bytes:
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        env.update(GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="")
        executable = shutil.which("git", path=env.get("PATH"))
        if not executable:
            raise ValueError("GIT_STATE_UNAVAILABLE: a trusted Git installation is required.")
        trusted_path = Path(executable).resolve()
        if trusted_path.is_relative_to(self.root):
            raise ValueError(
                "EXECUTABLE_UNTRUSTED: repository executables cannot inspect Git state."
            )
        result = subprocess.run(
            [str(trusted_path), "--no-optional-locks", "-c", "core.fsmonitor=false", *args],
            cwd=self.root,
            env=env,
            capture_output=True,
            shell=False,
            timeout=30,
        )
        if result.returncode or len(result.stdout) > 65536:
            raise ValueError("GIT_STATE_UNAVAILABLE: a bounded Git repository is required.")
        return result.stdout

    def _git(self, *args: str) -> str:
        return (
            RedactionPolicy()
            .redact_text(self._git_bytes(*args).decode("utf-8", errors="replace"))
            .rstrip("\r\n")
        )

    def read_base_text(self, revision: str, path: str) -> str | None:
        if not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", revision):
            raise ValueError("DIFF_BASE_UNAVAILABLE: recorded base is not an exact Git commit.")
        normalized_path(path)
        if RedactionPolicy.is_sensitive_path(Path(path)):
            raise ValueError("DIFF_CONTENT_UNAVAILABLE: protected content.")
        entry = self._git_bytes("ls-tree", "-z", revision, "--", ":(literal)" + path)
        if not entry:
            return None
        metadata, recorded_path = entry.rstrip(b"\0").split(b"\t", 1)
        mode, kind, blob = metadata.split(b" ")
        if recorded_path.decode("utf-8") != path or mode not in {b"100644", b"100755"}:
            raise ValueError("DIFF_CONTENT_UNAVAILABLE: unsupported base file mode.")
        if kind != b"blob" or not re.fullmatch(rb"[a-f0-9]{40}|[a-f0-9]{64}", blob):
            raise ValueError("DIFF_CONTENT_UNAVAILABLE: unsupported base object.")
        identity = blob.decode("ascii")
        if int(self._git("cat-file", "-s", identity)) > 32768:
            raise ValueError("DIFF_CONTENT_UNAVAILABLE: base file exceeds the preview budget.")
        data = self._git_bytes("cat-file", "blob", identity)
        text = data.decode("utf-8")
        if "\0" in text or RedactionPolicy().contains_secret(text):
            raise ValueError("DIFF_CONTENT_UNAVAILABLE: binary or protected base content.")
        return text

    def repository_state(self) -> RepositoryState:
        identity = self._git("rev-parse", "--show-toplevel", "HEAD").splitlines()
        if len(identity) != 2 or Path(identity[0]).resolve() != self.root:
            raise ValueError("GIT_ROOT_MISMATCH: bind the Git working tree root.")
        revision = identity[1]
        if revision not in self._root_commits:
            roots = self._git("rev-list", "--max-parents=0", revision).splitlines()
            self._root_commits[revision] = ",".join(sorted(roots))
        status = self._git("status", "--porcelain=v1", "--untracked-files=all")
        return RepositoryState(
            revision=revision,
            root_commit=self._root_commits[revision],
            fingerprint=compute_worktree_fingerprint(self.root),
            clean=not status,
            dirty_paths=tuple(line[3:] for line in status.splitlines()[:100]),
        )

    def policy_digest(self) -> str:
        if self.authorization:
            return self.authorization.project_policy_digest()
        return GitGovernanceAdapter().get_policy_digest(str(self.root))

    def policy(self) -> ProjectPolicy:
        if self.authorization:
            return self.authorization.project_policy()
        return GitGovernanceAdapter().get_policy(str(self.root))
