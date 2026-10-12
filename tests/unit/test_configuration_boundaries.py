"""Offline permission, transport, crash and worker acceptance for configuration."""

import json
import threading
import time

import pytest
from pydantic import ValidationError
from test_access import signed
from test_access_http import request
from test_configuration import activate, project_configuration
from test_configuration import configured as configuration_fixture

from migration_agent.adapters.configuration_api import ConfigurationApi
from migration_agent.adapters.configuration_checks import ConfigurationChecks
from migration_agent.adapters.control_api.server import LoopbackControlServer
from migration_agent.application.control_service import ControlApiService
from migration_agent.domain.access import (
    AccessActor,
    AccessDenied,
    AccessMember,
    AccessRole,
    ConfigurationActivationRequest,
)
from migration_agent.domain.configuration import (
    CheckKind,
    ConfigurationCheckRequest,
    LocalConfiguration,
    LocalConfigurationRequest,
    ProjectConfigurationRequest,
)
from migration_agent.domain.host_workflow import OperationStatus


@pytest.fixture
def configured(request):
    return configuration_fixture.__wrapped__(request.getfixturevalue("tmp_path"))


@pytest.fixture
def http_configuration(configured):
    facade, access, key = configured
    server = LoopbackControlServer(
        ControlApiService(),
        facade.authorization.source,
        authorization=facade.authorization,
        settings=facade.repository.settings,
    )
    server.start("127.0.0.1", 0, "offline-configuration-session")
    try:
        yield server, facade, access, key
    finally:
        server.stop()


def path(facade):
    return f"/api/v1/projects/{facade.repository.project_id}/configuration"


def finish(checks, operation_id):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        result = checks.result(operation_id)
        if result.status not in {"QUEUED", "RUNNING", "CANCEL_REQUESTED"}:
            return result
        time.sleep(0.02)
    raise AssertionError("bounded check did not finish")


def test_configuration_transport_auth_csrf_project_binding_and_strict_input(http_configuration):
    server, facade, _, _ = http_configuration
    base = path(facade)
    assert request(server, base, token=False)[0] == 401
    assert request(server, base.replace(facade.repository.project_id, "foreign"))[0] in {
        400,
        403,
        404,
        409,
    }
    view = facade.service.view()
    body = {
        "expected_revision": view.revision,
        "request_id": "local-http",
        "configuration": LocalConfiguration(max_turns=5).model_dump(mode="json"),
    }
    assert request(server, base + "/local", body, csrf=False)[0] == 403
    body["configuration"]["api_key"] = "must-never-be-persisted"
    status, data = request(server, base + "/local", body)
    assert status == 400 and "must-never-be-persisted" not in json.dumps(data)
    assert facade.repository.local_request_id() is None


def test_configuration_only_role_can_open_settings_and_cannot_mutate(http_configuration):
    server, facade, access, key = http_configuration
    current = access.view()
    role = AccessRole(
        role_id="settings-reader",
        label="Settings reader",
        capabilities=("project.read", "configuration.read"),
    )
    member = AccessMember(
        principal_id="settings-user",
        label="Settings user",
        roles=(role.role_id,),
        status="active",
        os_identity="uid:configuration-fixture",
    )
    candidate = current.model_copy(
        update={
            "revision": current.revision + 1,
            "previous_digest": current.digest,
            "roles": (*current.roles, role),
            "members": (*current.members, member),
        }
    )
    access.commit(signed(access.propose(candidate), key, current.members[0]))
    facade.authorization.actor = AccessActor(os_identity=member.os_identity, client="human")
    assert request(server, "/api/v1/session")[0] == 200
    status, data = request(server, path(facade))
    assert status == 200 and data["data"]["capabilities"] == sorted(role.capabilities)
    assert request(server, "/api/v1/workbench")[0] in {403, 404}
    body = {
        "expected_revision": data["data"]["revision"],
        "request_id": "viewer-save",
        "configuration": LocalConfiguration().model_dump(mode="json"),
    }
    assert request(server, path(facade) + "/local", body)[0] == 403
    assert (
        request(
            server,
            path(facade) + "/proposals",
            {**body, "configuration": project_configuration().model_dump(mode="json")},
        )[0]
        == 403
    )


