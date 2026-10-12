"""Configuration scope, exact activation, rollback protection and consumer agreement."""

from pathlib import Path

import pytest
from security_project import security_project
from test_access import signed

from migration_agent.adapters.configuration_runtime import ConfigurationFacade
from migration_agent.application.configuration import resolve_configuration
from migration_agent.domain.access import AccessDenied
from migration_agent.domain.configuration import (
    LauncherConfiguration,
    LocalConfiguration,
    LocalConfigurationRequest,
    ProjectConfiguration,
    ProjectConfigurationRequest,
    RuntimeProfile,
)


@pytest.fixture
def configured(tmp_path):
    authorization, access, key = security_project(tmp_path)
    settings = authorization.settings.model_copy(
        update={"local_config_root": tmp_path / "preferences"}
    )
    authorization.settings = settings
    return ConfigurationFacade(authorization, settings), access, key


def project_configuration():
    return ProjectConfiguration(
        profiles=(
            RuntimeProfile(
                profile_id="approved",
                provider="gemini",
                models=("fixture-model", "alternate-model"),
                default_model="fixture-model",
            ),
        ),
        default_profile="approved",
        max_turns=7,
    )


def activate(facade, access, key, project):
    before = facade.service.view()
    receipt = facade.service.propose(
        ProjectConfigurationRequest(
            expected_revision=before.revision, request_id="project-proposal", configuration=project
        )
    )
    review = facade.service.review(receipt.proposal_id, prepare_signature=True)
    proof = signed(
        facade.repository.approved_proposal(receipt.proposal_id), key, access.view().members[0]
    )
    assert review.signing_digest == proof.proposal.signing_digest
    return facade.service.activate(receipt.proposal_id, proof)


def test_exact_owner_configuration_activation_and_runtime_values(configured):
    facade, access, key = configured
    project = project_configuration()
    active = activate(facade, access, key, project)
    assert active.project == project
    assert access.view().revision == 2
    assert facade.runtime_settings(model_operation=True).effective_model == "fixture-model"
    assert not (Path(active.bindings["source_root"]) / ".agent").exists()
    assert active.effective.fields[0].origin == "project"


def test_local_model_selection_is_principal_scoped_idempotent_and_bounded(configured):
    facade, access, key = configured
    active = activate(facade, access, key, project_configuration())
    request = LocalConfigurationRequest(
        expected_revision=active.revision,
        request_id="local-choice",
        configuration=LocalConfiguration(
            profile_id="approved", model="alternate-model", max_turns=5
        ),
    )
    receipt = facade.service.save_local(request)
    assert facade.service.save_local(request) == receipt
    assert access.view().revision == 2
    assert facade.runtime_settings(model_operation=True).effective_model == "alternate-model"
    changed = LocalConfigurationRequest(
        expected_revision=facade.service.view().revision,
        request_id="invalid-limit",
        configuration=LocalConfiguration(
            profile_id="approved", model="alternate-model", max_turns=8
        ),
    )
    with pytest.raises(ValueError, match="CONFIGURATION_INVALID"):
        facade.service.save_local(changed)


def test_source_overlap_and_stale_configuration_are_rejected(configured):
    facade, access, key = configured
    active = activate(facade, access, key, project_configuration())
    request = LocalConfigurationRequest(
        expected_revision=active.revision,
        request_id="unsafe-root",
        configuration=LocalConfiguration(final_target_root=active.bindings["source_root"]),
    )
    with pytest.raises(ValueError, match="CONFIGURATION_INVALID"):
        facade.service.save_local(request)
    with pytest.raises(ValueError, match="CONFIGURATION_STALE"):
        facade.service.propose(
            ProjectConfigurationRequest(
                expected_revision="sha256:" + "0" * 64,
                request_id="stale",
                configuration=project_configuration(),
            )
        )


def test_resolver_never_grants_provider_or_execution_from_launcher():
    result = resolve_configuration(
        project_configuration(),
        LocalConfiguration(),
        LauncherConfiguration(
            provider="openai", model="foreign-model", browser_provider_export=True
        ),
    )
    codes = {d.code for d in result.diagnostics}
    assert "PROVIDER_NOT_ALLOWED" in codes and "EXPORT_NOT_ALLOWED" in codes


def test_optional_default_guides_personal_selection_without_owner_approval():
    project = project_configuration().model_copy(update={"default_profile": None})
    result = resolve_configuration(project, LocalConfiguration(), LauncherConfiguration())
    assert {d.code for d in result.diagnostics} == {"PROFILE_SELECTION_REQUIRED"}
    selected = resolve_configuration(
        project, LocalConfiguration(profile_id="approved"), LauncherConfiguration()
    )
    assert not selected.diagnostics
    assert next(f.value for f in selected.fields if f.name == "model") == "fixture-model"


def test_configuration_draft_does_not_mutate_governance_or_execute(configured):
    facade, access, _ = configured
    before = facade.service.view()
    path = Path(before.bindings["governance_root"]) / ".agent/config.json"
    assert not path.exists()
    facade.service.propose(
        ProjectConfigurationRequest(
            expected_revision=before.revision,
            request_id="draft-only",
            configuration=project_configuration(),
        )
    )
    assert not path.exists() and access.view().revision == 1
    with pytest.raises(ValueError, match="OWNER_SETUP_REQUIRED"):
        facade.runtime_settings(model_operation=True)


def test_activation_interruption_recovers_signed_configuration_and_pointer(configured, monkeypatch):
    facade, access, key = configured
    before = facade.service.view()
    receipt = facade.service.propose(
        ProjectConfigurationRequest(
            expected_revision=before.revision,
            request_id="interrupted",
            configuration=project_configuration(),
        )
    )
    facade.service.review(receipt.proposal_id, prepare_signature=True)
    revision = signed(
        facade.repository.approved_proposal(receipt.proposal_id), key, access.view().members[0]
    )
    write = access.store._write

    def interrupted(root, relative, value):
        if relative == ".agent/access/current.json":
            raise OSError("Injected pointer failure")
        write(root, relative, value)

    monkeypatch.setattr(facade.service.access.store, "_write", interrupted)
    with pytest.raises(OSError):
        facade.service.activate(receipt.proposal_id, revision)
    with pytest.raises(AccessDenied, match="ACTIVATION_PENDING"):
        access.view()
    access.store.recover()
    assert facade.service.view().project == project_configuration()
