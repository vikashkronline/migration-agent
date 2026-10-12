"""Durable bounded configuration checks; probes never execute repository scripts."""

import os
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from migration_agent.adapters.configuration_runtime import ConfigurationFacade
from migration_agent.adapters.native_process import launch_native
from migration_agent.domain.access import AccessDecision
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.configuration import (
    CheckKind,
    ConfigurationCheckRequest,
    ConfigurationCheckResult,
    ConfigurationDiagnostic,
    LocalConfiguration,
    ProjectConfiguration,
)
from migration_agent.domain.host_workflow import TERMINAL_OPERATIONS, Operation, OperationStatus


class ConfigurationProbes:
    def run(
        self,
        kind: CheckKind,
        facade: ConfigurationFacade,
        local: LocalConfiguration,
        cancelled: Callable[[], bool],
    ) -> tuple[ConfigurationDiagnostic, ...]:
        if kind == CheckKind.PROVIDER:
            from migration_agent.application.configuration import resolve_configuration

            snapshot = resolve_configuration(
                facade.repository.project(), local, facade.repository.launcher()
            )
            values = {field.name: field.value for field in snapshot.fields}
            profile = next(
                (
                    p
                    for p in facade.repository.project().profiles
                    if p.profile_id == values["profile_id"]
                ),
                None,
            )
            if not profile or "connectivity" not in profile.allowed_payloads:
                raise ValueError(
                    "CONFIGURATION_DISCLOSURE_REQUIRED: connectivity use needs owner approval."
                )
            if not values["model"]:
                raise ValueError(
                    "CONFIGURATION_OWNER_SETUP_REQUIRED: select an approved runtime profile."
                )
            if cancelled():
                raise ValueError("CONFIGURATION_CANCELLED: check cancelled before provider use.")
            if values["provider"] == "openai":
                from openai import OpenAI

                with OpenAI(
                    base_url="https://api.openai.com/v1", timeout=5, max_retries=0
                ) as client:
                    client.responses.create(
                        model=str(values["model"]), input="Reply exactly OK.", max_output_tokens=16
                    )
            else:
                from google import genai
                from google.genai import types

                gemini_client = genai.Client(
                    vertexai=False,
                    http_options=types.HttpOptions(
                        base_url="https://generativelanguage.googleapis.com",
                        timeout=5000,
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
                try:
                    gemini_client.models.generate_content(
                        model=str(values["model"]),
                        contents="Reply exactly OK.",
                        config=types.GenerateContentConfig(max_output_tokens=16),
                    )
                finally:
                    gemini_client.close()
            return (
                ConfigurationDiagnostic(
                    field="model",
                    code="PROVIDER_RESPONDED",
                    severity="info",
                    message=(
                        "The approved provider answered a fixed source-free "
                        "connectivity probe. This is not migration validation."
                    ),
                ),
            )
        if kind == CheckKind.TOOLCHAIN:
            from migration_agent.application.configuration import resolve_configuration

            snapshot = resolve_configuration(
                facade.repository.project(), local, facade.repository.launcher()
            )
            selected = next(f.value for f in snapshot.fields if f.name == "native_toolchain_root")
            root = Path(str(selected or "")).resolve()
            if not selected or not root.is_dir():
                raise ValueError(
                    "CONFIGURATION_TOOLCHAIN_REQUIRED: select an installed external toolchain."
                )
            node = root / ("node.exe" if os.name == "nt" else "bin/node")
            if not node.is_file() or node.is_symlink() or not node.resolve().is_relative_to(root):
                raise ValueError(
                    "CONFIGURATION_TOOLCHAIN_REQUIRED: the fixed installed Node "
                    "executable is unavailable."
                )
            environment = {
                key: value
                for key, value in os.environ.items()
                if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
            }
            environment["PATH"] = str(root)
            process = launch_native([str(node), "--version"], root, environment)
            deadline = time.monotonic() + 5
            try:
                while process.poll() is None:
                    if time.monotonic() >= deadline or cancelled():
                        raise ValueError(
                            "CONFIGURATION_PROBE_STOPPED: the bounded probe timed out or "
                            "was cancelled."
                        )
                    time.sleep(0.05)
                if process.poll() != 0:
                    raise ValueError(
                        "CONFIGURATION_PROBE_FAILED: the installed tool did not answer "
                        "the fixed version probe."
                    )
            finally:
                process.close()
                process.stdout.close()
            return (
                ConfigurationDiagnostic(
                    field="native_toolchain_root",
                    code="TOOL_RESPONDED",
                    severity="info",
                    message=(
                        "The installed tool answered the supervised version probe. "
                        "Dependencies and project builds remain separate checks."
                    ),
                ),
            )
        return ()


class ConfigurationChecks:
    _capacity = threading.BoundedSemaphore(2)

    def __init__(
        self, facade: ConfigurationFacade, probes: ConfigurationProbes | None = None
    ) -> None:
        self.facade = facade
        self.repository = facade.repository
        self.store = self.repository.database
        self.probes = probes or ConfigurationProbes()
        with self.store._get_connection() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS configuration_check_results "
                "(operation_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, "
                "content_json TEXT NOT NULL, request_json TEXT NOT NULL)"
            )

    def _authorize(self, kind: CheckKind, expected_digest: str | None = None) -> AccessDecision:
        decision = self.facade.authorization.require("configuration.read", expected_digest)
        if kind == CheckKind.PROVIDER:
            self.facade.authorization.require("provider.use", decision.access_digest)
        if kind == CheckKind.TOOLCHAIN:
            self.facade.authorization.require("execution.consent", decision.access_digest)
            self.facade.authorization.require("validation.run", decision.access_digest)
        return decision

    def start(self, request: ConfigurationCheckRequest) -> ConfigurationCheckResult:
        with self.repository.guard():
            decision = self._authorize(request.kind)
            view = self.facade.service.view()
            payload = compute_canonical_digest(request)
            scope = compute_canonical_digest(
                {"principal": decision.principal_id, "request": request.request_id}
            )
            operation = Operation(
                operation_id="op-" + uuid.uuid4().hex,
                project_id=view.project_id,
                request_id="configuration-" + scope.split(":")[1],
                kind="configuration." + request.kind.value,
                payload_digest=payload,
                actor=self.facade.authorization.actor.os_identity,
                principal_id=decision.principal_id,
                access_digest=decision.access_digest,
                capability="configuration.read",
                configuration_snapshot=view.effective,
            )
            if request.project_configuration is not None and request.kind != CheckKind.OFFLINE:
                raise ValueError(
                    "CONFIGURATION_PROBE_ACTIVE_ONLY: provider and tool probes use "
                    "active project constraints."
                )
            if request.project_configuration is not None:
                self.facade.authorization.require("configuration.propose", decision.access_digest)
            existing, claimed = self.store.claim_request(operation)
            initial = ConfigurationCheckResult(
                operation_id=existing.operation_id,
                status=existing.status.value,
                request_id=request.request_id,
                principal_id=existing.principal_id or "",
                access_digest=existing.access_digest or "",
                input_revision=request.expected_revision,
            )
            with self.store._get_connection() as connection:
                connection.execute(
                    "INSERT OR IGNORE INTO configuration_check_results VALUES(?,?,?,?)",
                    (
                        existing.operation_id,
                        existing.project_id,
                        initial.model_dump_json(),
                        request.model_dump_json(),
                    ),
                )
            if not claimed:
                if (
                    existing.principal_id != decision.principal_id
                    or existing.access_digest != decision.access_digest
                ):
                    raise ValueError(
                        "CONFIGURATION_CONTEXT_CHANGED: checks cannot replay under "
                        "changed authority."
                    )
                if existing.status not in TERMINAL_OPERATIONS:
                    self._launch(existing, request, request.project_configuration or view.project)
                return self.result(existing.operation_id)
            if request.expected_revision != view.revision:
                self.store.save_operation(
                    existing.model_copy(
                        update={
                            "status": OperationStatus.FAILED,
                            "message": "CONFIGURATION_STALE: refresh before checking.",
                        }
                    )
                )
                raise ValueError("CONFIGURATION_STALE: refresh before checking.")
            self._launch(existing, request, request.project_configuration or view.project)
            return self.result(existing.operation_id)

    def _launch(
        self,
        operation: Operation,
        request: ConfigurationCheckRequest,
        project: ProjectConfiguration,
    ) -> None:
        threading.Thread(
            target=self._run,
            args=(operation, request, project),
            daemon=True,
            name="configuration-check",
        ).start()

    def _run(
        self,
        operation: Operation,
        request: ConfigurationCheckRequest,
        project: ProjectConfiguration,
    ) -> None:
        try:
            lease = self.store.acquire_lease(
                "configuration-check:" + operation.operation_id, operation.operation_id, ttl=30
            )
        except ValueError:
            return
        acquired = False
        try:
            current = self.store.get_operation(operation.project_id, operation.operation_id)
            if current.status in TERMINAL_OPERATIONS:
                return
            acquired = self._capacity.acquire(blocking=False)
            status = OperationStatus.SUCCEEDED
            diagnostics: tuple[ConfigurationDiagnostic, ...] = ()

            def cancelled() -> bool:
                self.store.verify_lease(lease)
                self._authorize(request.kind, operation.access_digest)
                return self.store.get_operation(
                    operation.project_id, operation.operation_id
                ).status in {OperationStatus.CANCEL_REQUESTED, OperationStatus.CANCELLED}

            try:
                if not acquired:
                    raise ValueError("CONFIGURATION_BUSY: bounded probe capacity reached.")
                if cancelled():
                    status = OperationStatus.CANCELLED
                elif (
                    current.status == OperationStatus.RUNNING and request.kind == CheckKind.PROVIDER
                ):
                    status = OperationStatus.RECOVERY_REQUIRED
                    diagnostics = (
                        ConfigurationDiagnostic(
                            field="provider",
                            code="PROBE_OUTCOME_UNKNOWN",
                            severity="warning",
                            message=(
                                "An interrupted provider call cannot be replayed. Review "
                                "account usage before explicitly starting a new check."
                            ),
                        ),
                    )
                else:
                    if request.expected_revision != self.facade.service.view().revision:
                        raise ValueError("CONFIGURATION_STALE: refresh before checking.")
                    self.store.save_operation(
                        current.model_copy(update={"status": OperationStatus.RUNNING}), lease
                    )
                    diagnostics = self.facade.offline_checks(project, request.configuration)
                    if any(item.severity == "error" for item in diagnostics):
                        status = OperationStatus.FAILED
                    elif request.kind != CheckKind.OFFLINE:
                        diagnostics = (
                            *diagnostics,
                            *self.probes.run(
                                request.kind, self.facade, request.configuration, cancelled
                            ),
                        )
                    if cancelled():
                        status = OperationStatus.CANCELLED
            except Exception:
                status = OperationStatus.FAILED
                diagnostics = (
                    ConfigurationDiagnostic(
                        field=request.kind.value,
                        code="CHECK_UNAVAILABLE",
                        severity="error",
                        message=(
                            "The check failed, timed out, exceeded bounded capacity or lost"
                            " permission. Refresh and inspect its prerequisites."
                        ),
                    ),
                )
            current = self.store.get_operation(operation.project_id, operation.operation_id)
            if current.status in TERMINAL_OPERATIONS:
                return
            if current.status == OperationStatus.CANCEL_REQUESTED:
                status = OperationStatus.CANCELLED
            result = ConfigurationCheckResult(
                operation_id=operation.operation_id,
                status=status.value,
                request_id=request.request_id,
                principal_id=operation.principal_id or "",
                access_digest=operation.access_digest or "",
                input_revision=request.expected_revision,
                diagnostics=diagnostics,
            )
            with self.store._get_connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self.store._verify(connection, lease)
                connection.execute(
                    (
                        "UPDATE configuration_check_results SET content_json=? WHERE "
                        "operation_id=? AND project_id=?"
                    ),
                    (result.model_dump_json(), operation.operation_id, operation.project_id),
                )
            self.store.save_operation(
                current.model_copy(
                    update={
                        "status": status,
                        "message": "Configuration checks recorded; no workflow executed.",
                        "updated_at": datetime.now(UTC),
                    }
                ),
                lease,
            )
        except ValueError:
            # A lost lease leaves the durable operation recoverable by its original principal.
            return
        finally:
            if acquired:
                self._capacity.release()
            self.store.release_lease(lease)

    def result(self, operation_id: str) -> ConfigurationCheckResult:
        decision = self.facade.authorization.require("configuration.read")
        operation = self.store.get_operation(self.repository.project_id, operation_id)
        if operation.principal_id != decision.principal_id or not operation.kind.startswith(
            "configuration."
        ):
            raise ValueError(
                "CONFIGURATION_CHECK_NOT_FOUND: check belongs to another principal or purpose."
            )
        with self.store._get_connection() as connection:
            row = connection.execute(
                (
                    "SELECT content_json FROM configuration_check_results WHERE "
                    "operation_id=? AND project_id=?"
                ),
                (operation_id, self.repository.project_id),
            ).fetchone()
        if row:
            return ConfigurationCheckResult.model_validate_json(row["content_json"]).model_copy(
                update={"status": operation.status.value}
            )
        return ConfigurationCheckResult(
            operation_id=operation_id,
            status=operation.status.value,
            request_id=operation.request_id,
            principal_id=decision.principal_id or "",
            access_digest=operation.access_digest or "",
            input_revision="",
            diagnostics=(),
        )

    def cancel(self, operation_id: str) -> ConfigurationCheckResult:
        self.result(operation_id)
        self.store.cancel_operation(self.repository.project_id, operation_id)
        return self.result(operation_id)

    def recover(self, operation_id: str) -> ConfigurationCheckResult:
        self.result(operation_id)
        with self.store._get_connection() as connection:
            row = connection.execute(
                (
                    "SELECT request_json FROM configuration_check_results WHERE "
                    "operation_id=? AND project_id=?"
                ),
                (operation_id, self.repository.project_id),
            ).fetchone()
        if not row:
            raise ValueError(
                "CONFIGURATION_CHECK_NOT_FOUND: no immutable check request is recorded."
            )
        return self.start(ConfigurationCheckRequest.model_validate_json(row["request_json"]))
