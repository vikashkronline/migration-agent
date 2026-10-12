"""Trusted launcher selection, native consent, and shared execution provenance."""

import hashlib
import importlib
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.approval_proof import LocalApprovalProof
from migration_agent.adapters.fenced_validation import (
    BROWSER_COMMAND,
    BrowserMounts,
    FencedValidationRunner,
    validation_commands,
)
from migration_agent.adapters.native_process import launch_native
from migration_agent.adapters.project_evidence import LocalProjectEvidence
from migration_agent.adapters.workflow_store import SqliteWorkflowStore
from migration_agent.application.host_proposals import HostProposalService
from migration_agent.config import Settings
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.execution import (
    ExecutionPolicy,
    ExecutionProvenance,
    NativeExecutionConsent,
    ToolIdentity,
    ValidationMode,
)
from migration_agent.domain.host_workflow import (
    Lifecycle,
    ValidationExecution,
    WorkflowRecord,
    WriterLease,
)
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.validation import (
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
)


def safe_path(path: Path) -> Path:
    candidate = path.expanduser().absolute()
    for component in (candidate, *candidate.parents):
        if component.is_symlink() or component.is_junction():
            raise ValueError("NATIVE_PATH_UNSAFE: links and junctions are unsupported.")
    return candidate.resolve()


def _opened_path(handle: BinaryIO) -> Path:
    if os.name == "nt":
        ctypes = importlib.import_module("ctypes")
        wintypes = importlib.import_module("ctypes.wintypes")
        msvcrt = importlib.import_module("msvcrt")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        final_path = kernel.GetFinalPathNameByHandleW
        final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        final_path.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        length = final_path(msvcrt.get_osfhandle(handle.fileno()), buffer, len(buffer), 0)
        if length == 0 or length >= len(buffer):
            raise ValueError("NATIVE_PATH_UNSAFE: opened file identity is unavailable.")
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)
    if sys.platform == "linux":
        try:
            return Path(os.readlink(f"/proc/self/fd/{handle.fileno()}"))
        except OSError:
            raise ValueError("NATIVE_PATH_UNSAFE: opened file identity is unavailable.") from None
    raise ValueError("NATIVE_PATH_UNSAFE: opened file verification is unsupported.")


def file_digest(
    path: Path, verified_root: Path | None = None, fence: Callable[[], None] | None = None
) -> str:
    if fence:
        fence()
    if verified_root is None:
        safe_path(path)
    elif not path.is_relative_to(verified_root):
        raise ValueError("NATIVE_PATH_UNSAFE: file is outside the verified tree.")
    digest = hashlib.sha256()
    before = path.stat()
    with path.open("rb") as handle:
        if verified_root is not None:
            actual = _opened_path(handle)
            if actual != path or not actual.is_relative_to(verified_root):
                raise ValueError("NATIVE_PATH_UNSAFE: opened file escaped its verified tree.")
        opened = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ino,
        ):
            raise ValueError("NATIVE_INPUT_CHANGED: file changed while opening.")
        read_bytes = 0
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if fence:
                fence()
            read_bytes += len(chunk)
            if read_bytes > before.st_size:
                raise ValueError("NATIVE_INPUT_CHANGED: file grew while fingerprinting.")
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise ValueError("NATIVE_INPUT_CHANGED: file changed while fingerprinting.")
    return digest.hexdigest()


def tree_digest(
    root: Path,
    excluded: tuple[str, ...] = (),
    excluded_files: tuple[str, ...] = (),
    fence: Callable[[], None] | None = None,
) -> str:
    next_check = 0.0
    stopped: Exception | None = None
    pulse_lock = threading.Lock()

    def pulse() -> None:
        nonlocal next_check, stopped
        if fence is None:
            return
        with pulse_lock:
            if stopped is not None:
                raise stopped
            now = time.monotonic()
            if now >= next_check:
                try:
                    fence()
                except Exception as error:
                    stopped = error
                    raise
                next_check = time.monotonic() + 1

    pulse()
    root = safe_path(root)
    if not root.is_dir():
        raise ValueError("NATIVE_DEPENDENCIES_REQUIRED: prepare the external offline directory.")
    entries: list[tuple[str, Path]] = []
    total_bytes = 0
    for directory, dirs, names in os.walk(root, followlinks=False):
        pulse()
        for name in dirs:
            safe_path(Path(directory) / name)
        dirs[:] = sorted(
            name
            for name in dirs
            if (Path(directory) / name).relative_to(root).as_posix() not in excluded
        )
        for name in sorted(names):
            pulse()
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            if rel in excluded_files:
                continue
            if RedactionPolicy.is_sensitive_path(path):
                raise ValueError(
                    "NATIVE_INPUT_PROTECTED: excluded credential-shaped file "
                    f"{rel[:200]!r} was not read; provision a clean external "
                    "runtime dependency tree."
                )
            if not path.is_file():
                raise ValueError("NATIVE_PATH_UNSAFE: only regular input files are supported.")
            total_bytes += path.stat().st_size
            if total_bytes > 4 * 1024 * 1024 * 1024:
                raise ValueError("NATIVE_INPUT_TOO_LARGE: offline input byte budget exceeded.")
            entries.append((rel, path))
            if len(entries) > 100_000:
                raise ValueError("NATIVE_INPUT_TOO_LARGE: file budget exceeded.")
    entries.sort(key=lambda item: item[0])

    def fingerprint(path: Path) -> str:
        return file_digest(path, root, pulse)

    if len(entries) > 64:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="input-digest") as pool:
            digests = list(pool.map(fingerprint, (path for _, path in entries)))
    else:
        digests = [fingerprint(path) for _, path in entries]
    pulse()
    return compute_canonical_digest(
        [(relative, digest) for (relative, _), digest in zip(entries, digests, strict=True)]
    ).removeprefix("sha256:")


