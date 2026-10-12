"""Typed configuration API facade, bound to the launched project and OS principal."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.configuration_checks import ConfigurationChecks
from migration_agent.adapters.configuration_runtime import ConfigurationFacade
from migration_agent.config import Settings
from migration_agent.domain.access import ConfigurationActivationRequest
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.configuration import (
    ConfigurationCheckRequest,
    ConfigurationReceipt,
    ConfigurationSetupPlan,
    ConfigurationSetupRequest,
    LocalConfigurationRequest,
    ProjectConfigurationRequest,
)


class ConfigurationApi:
    def __init__(self, authorization: ProjectAuthorization, settings: Settings) -> None:
        self.facade = ConfigurationFacade(authorization, settings)

    def get(self, suffix: str, query: dict[str, list[str]]) -> BaseModel | dict[str, Any]:
        service = self.facade.service
        if suffix == "":
            return service.view()
        if suffix == "/schema":
            return {
                "schema_version": 1,
                "fields": [
                    field.model_dump(mode="json") for field in service.view().field_descriptors
                ],
            }
        if suffix == "/history":
            view = service.view()
            proposals = service.history(
                int(query.get("offset", ["0"])[0]), int(query.get("limit", ["25"])[0])
            )
            entries = []
            for proposal in proposals:
                prepared = self.facade.repository.approved_proposal(proposal.proposal_id)
                status = (
                    "ACTIVE"
                    if prepared and prepared.candidate.digest == view.access_digest
                    else ("STALE" if proposal.base_access_digest != view.access_digest else "DRAFT")
                )
                entries.append(
                    {
                        "proposal_id": proposal.proposal_id,
                        "status": status,
                        "principal_id": proposal.principal_id,
                        "created_at": proposal.created_at,
                    }
                )
            return {
                "active_access_digest": view.access_digest,
                "entries": entries,
                "proposals": [proposal.model_dump(mode="json") for proposal in proposals],
            }
        if suffix.startswith("/proposals/"):
            return service.review(suffix.removeprefix("/proposals/"))
        if suffix.startswith("/checks/"):
            return ConfigurationChecks(self.facade).result(suffix.removeprefix("/checks/"))
        raise KeyError("CONFIGURATION_ENDPOINT_NOT_FOUND")

    def post(self, suffix: str, body: dict[str, Any]) -> BaseModel:
        service = self.facade.service
        if suffix == "/proposals":
            return service.propose(
                ProjectConfigurationRequest.model_validate_json(json.dumps(body))
            )
        if suffix == "/local":
            return service.save_local(
                LocalConfigurationRequest.model_validate_json(json.dumps(body))
            )
        if suffix == "/checks":
            return ConfigurationChecks(self.facade).start(
                ConfigurationCheckRequest.model_validate_json(json.dumps(body))
            )
        if suffix.startswith("/checks/"):
            operation_id, action = suffix.removeprefix("/checks/").rsplit("/", 1)
            checks = ConfigurationChecks(self.facade)
            if action == "cancel":
                return checks.cancel(operation_id)
            if action == "recover":
                return checks.recover(operation_id)
        if suffix.startswith("/proposals/") and suffix.endswith("/review"):
            return service.review(
                suffix.removeprefix("/proposals/").removesuffix("/review"), prepare_signature=True
            )
        if suffix == "/activate":
            request = ConfigurationActivationRequest.model_validate_json(json.dumps(body))
            self.facade.authorization.require("rules.manage")
            self.facade.authorization.require("access.commit")
            payload = compute_canonical_digest(request)
            with self.facade.repository.guard():
                previous = self.facade.repository.receipt(request.request_id, payload)
            if previous:
                self.facade.authorization.require("rules.manage", previous.access_digest)
                return previous
            prepared = self.facade.repository.approved_proposal(request.proposal_id)
            if prepared != request.revision.proposal:
                raise ValueError("CONFIGURATION_CONFLICT: proof must bind the recorded proposal.")
            if service.access.store.is_active_revision(request.revision):
                view = service.view()
            else:
                view = service.activate(request.proposal_id, request.revision)
            receipt = ConfigurationReceipt(
                request_id=request.request_id,
                status="ACTIVATED",
                revision=view.revision,
                proposal_id=request.proposal_id,
                message="Signed project configuration activated; no workflow was started.",
                access_digest=view.access_digest,
            )
            with self.facade.repository.guard():
                previous = self.facade.repository.receipt(request.request_id, payload)
                if previous:
                    return previous
                self.facade.repository.save_receipt(receipt, payload)
            return receipt
        if suffix == "/setup-plan":
            return self.setup_plan(ConfigurationSetupRequest.model_validate_json(json.dumps(body)))
        raise KeyError("CONFIGURATION_ENDPOINT_NOT_FOUND")

    def setup_plan(self, request: ConfigurationSetupRequest) -> ConfigurationSetupPlan:
        view = self.facade.service.view()
        self.facade.authorization.require("access.commit", view.access_digest)
        if not view.is_owner:
            raise ValueError(
                "CONFIGURATION_OWNER_REQUIRED: only an owner can prepare a new binding."
            )
        roots = [
            Path(value).expanduser()
            for value in (
                request.source_root,
                request.governance_root,
                request.state_dir,
                request.staging_root,
            )
        ]
        for index, path in enumerate(roots):
            if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
                raise ValueError("CONFIGURATION_PATH_INVALID: setup requires absolute local paths.")
            canonical = path.resolve()
            protected = tuple(Path(value) for value in view.bindings.values())
            if any(
                canonical.is_relative_to(root) or root.is_relative_to(canonical)
                for root in protected
            ):
                raise ValueError(
                    "CONFIGURATION_UNSAFE_ROOTS: new setup must not reuse or "
                    "overlap current bindings."
                )
            for other in roots[index + 1 :]:
                other = other.resolve()
                if canonical.is_relative_to(other) or other.is_relative_to(canonical):
                    raise ValueError("CONFIGURATION_UNSAFE_ROOTS: setup roots must be distinct.")
            trust = self.facade.repository.trust
            if canonical.is_relative_to(trust) or trust.is_relative_to(canonical):
                raise ValueError("CONFIGURATION_UNSAFE_ROOTS: setup cannot overlap external trust.")
        if roots[0].resolve() == self.facade.repository.source.resolve():
            raise ValueError(
                "CONFIGURATION_BINDING_EXISTS: use the current project; source "
                "bindings cannot be replaced."
            )
        return ConfigurationSetupPlan(
            request=request,
            command_arguments=(
                "agent",
                "init",
                str(roots[1]),
                "--source",
                str(roots[0]),
                "--id",
                request.project_name,
                "--state-dir",
                str(roots[2]),
                "--staging-root",
                str(roots[3]),
            ),
            message=(
                "This is an initialization handoff only. No new source was "
                "read, opened or changed. Run in a trusted terminal, then "
                "bootstrap its owner and open a newly bound session."
            ),
        )
