"""Pinned provider, model, disclosure and turn limits around supported runtime ports."""

import uuid
from typing import TypeVar

from pydantic import BaseModel

from migration_agent.adapters.configuration_runtime import ConfigurationFacade
from migration_agent.application.configuration import resolve_configuration
from migration_agent.domain import (
    AnalysisResult,
    ContextualAnswer,
    ContextualQARequest,
    InventoryInterpretation,
    InventoryInterpretationRequest,
    MigrationAnalysisOutput,
    MigrationAnalystRequest,
    MigrationStep,
    PlanCriticRequest,
    PlanCritique,
    RepairDiagnosis,
    RepairDiagnosticianRequest,
)
from migration_agent.ports.agent_runtime import (
    AgentRuntimePort,
    AnalysisRequest,
    FileReaderPort,
    PlanningRequest,
)
from migration_agent.ports.checkpoints import AuditEvent
from migration_agent.ports.specialists import SpecialistRuntimePort

Request = TypeVar("Request", bound=BaseModel)


class ConfigurationAgentRuntime:
    def __init__(
        self,
        runtime: AgentRuntimePort,
        facade: ConfigurationFacade,
        turn_override: int | None = None,
    ) -> None:
        self.runtime = runtime
        self.facade = facade
        self.configuration_snapshot = resolve_configuration(
            facade.repository.project(), facade.repository.local(), facade.repository.launcher()
        )
        self.values = {field.name: field.value for field in self.configuration_snapshot.fields}
        self.access_digest = facade.authorization.require("provider.use").access_digest
        self.turn_override = turn_override

    def _permit(self, purpose: str) -> None:
        self.facade.authorization.require("provider.use", self.access_digest)
        project = self.facade.repository.project()
        profile = next(
            (
                profile
                for profile in project.profiles
                if profile.profile_id == self.values["profile_id"]
            ),
            None,
        )
        if not profile or purpose not in profile.allowed_payloads:
            raise ValueError(
                "CONFIGURATION_DISCLOSURE_REQUIRED: the owner must approve this"
                " payload purpose for the selected provider profile."
            )

    def _request(self, request: Request, purpose: str, specialist: bool = False) -> Request:
        self._permit(purpose)
        maximum = int(self.values["max_turns"] or 1)
        turns = self.turn_override if self.turn_override is not None else maximum
        if not 1 <= turns <= self.facade.repository.project().max_turns:
            raise ValueError(
                "CONFIGURATION_LIMIT_EXCEEDED: explicit turn override exceeds approved limits."
            )
        if specialist:
            turns = min(turns, int(getattr(request, "max_turns", turns)))
        updates = {
            name: value
            for name, value in {
                "provider": self.values["provider"],
                "model": self.values["model"],
                "max_turns": turns,
            }.items()
            if name in type(request).model_fields
        }
        self.facade.repository.database.record_event(
            AuditEvent(
                event_id="configuration-" + uuid.uuid4().hex,
                run_id=str(getattr(request, "run_id", self.facade.repository.project_id)),
                event_type="configuration.runtime.snapshot",
                actor=self.facade.repository.principal_id,
                payload={
                    "purpose": purpose,
                    "access_digest": self.access_digest,
                    "configuration_digest": self.configuration_snapshot.digest,
                    "configuration": self.configuration_snapshot.model_dump(mode="json"),
                    "effective_turns": turns,
                    "bindings": self.facade.repository.bindings(),
                },
            )
        )
        return request.model_copy(update=updates)

    def analyze(self, request: AnalysisRequest, file_reader: FileReaderPort) -> AnalysisResult:
        guarded = self

        class Reader:
            def read_file(self, path: str) -> str:
                guarded._permit("source_analysis")
                return file_reader.read_file(path)

        result = self.runtime.analyze(self._request(request, "source_analysis"), Reader())
        self._permit("source_analysis")
        return result

    def plan(self, request: PlanningRequest) -> list[MigrationStep]:
        result = self.runtime.plan(self._request(request, "planning"))
        self._permit("planning")
        return result

    def ask(self, request: ContextualQARequest) -> ContextualAnswer:
        result = self.runtime.ask(self._request(request, "contextual_qa"))
        self._permit("contextual_qa")
        return result


class ConfigurationSpecialistRuntime(ConfigurationAgentRuntime):
    def specialist(self) -> SpecialistRuntimePort:
        if not isinstance(self.runtime, SpecialistRuntimePort):
            raise ValueError(
                "CONFIGURATION_RUNTIME_UNSUPPORTED: specialist capability is unavailable."
            )
        return self.runtime

    def interpret_inventory(
        self, request: InventoryInterpretationRequest
    ) -> InventoryInterpretation:
        result = self.specialist().interpret_inventory(
            self._request(request, "source_analysis", True)
        )
        self._permit("source_analysis")
        return result

    def analyze_migration(
        self, request: MigrationAnalystRequest, file_reader: FileReaderPort
    ) -> MigrationAnalysisOutput:
        guarded = self

        class Reader:
            def read_file(self, path: str) -> str:
                guarded._permit("source_analysis")
                return file_reader.read_file(path)

        result = self.specialist().analyze_migration(
            self._request(request, "source_analysis", True), Reader()
        )
        self._permit("source_analysis")
        return result

    def criticize_plan(self, request: PlanCriticRequest) -> PlanCritique:
        result = self.specialist().criticize_plan(self._request(request, "planning", True))
        self._permit("planning")
        return result

    def diagnose_repair(self, request: RepairDiagnosticianRequest) -> RepairDiagnosis:
        result = self.specialist().diagnose_repair(self._request(request, "source_analysis", True))
        self._permit("source_analysis")
        return result