def repairable(path: str) -> bool:
    name = Path(path).name.casefold()
    return not (
        name
        in {
            "package.json",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "angular.json",
            "karma.conf.js",
        }
        or name.startswith(("tsconfig", "eslint", ".", "vite.config", "webpack.config"))
        or Path(path).suffix.casefold() in {".cmd", ".bat", ".ps1", ".sh"}
    )


class ValidationBackend:
    def __init__(
        self,
        settings: Settings,
        proposals: HostProposalService,
        store: SqliteWorkflowStore,
        staging: Path,
        state: Path,
        trust: Path,
    ) -> None:
        self.settings, self.proposals, self.store = settings, proposals, store
        self.staging, self.state, self.trust = staging, state, trust
        self.proof = LocalApprovalProof(trust, state)
        self.container = FencedValidationRunner(
            staging, container_image=settings.validation_image, source_root=proposals.root
        )
        self._local = threading.local()

    @contextmanager
    def _fingerprinting(self, fence: Callable[[], None] | None) -> Iterator[None]:
        previous = getattr(self._local, "input_fence", None)
        self._local.input_fence = fence or previous
        try:
            yield
        finally:
            self._local.input_fence = previous

    def _tree_digest(
        self, root: Path, excluded: tuple[str, ...] = (), excluded_files: tuple[str, ...] = ()
    ) -> str:
        fence = getattr(self._local, "input_fence", None)
        if fence:
            return tree_digest(root, excluded, excluded_files, fence)
        if excluded or excluded_files:
            return tree_digest(root, excluded, excluded_files)
        return tree_digest(root)

    def consent_status(self, record: WorkflowRecord) -> str:
        try:
            consent = self.store.get_native_consent(
                record.project_id, record.plan_id, record.step_id
            )
            return "EXPIRED" if datetime.now(UTC) >= consent.expires_at else "AUTHORIZED"
        except ValueError:
            return "NATIVE_CONSENT_REQUIRED"

    def _container_identity(self) -> tuple[ToolIdentity, ...]:
        if not self.settings.validation_image or not re.fullmatch(
            r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", self.settings.validation_image
        ):
            raise ValueError("ISOLATION_REQUIRED: configure a locally installed pinned image.")
        engine = shutil.which("docker")
        if engine is None:
            raise ValueError("ISOLATION_REQUIRED: install a trusted local Docker engine.")
        path = safe_path(Path(engine))
        if path.is_relative_to(self.proposals.root) or path.is_relative_to(self.staging):
            raise ValueError("EXECUTABLE_UNTRUSTED: repository engines cannot validate code.")
        identities: tuple[ToolIdentity, ...] = (
            ToolIdentity(path=str(path), sha256=file_digest(path)),
        )
        if self.settings.browser_validation_plan:
            worker = Path(__file__).with_name("browser_worker.cjs").resolve()
            identities += (ToolIdentity(path=str(worker), sha256=file_digest(worker)),)
        return identities

    def policy(self) -> ExecutionPolicy:
        mode = self.settings.effective_validation_mode
        project = self.proposals.evidence.policy()
        if project.execution_mode == "denied" or mode == ValidationMode.RESTRICTED:
            raise ValueError(
                "ISOLATION_REQUIRED: restricted mode does not execute code; "
                "select an authorized validation backend."
            )
        if project.execution_mode == "container" and mode != ValidationMode.CONTAINER:
            raise ValueError("EXECUTION_POLICY_UNSUPPORTED: project requires container validation.")
        if mode == ValidationMode.NATIVE and (
            project.native_network != "host"
            or project.native_filesystem_isolation
            or (project.native_hard_resource_limits and sys.platform != "win32")
        ):
            raise ValueError(
                "EXECUTION_POLICY_UNSUPPORTED: native cannot enforce the "
                "requested isolation or hard resource limits."
            )
        if mode == ValidationMode.NATIVE and sys.platform not in {"win32", "linux"}:
            raise ValueError(
                "EXECUTION_POLICY_UNSUPPORTED: native supervision requires Windows or Linux."
            )
        assurance = (
            AssuranceLevel.MODE_A
            if project.default_mode == "MODE_A"
            else self.settings.apply_minimum_assurance
        )
        if assurance == AssuranceLevel.MODE_C:
            raise ValueError("ASSURANCE_REQUIRED: native execution requires at least Mode B.")
        windows = mode == ValidationMode.NATIVE and sys.platform == "win32"
        browser_digest = None
        if self.settings.browser_validation_plan is not None:
            from migration_agent.adapters.browser_config import load_browser_plan

            browser_digest = load_browser_plan(self.settings).digest
        from migration_agent.adapters.visual_specialist import provider_disclosure

        return ExecutionPolicy(
            mode=mode,
            catalog_version=self.settings.validation_catalog,
            project_policy_digest=self.proposals.evidence.policy_digest(),
            minimum_assurance=assurance,
            network="host" if mode == ValidationMode.NATIVE else "none",
            filesystem="host" if mode == ValidationMode.NATIVE else "container",
            environment_policy="positive-fresh-home-v1"
            if mode == ValidationMode.NATIVE
            else "container-minimal-v1",
            output_directories=(".angular", "coverage", "dist")
            if mode == ValidationMode.NATIVE
            else (),
            process_limit=128 if windows or mode == ValidationMode.CONTAINER else None,
            memory_bytes=512 * 1024 * 1024 if windows or mode == ValidationMode.CONTAINER else None,
            cpu_seconds=60 if windows else None,
            cpu_count=1 if mode == ValidationMode.CONTAINER else None,
            supervision="windows-atomic-job-v1"
            if windows
            else "linux-pipe-guardian-v1"
            if mode == ValidationMode.NATIVE
            else "docker-cleanup-v1",
            browser_plan_digest=browser_digest,
            browser_provider_disclosure=provider_disclosure(self.settings)
            if browser_digest
            else None,
            browser_catalog="browser-v1" if browser_digest else None,
            browser_worker_digest=file_digest(Path(__file__).with_name("browser_worker.cjs"))
            if browser_digest
            else None,
            browser_environment_policy=(
                "windows-known-folders-fresh-browser-v1"
                if windows
                else "positive-fresh-home-v1"
                if mode == ValidationMode.NATIVE
                else "container-minimal-v1"
            )
            if browser_digest
            else None,
        )

    def _external(self, configured: Path | None) -> Path:
        if configured is None:
            raise ValueError(
                "NATIVE_TOOLCHAIN_REQUIRED: configure external toolchain and "
                "offline node_modules roots."
            )
        path = safe_path(configured)
        if not path.is_dir() or any(
            path.is_relative_to(root) or root.is_relative_to(path)
            for root in (
                self.proposals.root,
                self.staging,
                self.state,
                self.trust,
                *((self.settings.final_target_root,) if self.settings.final_target_root else ()),
            )
        ):
            raise ValueError(
                "EXECUTABLE_UNTRUSTED: toolchain/dependencies must be separate "
                "from source, staging, state and trust."
            )
        return path

    def _tools(self, commands: tuple[ValidationCommand, ...]) -> tuple[ToolIdentity, ...]:
        root = self._external(self.settings.native_toolchain_root)
        node = root / ("node.exe" if os.name == "nt" else "bin/node")
        entries = {
            "npm": "node_modules/npm/bin/npm-cli.js",
            "tsc": "node_modules/typescript/bin/tsc",
            "ng": "node_modules/@angular/cli/bin/ng.js",
        }
        identities = {str(node): ToolIdentity(path=str(node), sha256=file_digest(node))}
        # Bind supporting toolchain modules, not only CLI entry points.
        modules = root / "node_modules"
        identities[str(modules)] = ToolIdentity(
            path=str(modules), sha256=self._tree_digest(modules)
        )
        if os.name == "nt" and any(command.executable == "npm" for command in commands):
            shell = safe_path(
                Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/cmd.exe"
            )
            if shell.is_relative_to(self.proposals.root) or shell.is_relative_to(self.staging):
                raise ValueError(
                    "EXECUTABLE_UNTRUSTED: system shell cannot belong to a repository."
                )
            identities[str(shell)] = ToolIdentity(path=str(shell), sha256=file_digest(shell))
        if sys.platform == "linux":
            python = safe_path(Path(sys.executable).resolve())
            if any(python.is_relative_to(p) for p in (self.proposals.root, self.staging)):
                raise ValueError(
                    "EXECUTABLE_UNTRUSTED: guardian Python must be installed outside "
                    "source/staging."
                )
            guardian = Path(__file__).with_name("native_guardian.py").resolve()
            if guardian.is_relative_to(self.proposals.root) or guardian.is_relative_to(
                self.staging
            ):
                raise ValueError(
                    "EXECUTABLE_UNTRUSTED: install the agent outside selected source/staging."
                )
            for path in (python, guardian):
                identities[str(path)] = ToolIdentity(path=str(path), sha256=file_digest(path))
        for command in commands:
            if command not in tuple(
                c
                for values in validation_commands(self.settings.validation_catalog).values()
                for c in values
            ):
                raise ValueError("COMMAND_REJECTED: only the selected fixed catalog is accepted.")
            entry = root / entries[command.executable]
            identities[str(entry)] = ToolIdentity(path=str(entry), sha256=file_digest(entry))
        if self.settings.native_browser_path:
            browser = safe_path(self.settings.native_browser_path)
            if not browser.is_file() or any(
                browser.is_relative_to(path)
                for path in (self.proposals.root, self.staging, self.state, self.trust)
            ):
                raise ValueError(
                    "EXECUTABLE_UNTRUSTED: browser must be installed outside workflow roots."
                )
            identities[str(browser)] = ToolIdentity(path=str(browser), sha256=file_digest(browser))
        if self.settings.browser_validation_plan is not None:
            if self.settings.native_browser_path is None:
                raise ValueError(
                    "BROWSER_REQUIRED: configure a verified installed Chromium browser."
                )
            worker = Path(__file__).with_name("browser_worker.cjs").resolve()
            if any(worker.is_relative_to(p) for p in (self.proposals.root, self.staging)):
                raise ValueError("EXECUTABLE_UNTRUSTED: install the agent outside selected source.")
            entry = root / "node_modules/playwright-core/index.js"
            for path in (worker, entry):
                identities[str(path)] = ToolIdentity(path=str(path), sha256=file_digest(path))
        return tuple(identities[key] for key in sorted(identities))

    def _scope(self, record: WorkflowRecord) -> tuple[str, ...]:
        changeset = self.store.get_changeset(record.changeset_id or "")
        if not changeset:
            raise ValueError("CHANGESET_REQUIRED: stage before authorizing execution.")
        return tuple(sorted(change.path for change in changeset.changes))

    def _dependency_digest(self, toolchain: tuple[ToolIdentity, ...]) -> str:
        dependencies = self._external(self.settings.native_dependencies_root)
        matching = next(
            (identity for identity in toolchain if Path(identity.path) == dependencies), None
        )
        return matching.sha256 if matching else self._tree_digest(dependencies)

    def _reject_impersonation(self, workspace: Path) -> None:
        names = {
            name + suffix
            for name in ("node", "npm", "tsc", "ng", "pytest")
            for suffix in ("", ".exe", ".com", ".cmd", ".bat", ".ps1")
        }
        for root in (self.proposals.root, workspace):
            if any(path.name.casefold() in names for path in root.iterdir()):
                raise ValueError(
                    "EXECUTABLE_UNTRUSTED: source/stage cannot impersonate validation tools."
                )

    def _inputs(self, record: WorkflowRecord, scope: tuple[str, ...] = ()) -> str:
        policy = self.policy()
        root = safe_path(Path(record.staging_path or ""))
        if root.parent != self.staging:
            raise ValueError("STAGING_PATH_INVALID: expected a distinct staged workspace.")
        self._reject_impersonation(root)
        if any(
            path.split("/")[0].casefold() in {*policy.output_directories, "node_modules"}
            for path in self._scope(record)
        ):
            raise ValueError(
                "NATIVE_OUTPUT_OVERLAP: changes cannot target declared "
                "output/dependency directories."
            )
        for output in policy.output_directories:
            if (self.proposals.root / output).exists():
                evidence = self.proposals.evidence
                if not isinstance(evidence, LocalProjectEvidence) or evidence._git(
                    "ls-files", "--", output
                ):
                    raise ValueError(
                        "NATIVE_OUTPUT_OVERLAP: a declared output directory "
                        "contains tracked source inputs."
                    )
        return self._tree_digest(
            root,
            (*policy.output_directories, "node_modules"),
            tuple(path for path in scope if repairable(path)),
        )

    def consent_request(
        self,
        record: WorkflowRecord,
        commands: tuple[ValidationCommand, ...],
        repair_budget: int,
        fence: Callable[[], None] | None = None,
    ) -> NativeExecutionConsent:
        with self._fingerprinting(fence):
            return self._consent_request(record, commands, repair_budget)

    def _consent_request(
        self, record: WorkflowRecord, commands: tuple[ValidationCommand, ...], repair_budget: int
    ) -> NativeExecutionConsent:
        policy = self.policy()
        if policy.mode != ValidationMode.NATIVE or record.state not in {
            Lifecycle.STAGE_VERIFIED,
            Lifecycle.VALIDATION_FAILED,
            Lifecycle.VALIDATION_PASSED,
            Lifecycle.APPROVAL_PENDING,
            Lifecycle.APPROVAL_RECORDED,
        }:
            raise ValueError(
                "NATIVE_STAGE_REQUIRED: select native mode and stage the current artifact first."
            )
        source = self.proposals.evidence.repository_state()
        if not source.clean or (source.revision, source.fingerprint) != (
            record.base_revision,
            record.worktree_fingerprint,
        ):
            raise ValueError("BASE_CHANGED: stage a plan from a clean source base.")
        scope = self._scope(record)
        now = datetime.now(UTC)
        access = self.proposals.authorization.require("execution.consent")
        assurance = policy.minimum_assurance
        if isinstance(self.proposals.authorization, ProjectAuthorization):
            current = self.proposals.authorization.service().store.read()
            roles = {role.role_id: role for role in current.roles}
            if any(
                member.status == "active"
                and member.principal_id != access.principal_id
                and member.os_identity
                and (member.expires_at is None or member.expires_at > int(now.timestamp()))
                and any("validation.run" in roles[role].capabilities for role in member.roles)
                for member in current.members
            ):
                assurance = AssuranceLevel.MODE_A
        toolchain = self._tools(commands)
        return NativeExecutionConsent(
            consent_id=f"consent-{uuid.uuid4().hex}",
            project_id=record.project_id,
            source_root=str(self.proposals.root),
            root_commit=record.root_commit,
            base_revision=record.base_revision,
            worktree_fingerprint=record.worktree_fingerprint,
            plan_id=record.plan_id,
            step_id=record.step_id,
            initial_changeset_id=record.changeset_id or "",
            policy_digest=policy.digest,
            profiles=tuple(sorted({command.profile for command in commands})),
            toolchain=toolchain,
            dependency_digest=self._dependency_digest(toolchain),
            immutable_input_digest=self._inputs(record, scope),
            approved_scope=scope,
            repair_budget=repair_budget,
            actor=self.proposals.actor,
            principal_id=access.principal_id,
            access_digest=access.access_digest,
            destination=record.destination,
            assurance_level=assurance,
            key_fingerprint=access.key_fingerprint if assurance == AssuranceLevel.MODE_A else None,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

    def _consent(
        self,
        record: WorkflowRecord,
        commands: tuple[ValidationCommand, ...],
        consent_id: str | None = None,
        verify_inputs: bool = True,
        capability: str = "validation.run",
    ) -> NativeExecutionConsent:
        self.proposals.authorization.require(capability)
        consent = self.store.get_native_consent(
            record.project_id, record.plan_id, record.step_id, consent_id
        )
        if not consent.access_digest or not consent.principal_id:
            raise ValueError(
                "NATIVE_CONSENT_INVALID: renew legacy consent under current project access."
            )
        if consent.destination != record.destination:
            raise ValueError(
                "NATIVE_CONSENT_SCOPE_CHANGED: authorize this exact destination snapshot."
            )
        self.proposals.authorization.require(capability, consent.access_digest)
        policy = self.policy()
        if not verify_inputs and consent.assurance_level == AssuranceLevel.MODE_A:
            if getattr(self._local, "verified_consent", None) != (
                consent.signing_digest,
                consent.signature,
            ):
                raise ValueError("NATIVE_CONSENT_INVALID: signed consent changed during execution.")
            self.proof.authority(
                record.project_id, consent.key_fingerprint or "", record.root_commit
            )
            proof_valid = True
        else:
            proof_valid = self.proof.verify(consent, record.root_commit)
        if (
            datetime.now(UTC) >= consent.expires_at
            or consent.created_at > datetime.now(UTC)
            or not proof_valid
        ):
            raise ValueError("NATIVE_CONSENT_INVALID: trusted unexpired human consent required.")
        if (
            policy.minimum_assurance == AssuranceLevel.MODE_A
            and consent.assurance_level != AssuranceLevel.MODE_A
        ):
            raise ValueError("ASSURANCE_REQUIRED: Mode A native consent required.")
        if (
            (
                consent.source_root,
                consent.project_id,
                consent.plan_id,
                consent.step_id,
                consent.root_commit,
                consent.base_revision,
                consent.worktree_fingerprint,
                consent.policy_digest,
            )
            != (
                str(self.proposals.root),
                record.project_id,
                record.plan_id,
                record.step_id,
                record.root_commit,
                record.base_revision,
                record.worktree_fingerprint,
                policy.digest,
            )
            or not set(self._scope(record)).issubset(consent.approved_scope)
            or not {command.profile for command in commands}.issubset(consent.profiles)
        ):
            raise ValueError(
                "NATIVE_CONSENT_SCOPE_CHANGED: base, policy or approved scope changed."
            )
        if verify_inputs:
            toolchain = self._tools(self._commands(consent))
            if (
                toolchain != consent.toolchain
                or self._dependency_digest(toolchain) != consent.dependency_digest
                or self._inputs(record, consent.approved_scope) != consent.immutable_input_digest
            ):
                raise ValueError(
                    "NATIVE_CONSENT_INPUT_CHANGED: toolchain, dependencies or "
                    "validation configuration changed."
                )
            self._local.verified_consent = (consent.signing_digest, consent.signature)
        return consent

    def _commands(self, consent: NativeExecutionConsent) -> tuple[ValidationCommand, ...]:
        return tuple(
            command
            for profile in consent.profiles
            for command in validation_commands(self.settings.validation_catalog)[profile]
        )

    def prepare(
        self, record: WorkflowRecord, commands: tuple[ValidationCommand, ...], lease: WriterLease
    ) -> ExecutionProvenance:
        access = self.proposals.authorization.require("validation.run")

        def fence() -> None:
            self.proposals.authorization.require("validation.run", access.access_digest)
            self.store.renew_lease(lease, 300)

        with self._fingerprinting(fence):
            return self._prepare(record, commands, lease)

    def _prepare(
        self, record: WorkflowRecord, commands: tuple[ValidationCommand, ...], lease: WriterLease
    ) -> ExecutionProvenance:
        policy = self.policy()
        if policy.mode == ValidationMode.CONTAINER:
            # The existing runner validates pinned image/engine and performs cleanup.
            provenance = ExecutionProvenance(
                backend=policy.mode,
                policy=policy,
                policy_digest=policy.digest,
                dependency_digest=self.settings.validation_image or "",
                toolchain=self._container_identity(),
                input_digest=record.staging_fingerprint or "",
            )
            self._local.context = (record, commands, provenance)
            return provenance
        if os.name == "nt":
            shell = importlib.import_module("ctypes").WinDLL("shell32")
            if shell.IsUserAnAdmin():
                raise ValueError(
                    "NATIVE_ELEVATED_CONTEXT: restart validation in a standard user session."
                )
        elif importlib.import_module("os").geteuid() == 0:
            raise ValueError("NATIVE_ELEVATED_CONTEXT: native validation must not run as root.")
        consent = self._consent(record, commands)
        self.store.use_native_consent(consent, record.changeset_id or "", lease)
        dependencies = self._external(self.settings.native_dependencies_root)
        workspace = Path(record.staging_path or "")
        installed = workspace / "node_modules"
        if not installed.exists():
            next_check = 0.0
            copied = 0

            def copy_file(source: str, target: str) -> str:
                nonlocal next_check, copied
                now = time.monotonic()
                if copied % 64 == 0 or now >= next_check:
                    self.store.renew_lease(lease, 300)
                    self._consent(record, commands, consent.consent_id, verify_inputs=False)
                    next_check = time.monotonic() + 1.0
                safe_path(Path(source))
                safe_path(Path(target))
                result = shutil.copyfile(source, target)
                copied += 1
                return result

            shutil.copytree(dependencies, installed, symlinks=False, copy_function=copy_file)
            self._consent(record, commands, consent.consent_id, verify_inputs=False)
        if self._tree_digest(installed) != consent.dependency_digest:
            raise ValueError(
                "NATIVE_DEPENDENCIES_CHANGED: staged offline dependencies differ from consent."
            )
        provenance = ExecutionProvenance(
            backend=policy.mode,
            policy=policy,
            policy_digest=policy.digest,
            consent_id=consent.consent_id,
            toolchain=consent.toolchain,
            dependency_digest=consent.dependency_digest,
            input_digest=self._inputs(record),
        )
        self._local.context = (record, commands, provenance)
        return provenance

    def verify_browser_session(
        self, record: WorkflowRecord, provenance: ExecutionProvenance
    ) -> None:
        context = getattr(self._local, "context", None)
        if (
            context is None
            or context[0].changeset_digest != record.changeset_digest
            or context[2] != provenance
            or self.policy().digest != provenance.policy_digest
        ):
            raise ValueError("BROWSER_PROVIDER_POLICY_CHANGED: active validation context required.")
        if provenance.backend == ValidationMode.NATIVE:
            self._consent(record, context[1], provenance.consent_id, verify_inputs=False)

    def completed(
        self,
        provenance: ExecutionProvenance,
        record: WorkflowRecord,
        fence: Callable[[], None] | None = None,
    ) -> ExecutionProvenance:
        with self._fingerprinting(fence):
            return self._completed(provenance, record)

    def _completed(
        self, provenance: ExecutionProvenance, record: WorkflowRecord
    ) -> ExecutionProvenance:
        if provenance.backend == ValidationMode.NATIVE:
            if (
                self._inputs(record) != provenance.input_digest
                or self._tree_digest(Path(record.staging_path or "") / "node_modules")
                != provenance.dependency_digest
            ):
                raise ValueError(
                    "NATIVE_INPUT_CHANGED: validation modified staged inputs or dependencies."
                )
            self._consent(record, self._local.context[1], provenance.consent_id)
        elif self._container_identity() != provenance.toolchain:
            raise ValueError("EXECUTABLE_UNTRUSTED: Docker identity changed during validation.")
        return provenance.model_copy(update={"cleanup_verified": True})

    def verify_execution(
        self,
        execution: ValidationExecution,
        record: WorkflowRecord,
        fence: Callable[[], None] | None = None,
    ) -> None:
        with self._fingerprinting(fence):
            self._verify_execution(execution, record)

    def _verify_execution(self, execution: ValidationExecution, record: WorkflowRecord) -> None:
        evidence = execution.provenance
        if (
            execution.schema_version not in {2, 3}
            or evidence is None
            or not evidence.cleanup_verified
            or evidence.policy_digest != self.policy().digest
        ):
            raise ValueError(
                "VALIDATION_BACKEND_UNSUPPORTED: revalidate using the effective backend and policy."
            )
        if evidence.backend == ValidationMode.NATIVE:
            commands = tuple(
                command
                for result in execution.results
                for command in validation_commands(self.settings.validation_catalog)[result.profile]
            )
            consent = self._consent(
                record, commands, evidence.consent_id, capability="evidence.read"
            )
            if (
                evidence.toolchain != consent.toolchain
                or evidence.dependency_digest != consent.dependency_digest
                or evidence.input_digest != self._inputs(record)
                or self._tree_digest(Path(record.staging_path or "") / "node_modules")
                != evidence.dependency_digest
            ):
                raise ValueError(
                    "VALIDATION_NATIVE_INVALID: native provenance changed; revalidate."
                )
        elif (
            evidence.backend != ValidationMode.CONTAINER
            or evidence.dependency_digest != self.settings.validation_image
            or evidence.toolchain != self._container_identity()
            or evidence.input_digest != record.staging_fingerprint
        ):
            raise ValueError("VALIDATION_BACKEND_UNSUPPORTED: backend identity changed.")

    def run(
        self, command: ValidationCommand, working_dir: Path, fence: Callable[[], None]
    ) -> ValidationResult:
        if self.policy().mode == ValidationMode.CONTAINER:
            context = getattr(self._local, "context", None)
            if context is None:
                raise ValueError("VALIDATION_WORKFLOW_REQUIRED: use the shared staged workflow.")
            return self.container.run(
                command, working_dir, fence, engine_identity=context[2].toolchain[0]
            )
        context = getattr(self._local, "context", None)
        if context is None:
            raise ValueError("NATIVE_CONSENT_REQUIRED: use the shared staged workflow.")
        record, commands, provenance = context
        if command not in commands or working_dir != Path(record.staging_path or ""):
            raise ValueError("COMMAND_REJECTED: command/workspace outside consent.")
        consent = self._consent(record, commands, provenance.consent_id)
        node = next(
            identity.path
            for identity in consent.toolchain
            if Path(identity.path).name in {"node", "node.exe"}
        )
        root = self._external(self.settings.native_toolchain_root)
        entries = {
            "npm": "node_modules/npm/bin/npm-cli.js",
            "tsc": "node_modules/typescript/bin/tsc",
            "ng": "node_modules/@angular/cli/bin/ng.js",
        }
        argv = [node, str(root / entries[command.executable]), *command.args]
        return self._run_native(argv, command, working_dir, fence)

    def run_browser(
        self, request_path: Path, working_dir: Path, fence: Callable[[], None]
    ) -> ValidationResult:
        policy = self.policy()
        if not policy.browser_plan_digest:
            raise ValueError(
                "BROWSER_BACKEND_UNSUPPORTED: use explicitly consented native browser execution."
            )
        context = getattr(self._local, "context", None)
        if context is None or working_dir != Path(context[0].staging_path or ""):
            raise ValueError(
                "NATIVE_CONSENT_REQUIRED: browser execution requires the shared workflow."
            )
        path = safe_path(request_path)
        if not path.is_relative_to(self.state / "browser") or path.name != "request.json":
            raise ValueError(
                "BROWSER_REQUEST_INVALID: external generated browser request required."
            )
        from migration_agent.adapters.browser_request import BrowserWorkerRequest

        if path.stat().st_size > 131072:
            raise ValueError("BROWSER_REQUEST_INVALID: request exceeds the fixed manifest limit.")
        request = BrowserWorkerRequest.model_validate_json(path.read_text(encoding="utf-8"))
        if request.plan.digest != policy.browser_plan_digest:
            raise ValueError("BROWSER_REQUEST_INVALID: manifest differs from execution policy.")
        if request.phase == "e2e" and not request.plan.e2e_enabled:
            raise ValueError("BROWSER_REQUEST_INVALID: optional E2E was not enabled.")
        allowed = (
            set(request.plan.coverage)
            if request.phase == "ui"
            else {case.id for case in request.plan.e2e_cases}
        )
        if not set(request.case_keys) <= allowed or len(set(request.case_keys)) != len(
            request.case_keys
        ):
            raise ValueError("BROWSER_REQUEST_INVALID: capture batch exceeds declared coverage.")
        if policy.mode == ValidationMode.CONTAINER:
            expected = (
                "/workspace/" + request.plan.build_root,
                "/artifacts",
                "/usr/bin/chromium",
                "/opt/agent-tools/node_modules/playwright-core/index.js",
                False,
            )
            worker = Path(__file__).with_name("browser_worker.cjs").resolve()
            identity = ToolIdentity(path=str(worker), sha256=file_digest(worker))
            if identity not in context[2].toolchain:
                raise ValueError(
                    "BROWSER_WORKER_CHANGED: revalidate the container worker identity."
                )
            if (
                request.build_root,
                request.output_root,
                request.browser_path,
                request.playwright_entry,
                request.chromium_sandbox,
            ) != expected:
                raise ValueError(
                    "BROWSER_REQUEST_INVALID: container manifest has unsupported paths/options."
                )
            return self.container.run(
                BROWSER_COMMAND,
                working_dir,
                fence,
                engine_identity=context[2].toolchain[0],
                browser_mounts=BrowserMounts(worker=identity, artifacts=str(path.parent)),
            )
        consent = self._consent(context[0], context[1], context[2].consent_id)
        worker = Path(__file__).with_name("browser_worker.cjs").resolve()
        if not any(
            tool.path == str(worker) and tool.sha256 == file_digest(worker)
            for tool in consent.toolchain
        ):
            raise ValueError("BROWSER_CONSENT_REQUIRED: authorize browser-v1 execution explicitly.")
        root = self._external(self.settings.native_toolchain_root)
        expected = (
            str(safe_path(working_dir / request.plan.build_root)),
            str(path.parent),
            str(safe_path(self.settings.native_browser_path))
            if self.settings.native_browser_path
            else "",
            str(root / "node_modules/playwright-core/index.js"),
            True,
        )
        if (
            request.build_root,
            request.output_root,
            request.browser_path,
            request.playwright_entry,
            request.chromium_sandbox,
        ) != expected:
            raise ValueError(
                "BROWSER_REQUEST_INVALID: native manifest has unsupported paths/options."
            )
        node = root / ("node.exe" if os.name == "nt" else "bin/node")
        command = ValidationCommand(
            executable="browser-v1", args=(), profile=ValidationProfile.BUILD
        )
        return self._run_native([str(node), str(worker), str(path)], command, working_dir, fence)

    def _run_native(
        self,
        argv: list[str],
        command: ValidationCommand,
        working_dir: Path,
        fence: Callable[[], None],
    ) -> ValidationResult:
        record, commands, provenance = self._local.context
        consent = self._consent(record, commands, provenance.consent_id)
        root = self._external(self.settings.native_toolchain_root)
        start = time.monotonic()
        output, digest = bytearray(), hashlib.sha256()
        with tempfile.TemporaryDirectory(prefix="native-home-", dir=self.state) as home:
            env = {
                key: value
                for key, value in os.environ.items()
                if key.upper() in {"SYSTEMROOT", "WINDIR"}
            }
            env.update(
                {
                    "PATH": str(root)
                    + os.pathsep
                    + str(root / "node_modules" / ".bin")
                    + (
                        os.pathsep
                        + str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32")
                        if os.name == "nt"
                        else os.pathsep + "/usr/bin:/bin"
                    ),
                    "HOME": home,
                    "USERPROFILE": home,
                    "TEMP": home,
                    "TMP": home,
                    "TMPDIR": home,
                    "XDG_CACHE_HOME": home,
                    "APPDATA": home,
                    "LOCALAPPDATA": home,
                    "NODE_ENV": "test",
                    "npm_config_offline": "true",
                    "npm_config_audit": "false",
                    "npm_config_fund": "false",
                    "npm_config_ignore_scripts": "true",
                    "npm_config_cache": str(Path(home) / "npm-cache"),
                    "npm_config_userconfig": str(Path(home) / "empty-npmrc"),
                    "npm_config_globalconfig": str(Path(home) / "empty-npmrc"),
                    "CI": "true",
                    "NG_CLI_ANALYTICS": "false",
                }
            )
            Path(home, "empty-npmrc").touch()
            if os.name == "nt":
                system_shell = str(
                    Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/cmd.exe"
                )
                env["ComSpec"] = system_shell
                env["npm_config_script_shell"] = system_shell
            if self.settings.native_browser_path:
                env["CHROME_BIN"] = str(safe_path(self.settings.native_browser_path))
            if command.executable == "browser-v1" and os.name == "nt":
                for folder in ("USERPROFILE", "APPDATA", "LOCALAPPDATA"):
                    configured = os.environ.get(folder)
                    if configured:
                        env[folder] = str(safe_path(Path(configured)))
            fence()
            process = launch_native(argv, working_dir, env)
            output_failed: list[bool] = []

            def drain(stream: BinaryIO) -> None:
                try:
                    for chunk in iter(lambda: stream.read(4096), b""):
                        digest.update(chunk)
                        output.extend(chunk[: max(0, 66560 - len(output))])
                except OSError:
                    output_failed.append(True)
                finally:
                    stream.close()

            reader = threading.Thread(target=drain, args=(process.stdout,), daemon=True)
            reader.start()
            timed_out = False
            try:
                while process.poll() is None:
                    fence()
                    self._consent(record, commands, consent.consent_id, verify_inputs=False)
                    if time.monotonic() - start >= command.timeout_seconds:
                        timed_out = True
                        break
                    time.sleep(0.1)
                code = process.poll()
            finally:
                process.close()
                reader.join(timeout=5)
                if reader.is_alive():
                    raise ValueError("NATIVE_CLEANUP_UNVERIFIED: output handle remains open.")
                if output_failed:
                    raise ValueError("NATIVE_OUTPUT_UNVERIFIED: output collection failed.")
            fence()
            self._consent(record, commands, consent.consent_id)
            text = RedactionPolicy().redact_text(output.decode("utf-8", errors="replace"))
            text = text.encode("utf-8")[:65536].decode("utf-8", errors="ignore")
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=ValidationStatus.TIMED_OUT
                if timed_out
                else ValidationStatus.PASSED
                if code == 0
                else ValidationStatus.FAILED,
                exit_code=code,
                duration_ms=int((time.monotonic() - start) * 1000),
                sanitized_output=text,
                output_digest=f"sha256:{digest.hexdigest()}",
                diagnostics=tuple(
                    line[:512]
                    for line in text.splitlines()
                    if any(word in line.casefold() for word in ("error", "fail", "exception"))
                )[:10],
            )