def test_lost_activation_receipt_recovers_without_resigning_or_second_activation(
    configured, monkeypatch
):
    facade, access, key = configured
    receipt = facade.service.propose(
        ProjectConfigurationRequest(
            expected_revision=facade.service.view().revision,
            request_id="activation-draft",
            configuration=project_configuration(),
        )
    )
    facade.service.review(receipt.proposal_id, prepare_signature=True)
    revision = signed(
        facade.repository.approved_proposal(receipt.proposal_id), key, access.view().members[0]
    )
    api = ConfigurationApi(facade.authorization, facade.repository.settings)
    body = ConfigurationActivationRequest(
        proposal_id=receipt.proposal_id, request_id="activate-once", revision=revision
    ).model_dump(mode="json")
    save = api.facade.repository.save_receipt
    monkeypatch.setattr(
        api.facade.repository, "save_receipt", lambda *_: (_ for _ in ()).throw(OSError("fixture"))
    )
    with pytest.raises(OSError):
        api.post("/activate", body)
    assert access.view().revision == 2
    monkeypatch.setattr(api.facade.repository, "save_receipt", save)
    assert api.post("/activate", body).status == "ACTIVATED"
    assert access.view().revision == 2


def test_local_atomic_envelope_recovers_receipt_and_revocation_blocks_replay(
    configured, monkeypatch
):
    facade, access, key = configured
    request = LocalConfigurationRequest(
        expected_revision=facade.service.view().revision,
        request_id="local-interrupted",
        configuration=LocalConfiguration(max_turns=5),
    )
    save = facade.repository.save_receipt
    monkeypatch.setattr(
        facade.repository, "save_receipt", lambda *_: (_ for _ in ()).throw(OSError("fixture"))
    )
    with pytest.raises(OSError):
        facade.service.save_local(request)
    monkeypatch.setattr(facade.repository, "save_receipt", save)
    assert facade.service.save_local(request).status == "SAVED"
    current = access.view()
    candidate = current.model_copy(
        update={"revision": current.revision + 1, "previous_digest": current.digest}
    )
    access.commit(signed(access.propose(candidate), key, current.members[0]))
    with pytest.raises(AccessDenied):
        facade.service.save_local(request)


def test_provider_check_is_source_free_bounded_principal_bound_and_not_replayed(configured):
    facade, access, key = configured
    activate(facade, access, key, project_configuration())
    entered, release = threading.Event(), threading.Event()

    class Probe:
        count = 0

        def run(self, kind, bound, local, cancelled):
            self.count += 1
            assert kind == CheckKind.PROVIDER and local == LocalConfiguration()
            assert not cancelled()
            entered.set()
            assert release.wait(8)
            return ()

    probe = Probe()
    checks = ConfigurationChecks(facade, probe)
    check_request = ConfigurationCheckRequest(
        expected_revision=facade.service.view().revision,
        request_id="provider-once",
        kind=CheckKind.PROVIDER,
        configuration=LocalConfiguration(),
    )
    first = checks.start(check_request)
    try:
        assert entered.wait(8)
        assert checks.start(check_request).operation_id == first.operation_id
        assert probe.count == 1
    finally:
        release.set()
    assert finish(checks, first.operation_id).status == "SUCCEEDED"
    assert (
        checks.recover(first.operation_id).operation_id == first.operation_id and probe.count == 1
    )


