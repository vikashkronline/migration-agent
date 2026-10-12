"""Bounded configuration persistence in existing state and principal-scoped OS data."""

import hashlib
import json
import os
import re
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from migration_agent.adapters.access_rules import rule_text_digest
from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.apply_lock import ExclusiveApplyLock
from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.workflow_store import SqliteWorkflowStore
from migration_agent.config import Settings
from migration_agent.domain.access import AccessProposal
from migration_agent.domain.configuration import (
    ConfigurationDiagnostic,
    ConfigurationModel,
    ConfigurationProposal,
    ConfigurationReceipt,
    LauncherConfiguration,
    LocalConfiguration,
    ProjectConfiguration,
    unique_json_object,
)
from migration_agent.domain.stack_catalog import get_target_preset
from migration_agent.ports.filesystem import InspectionPolicy


class LocalEnvelope(ConfigurationModel):
    project_id: str
    principal_id: str
    access_digest: str
    request_id: str
    configuration: LocalConfiguration


class ConfigurationRepository:
    def __init__(self, authorization: ProjectAuthorization, settings: Settings) -> None:
        self.authorization = authorization
        self.settings = settings
        self.access = authorization.service()
        decision = self.access.require("project.read")
        self.principal_id = decision.principal_id or ""
        self.binding = self.access.store.binding
        self.source = Path(self.binding.source_root)
        self.governance = Path(self.binding.governance_root)
        self.project_id = ProjectBinding(authorization.source).project_id
        self.state = authorization.state
        self.staging = settings.resolve_staging_root().resolve()
        self.trust = authorization.trust
        self.local_root = (
            settings.local_config_root or Path.home() / ".agent-platform/config"
        ).resolve()
        roots = (
            self.source,
            self.governance,
            self.state,
            self.staging,
            self.trust,
            self.local_root,
        )
        for index, left in enumerate(roots):
            for right in roots[index + 1 :]:
                if left.is_relative_to(right) or right.is_relative_to(left):
                    raise ValueError(
                        "CONFIGURATION_UNSAFE_ROOTS: source, governance, state, staging, "
                        "trust and preferences must be distinct."
                    )
        self.identity = hashlib.sha256(
            f"{self.project_id}:{self.binding.model_dump_json()}:{authorization.actor.os_identity}:{self.principal_id}".encode()
        ).hexdigest()[:24]
        self.local_name = f"projects/{self.identity}/preferences.json"
        self.database = SqliteWorkflowStore(self.state)
        self.lock = ExclusiveApplyLock(self.state / "configuration-locks")
        with self.database._get_connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS configuration_requests (
                    project_id TEXT NOT NULL, principal_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    payload_digest TEXT NOT NULL, receipt_json TEXT NOT NULL,
                    PRIMARY KEY(project_id, principal_id, request_id));
                CREATE TABLE IF NOT EXISTS configuration_proposals (
                    proposal_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                    principal_id TEXT NOT NULL, proposal_json TEXT NOT NULL, access_json TEXT);
            """)

    @contextmanager
    def guard(self) -> Iterator[None]:
        with self.lock.acquire("configuration-" + self.project_id):
            yield

    def bindings(self) -> dict[str, str]:
        return {
            "source_root": str(self.source),
            "governance_root": str(self.governance),
            "state_dir": str(self.state),
            "staging_root": str(self.staging),
            "trust_root": str(self.trust),
            "local_config_root": str(self.local_root),
        }

    def _project_text(self) -> str | None:
        path = validate_repository_path(self.governance, ".agent/config.json")
        if not path.exists():
            return None
        text = read_repository_text(
            self.governance,
            ".agent/config.json",
            policy=InspectionPolicy(max_text_file_bytes=65536),
        )
        if rule_text_digest(".agent/config.json", text) != self.access.store.read().rules.get(
            ".agent/config.json"
        ):
            raise ValueError(
                "CONFIGURATION_UNVERIFIED: project settings differ from signed governance."
            )
        return text

    def project(self) -> ProjectConfiguration:
        text = self._project_text()
        if text is None:
            return self._legacy_project()
        data = json.loads(text, object_pairs_hook=unique_json_object)
        if data == {"version": 1, "workflows": {}}:
            return self._legacy_project()
        try:
            return ProjectConfiguration.model_validate_json(text)
        except ValidationError:
            raise ValueError(
                "CONFIGURATION_SCHEMA_UNSUPPORTED: preserve the existing file and "
                "review a schema upgrade; unknown workflows/settings cannot be "
                "silently replaced."
            ) from None

    def _legacy_project(self) -> ProjectConfiguration:
        from migration_agent.ports.governance import ProjectPolicy

        policy = ProjectPolicy.model_validate_json(
            read_repository_text(
                self.governance,
                ".agent/policy.json",
                policy=InspectionPolicy(max_text_file_bytes=65536),
            )
        )
        return ProjectConfiguration(
            max_step_files=min(100, policy.max_step_files),
            allowed_validation_modes=(self.settings.effective_validation_mode,),
        )

    def file_digest(self) -> str | None:
        text = self._project_text()
        if text is None:
            return None
        path = validate_repository_path(self.governance, ".agent/config.json")
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def source_revision(self) -> str:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(self.source), "rev-parse", "HEAD"],
            capture_output=True,
            timeout=5,
            shell=False,
        )
        revision = result.stdout.decode("ascii").strip()
        if result.returncode or len(revision) != 40:
            raise ValueError("CONFIGURATION_BINDING_INVALID: source revision is unavailable.")
        return revision

    def _local_envelope(self) -> LocalEnvelope | None:
        if (
            not self.local_root.exists()
            or not validate_repository_path(self.local_root, self.local_name).exists()
        ):
            return None
        value = LocalEnvelope.model_validate_json(
            read_repository_text(
                self.local_root, self.local_name, policy=InspectionPolicy(max_text_file_bytes=65536)
            )
        )
        if value.project_id != self.project_id or value.principal_id != self.principal_id:
            raise ValueError(
                "CONFIGURATION_BINDING_INVALID: local settings belong to another principal/project."
            )
        return value

    def local(self) -> LocalConfiguration:
        envelope = self._local_envelope()
        return envelope.configuration if envelope else LocalConfiguration()

    def local_request_id(self) -> str | None:
        envelope = self._local_envelope()
        return envelope.request_id if envelope else None

    def save_local(
        self, configuration: LocalConfiguration, request_id: str, access_digest: str
    ) -> None:
        value = LocalEnvelope(
            project_id=self.project_id,
            principal_id=self.principal_id,
            access_digest=access_digest,
            request_id=request_id,
            configuration=configuration,
        )
        self.local_root.mkdir(parents=True, exist_ok=True)
        path = validate_repository_path(self.local_root, self.local_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = validate_repository_path(
            self.local_root, self.local_name + ".tmp-" + uuid.uuid4().hex[:8]
        )
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(value.model_dump_json(indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            validate_repository_path(self.local_root, self.local_name)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def launcher(self) -> LauncherConfiguration:
        explicit = self.settings.model_fields_set
        return LauncherConfiguration(
            provider=self.settings.runtime_provider if "runtime_provider" in explicit else None,
            model=self.settings.effective_model,
            max_step_files=self.settings.max_step_files if "max_step_files" in explicit else None,
            validation_mode=self.settings.effective_validation_mode
            if "validation_mode" in explicit or "validation_image" in explicit
            else None,
            browser_provider_export=self.settings.browser_provider_export
            if "browser_provider_export" in explicit
            else None,
            paths={
                name: str(getattr(self.settings, name))
                for name in (
                    "final_target_root",
                    "native_toolchain_root",
                    "native_dependencies_root",
                    "native_browser_path",
                    "browser_validation_plan",
                    "validation_image",
                )
                if getattr(self.settings, name) is not None
            },
        )

    def diagnostics(
        self, project: ProjectConfiguration, local: LocalConfiguration
    ) -> tuple[ConfigurationDiagnostic, ...]:
        results: list[ConfigurationDiagnostic] = []

        def issue(
            field: str,
            code: str,
            message: str,
            severity: Literal["error", "prerequisite", "warning", "info"] = "error",
        ) -> None:
            results.append(
                ConfigurationDiagnostic(
                    field=field,
                    code=code,
                    message=message,
                    severity=severity,
                    action="Review this setting or open its prerequisite workflow.",
                )
            )

        if project.target_preset_id and get_target_preset(project.target_preset_id) is None:
            issue(
                "target_preset_id",
                "PRESET_UNSUPPORTED",
                "The target preset is not supported by an installed adapter.",
            )
        from migration_agent.ports.governance import ProjectPolicy

        policy = ProjectPolicy.model_validate_json(
            read_repository_text(
                self.governance,
                ".agent/policy.json",
                policy=InspectionPolicy(max_text_file_bytes=65536),
            )
        )
        if project.max_step_files > policy.max_step_files:
            issue(
                "max_step_files",
                "POLICY_LIMIT_EXCEEDED",
                (
                    "Configuration cannot expand the signed project file limit; "
                    "propose a policy change first."
                ),
            )
        if project.target_preset_id:
            from migration_agent.adapters.knowledge import GitKnowledgeAdapter
            from migration_agent.domain.knowledge import DecisionStatus

            decisions = GitKnowledgeAdapter().list_decisions(str(self.governance))
            for decision in decisions:
                accepted_preset = decision.metadata.get("preset_id")
                if (
                    decision.status == DecisionStatus.ACCEPTED
                    and accepted_preset
                    and accepted_preset != project.target_preset_id
                ):
                    issue(
                        "target_preset_id",
                        "ARCHITECTURE_CONFLICT",
                        (
                            "The selected preset conflicts with accepted architecture; review "
                            "supersession in the wizard."
                        ),
                    )
        roots = tuple(Path(value) for value in self.bindings().values())
        selected: dict[str, Path] = {}
        for name in (
            "native_toolchain_root",
            "native_dependencies_root",
            "native_browser_path",
            "browser_validation_plan",
            "final_target_root",
            "next_state_dir",
            "next_staging_root",
        ):
            value = getattr(local, name)
            if not value:
                continue
            path = Path(value).expanduser()
            if not path.is_absolute() or value.startswith(("\\\\", "//")):
                issue(
                    name,
                    "PATH_INVALID",
                    "Use an absolute local path; network paths are unsupported.",
                )
                continue
            if path.is_symlink() or path.is_junction():
                issue(
                    name,
                    "PATH_UNSAFE",
                    "Selected configuration paths cannot be links or junctions.",
                )
                continue
            path = path.resolve()
            if os.name == "nt" and len(str(path).encode("utf-16-le")) // 2 > 200:
                issue(
                    name,
                    "PATH_TOO_LONG",
                    "Choose a shorter root with room for artifact directories.",
                )
            if any(path.is_relative_to(root) or root.is_relative_to(path) for root in roots):
                issue(
                    name,
                    "PATH_OVERLAP",
                    (
                        "Configured paths must remain outside source, governance, state, "
                        "staging, trust and preferences."
                    ),
                )
            for previous, other in selected.items():
                # Permit a browser beneath its toolchain; other roots remain distinct.
                if {name, previous} == {"native_toolchain_root", "native_browser_path"}:
                    continue
                if path.is_relative_to(other) or other.is_relative_to(path):
                    issue(name, "PATH_OVERLAP", "Selected operational paths overlap one another.")
            selected[name] = path
            if (
                name not in {"final_target_root", "next_state_dir", "next_staging_root"}
                and not path.exists()
            ):
                issue(
                    name,
                    "PATH_MISSING",
                    "The selected installed prerequisite does not exist.",
                    "prerequisite",
                )
            if (
                path.exists()
                and name in {"native_browser_path", "browser_validation_plan"}
                and not path.is_file()
            ):
                issue(name, "PATH_KIND_INVALID", "This setting requires a regular file.")
            if (
                path.exists()
                and name not in {"native_browser_path", "browser_validation_plan"}
                and not path.is_dir()
            ):
                issue(name, "PATH_KIND_INVALID", "This setting requires a directory.")
            if name == "browser_validation_plan" and path.is_file():
                from migration_agent.adapters.browser_config import load_browser_plan

                try:
                    load_browser_plan(
                        self.settings.model_copy(update={"browser_validation_plan": path})
                    )
                except ValueError:
                    issue(
                        name,
                        "BROWSER_PLAN_INVALID",
                        "Browser coverage must satisfy the existing bounded plan schema.",
                    )
        if local.validation_image and not re.fullmatch(
            r"[^\s@]+@sha256:[a-f0-9]{64}", local.validation_image
        ):
            issue(
                "validation_image",
                "IMAGE_NOT_PINNED",
                "Select a locally installed image pinned by SHA-256 digest.",
            )
        if local.next_state_dir or local.next_staging_root:
            issue(
                "next_state_dir",
                "RESTART_REQUIRED",
                (
                    "Operational roots change only after an explicit idle/restart "
                    "handoff; no history is moved."
                ),
                "info",
            )
        return tuple(results)

    def receipt(self, request_id: str, payload_digest: str) -> ConfigurationReceipt | None:
        with self.database._get_connection() as connection:
            row = connection.execute(
                (
                    "SELECT payload_digest,receipt_json FROM configuration_requests "
                    "WHERE project_id=? AND principal_id=? AND request_id=?"
                ),
                (self.project_id, self.principal_id, request_id),
            ).fetchone()
        if row and row["payload_digest"] != payload_digest:
            raise ValueError(
                "CONFIGURATION_REQUEST_CONFLICT: request ID already binds different input."
            )
        return ConfigurationReceipt.model_validate_json(row["receipt_json"]) if row else None

    def save_receipt(self, receipt: ConfigurationReceipt, payload_digest: str) -> None:
        with self.database._get_connection() as connection:
            connection.execute(
                "INSERT INTO configuration_requests VALUES(?,?,?,?,?)",
                (
                    self.project_id,
                    self.principal_id,
                    receipt.request_id,
                    payload_digest,
                    receipt.model_dump_json(),
                ),
            )

    def local_access_digest(self) -> str | None:
        envelope = self._local_envelope()
        return envelope.access_digest if envelope else None

    def save_proposal(
        self, proposal: ConfigurationProposal, receipt: ConfigurationReceipt, payload_digest: str
    ) -> None:
        with self.database._get_connection() as connection:
            connection.execute(
                "INSERT INTO configuration_proposals VALUES(?,?,?,?,NULL)",
                (
                    proposal.proposal_id,
                    self.project_id,
                    self.principal_id,
                    proposal.model_dump_json(),
                ),
            )
            connection.execute(
                "INSERT INTO configuration_requests VALUES(?,?,?,?,?)",
                (
                    self.project_id,
                    self.principal_id,
                    receipt.request_id,
                    payload_digest,
                    receipt.model_dump_json(),
                ),
            )

    def proposal(self, proposal_id: str) -> ConfigurationProposal:
        with self.database._get_connection() as connection:
            row = connection.execute(
                (
                    "SELECT proposal_json FROM configuration_proposals WHERE "
                    "project_id=? AND proposal_id=?"
                ),
                (self.project_id, proposal_id),
            ).fetchone()
        if row is None:
            raise ValueError("CONFIGURATION_PROPOSAL_NOT_FOUND: select a recorded proposal.")
        return ConfigurationProposal.model_validate_json(row["proposal_json"])

    def approved_proposal(self, proposal_id: str) -> AccessProposal | None:
        with self.database._get_connection() as connection:
            row = connection.execute(
                (
                    "SELECT access_json FROM configuration_proposals WHERE "
                    "project_id=? AND proposal_id=?"
                ),
                (self.project_id, proposal_id),
            ).fetchone()
        return (
            AccessProposal.model_validate_json(row["access_json"])
            if row and row["access_json"]
            else None
        )

    def save_approved_proposal(self, proposal_id: str, access: AccessProposal) -> None:
        with self.database._get_connection() as connection:
            connection.execute(
                (
                    "UPDATE configuration_proposals SET access_json=? WHERE "
                    "project_id=? AND proposal_id=?"
                ),
                (access.model_dump_json(), self.project_id, proposal_id),
            )

    def history(self, offset: int, limit: int) -> tuple[ConfigurationProposal, ...]:
        with self.database._get_connection() as connection:
            rows = connection.execute(
                (
                    "SELECT proposal_json FROM configuration_proposals WHERE "
                    "project_id=? ORDER BY rowid DESC LIMIT ? OFFSET ?"
                ),
                (self.project_id, limit, offset),
            ).fetchall()
        return tuple(
            ConfigurationProposal.model_validate_json(row["proposal_json"]) for row in rows
        )
