"""Configuration inspection, proposals and exact human approval through shared services."""

import json
import uuid
from pathlib import Path
from typing import Annotated

import typer

from migration_agent.adapters.access_cli import _confirm, _emit
from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.configuration_api import ConfigurationApi
from migration_agent.adapters.configuration_checks import ConfigurationChecks
from migration_agent.adapters.configuration_runtime import ConfigurationFacade
from migration_agent.adapters.filesystem import read_repository_text
from migration_agent.config import Settings
from migration_agent.domain.configuration import (
    CheckKind,
    ConfigurationCheckRequest,
    LocalConfiguration,
    LocalConfigurationRequest,
    ProjectConfiguration,
    ProjectConfigurationRequest,
    unique_json_object,
)
from migration_agent.ports.filesystem import InspectionPolicy

Source = Annotated[Path, typer.Argument(help="Bound read-only source repository.")]
State = Annotated[Path | None, typer.Option("--state-dir")]
Trust = Annotated[Path | None, typer.Option("--trust-root")]
Staging = Annotated[Path | None, typer.Option("--staging-root")]
Preferences = Annotated[Path | None, typer.Option("--local-config-root")]


def configuration_settings(
    state: Path | None, trust: Path | None, staging: Path | None, preferences: Path | None
) -> Settings:
    return Settings().model_copy(
        update={
            name: value
            for name, value in (
                ("state_dir", state),
                ("trust_root", trust),
                ("staging_root", staging),
                ("local_config_root", preferences),
            )
            if value is not None
        }
    )


def configuration_facade(
    source: Path,
    state: Path | None,
    trust: Path | None,
    staging: Path | None,
    preferences: Path | None,
) -> ConfigurationFacade:
    settings = configuration_settings(state, trust, staging, preferences)
    return ConfigurationFacade(ProjectAuthorization(source, settings), settings)


def public_json(path: Path) -> str:
    if path.is_symlink() or path.is_junction() or path.suffix != ".json":
        raise ValueError("CONFIGURATION_INPUT_INVALID: select a bounded regular JSON file.")
    text = read_repository_text(
        path.resolve().parent, path.name, policy=InspectionPolicy(max_text_file_bytes=65536)
    )
    json.loads(text, object_pairs_hook=unique_json_object)
    return text


def register_configuration_cli(app: typer.Typer) -> None:
    group = typer.Typer(
        help="Inspect and manage public, constrained project/local settings.",
        pretty_exceptions_enable=False,
    )
    app.add_typer(group, name="config")

    @group.command("show")
    def show(
        source: Source,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
    ) -> None:
        _emit(
            configuration_facade(
                source, state_dir, trust_root, staging_root, local_config_root
            ).service.view()
        )

    @group.command("schema")
    def schema(
        source: Source,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
    ) -> None:
        view = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        ).service.view()
        _emit({"fields": [field.model_dump(mode="json") for field in view.field_descriptors]})

    @group.command("propose")
    def propose(
        source: Source,
        input_file: Annotated[Path, typer.Option("--input")],
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
        request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    ) -> None:
        facade = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        )
        facade.authorization.require("configuration.propose")
        configuration = ProjectConfiguration.model_validate_json(public_json(input_file))
        _emit(
            facade.service.propose(
                ProjectConfigurationRequest(
                    expected_revision=facade.service.view().revision,
                    request_id=request_id or uuid.uuid4().hex,
                    configuration=configuration,
                )
            )
        )

    @group.command("local-set")
    def local_set(
        source: Source,
        input_file: Annotated[Path, typer.Option("--input")],
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
        request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    ) -> None:
        facade = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        )
        facade.authorization.require("configuration.local.write")
        configuration = LocalConfiguration.model_validate_json(public_json(input_file))
        _emit(
            facade.service.save_local(
                LocalConfigurationRequest(
                    expected_revision=facade.service.view().revision,
                    request_id=request_id or uuid.uuid4().hex,
                    configuration=configuration,
                )
            )
        )

    @group.command("review")
    def review(
        source: Source,
        proposal_id: str,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
    ) -> None:
        facade = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        )
        _emit(facade.service.review(proposal_id, prepare_signature=True))

    @group.command("approve")
    def approve(
        source: Source,
        proposal_id: str,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
        request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    ) -> None:
        facade = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        )
        reviewed = facade.service.review(proposal_id, prepare_signature=True)
        _emit(reviewed)
        _confirm(reviewed.signing_digest or "")
        signed = facade.service.access.sign(reviewed.access_proposal_id or "")
        result = ConfigurationApi(facade.authorization, facade.repository.settings).post(
            "/activate",
            {
                "proposal_id": proposal_id,
                "request_id": request_id or uuid.uuid4().hex,
                "revision": signed.model_dump(mode="json"),
            },
        )
        _emit(result)

    @group.command("history")
    def history(
        source: Source,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
        offset: int = 0,
        limit: int = 25,
    ) -> None:
        facade = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        )
        _emit(
            {
                "proposals": [
                    proposal.model_dump(mode="json")
                    for proposal in facade.service.history(offset, limit)
                ]
            }
        )

    @group.command("check")
    def check(
        source: Source,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
        kind: CheckKind = CheckKind.OFFLINE,
        request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    ) -> None:
        facade = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        )
        view = facade.service.view()
        _emit(
            ConfigurationChecks(facade).start(
                ConfigurationCheckRequest(
                    expected_revision=view.revision,
                    request_id=request_id or uuid.uuid4().hex,
                    kind=kind,
                    configuration=view.local,
                )
            )
        )

    @group.command("check-status")
    def check_status(
        source: Source,
        operation_id: str,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
    ) -> None:
        facade = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        )
        _emit(ConfigurationChecks(facade).result(operation_id))

    @group.command("recover")
    def recover(
        source: Source,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
        operation_id: Annotated[str | None, typer.Option("--check")] = None,
    ) -> None:
        settings = configuration_settings(state_dir, trust_root, staging_root, local_config_root)
        authorization = ProjectAuthorization(source, settings)
        if operation_id:
            _emit(
                ConfigurationChecks(ConfigurationFacade(authorization, settings)).recover(
                    operation_id
                )
            )
        else:
            authorization.service().store.recover()
            _emit(
                {
                    "status": "RECOVERED",
                    "message": (
                        "Verified signed governance intent completed; no new authority was created."
                    ),
                }
            )

    @group.command("restore")
    def restore(
        source: Source,
        proposal_id: str,
        state_dir: State = None,
        trust_root: Trust = None,
        staging_root: Staging = None,
        local_config_root: Preferences = None,
    ) -> None:
        facade = configuration_facade(
            source, state_dir, trust_root, staging_root, local_config_root
        )
        facade.authorization.require("configuration.propose")
        old = facade.repository.proposal(proposal_id)
        _emit(
            facade.service.propose(
                ProjectConfigurationRequest(
                    expected_revision=facade.service.view().revision,
                    request_id=uuid.uuid4().hex,
                    configuration=old.configuration,
                )
            )
        )