def test_interrupted_running_provider_is_never_automatically_called_again(configured, monkeypatch):
    facade, access, key = configured
    activate(facade, access, key, project_configuration())
    checks = ConfigurationChecks(facade)
    monkeypatch.setattr(checks, "_launch", lambda *_: None)
    check_request = ConfigurationCheckRequest(
        expected_revision=facade.service.view().revision,
        request_id="provider-interrupted",
        kind=CheckKind.PROVIDER,
        configuration=LocalConfiguration(),
    )
    result = checks.start(check_request)
    operation = checks.store.get_operation(facade.repository.project_id, result.operation_id)
    checks.store.save_operation(operation.model_copy(update={"status": OperationStatus.RUNNING}))
    checks._run(operation, check_request, facade.repository.project())
    result = checks.result(result.operation_id)
    assert result.status == "RECOVERY_REQUIRED"
    assert result.diagnostics[0].code == "PROBE_OUTCOME_UNKNOWN"


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint": "https://unapproved.invalid"},
        {"max_turns": 31},
        {"profiles": [{"api_key": "never-store"}]},
        {"future_setting": True},
    ],
)
def test_unregistered_or_secret_configuration_input_fails_closed(changes):
    from migration_agent.domain.configuration import ProjectConfiguration

    with pytest.raises(ValidationError):
        ProjectConfiguration.model_validate_json(json.dumps(changes))


def test_historical_proposals_remain_inspectable_but_need_new_owner_review(configured):
    facade, access, key = configured
    before = facade.service.view()
    receipt = facade.service.propose(
        ProjectConfigurationRequest(
            expected_revision=before.revision,
            request_id="historical",
            configuration=project_configuration(),
        )
    )
    activate(facade, access, key, project_configuration())
    assert (
        facade.service.review(receipt.proposal_id).proposal.configuration == project_configuration()
    )
    with pytest.raises(ValueError, match="CONFIGURATION_STALE"):
        facade.service.review(receipt.proposal_id, prepare_signature=True)


def test_model_requests_pin_approved_choice_budget_disclosure_and_audit(configured):
    from migration_agent.adapters.configuration_agent_runtime import ConfigurationAgentRuntime
    from migration_agent.adapters.fake_runtime import FakeAgentRuntime
    from migration_agent.domain.qa import ContextEnvelope, ContextualQARequest

    facade, access, key = configured
    project = project_configuration()
    profile = project.profiles[0].model_copy(
        update={"allowed_payloads": ("connectivity", "contextual_qa")}
    )
    project = project.model_copy(update={"profiles": (profile,)})
    activate(facade, access, key, project)
    captured = []

    class Runtime(FakeAgentRuntime):
        def ask(self, request):
            captured.append(request)
            return super().ask(request)

    runtime = ConfigurationAgentRuntime(Runtime(), facade)
    request = ContextualQARequest(
        envelope=ContextEnvelope(
            project_root=str(facade.repository.source), query="Inspect recorded status"
        ),
        model="unapproved-input",
        max_turns=99,
    )
    view = facade.service.view()
    facade.service.save_local(
        LocalConfigurationRequest(
            expected_revision=view.revision,
            request_id="next-operation-model",
            configuration=LocalConfiguration(model="alternate-model"),
        )
    )
    runtime.ask(request)
    assert captured[0].model == "fixture-model" and captured[0].max_turns == 7
    next_runtime = ConfigurationAgentRuntime(Runtime(), facade)
    next_runtime.ask(request)
    assert captured[1].model == "alternate-model"
    events = facade.repository.database.get_events(facade.repository.project_id)
    assert events[-1].payload["configuration_digest"] == next_runtime.configuration_snapshot.digest
    with pytest.raises(ValueError, match="DISCLOSURE_REQUIRED"):
        runtime._request(request, "source_analysis")
    with pytest.raises(ValueError, match="LIMIT_EXCEEDED"):
        ConfigurationAgentRuntime(Runtime(), facade, turn_override=30).ask(request)


def test_semantically_identical_json_escaping_cannot_disable_runtime_constraints(configured):
    facade, access, key = configured
    project = project_configuration().model_copy(update={"max_step_files": 6})
    activate(facade, access, key, project)
    path = facade.repository.governance / ".agent/config.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace('"schema_version"', '"\\u0073chema_version"'), encoding="utf-8")
    assert facade.runtime_settings().max_step_files == 6
