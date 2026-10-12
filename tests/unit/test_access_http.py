"""Real loopback HTTP security and signed owner administration, without external network."""

import base64
import http.client
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from security_project import security_project
from test_access import signed

from migration_agent.adapters.control_api.server import LoopbackControlServer
from migration_agent.application.control_service import ControlApiService
from migration_agent.domain.access import AccessMember
from migration_agent.domain.git_directory import GitDirectoryResult


@pytest.fixture
def access_http(tmp_path):
    authorization, service, key = security_project(tmp_path)
    server = LoopbackControlServer(
        ControlApiService(), authorization.source, authorization=authorization
    )
    server.start("127.0.0.1", 0, "offline-rbac-session-fixture")
    try:
        yield server, service, key
    finally:
        server.stop()


def request(server, path, body=None, *, token=True, csrf=True):
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    headers = {"Origin": f"http://127.0.0.1:{server.port}"}
    if token:
        headers["X-Session-Token"] = server.session_token
    if csrf:
        headers["X-CSRF-Token"] = server.csrf_token
    connection.request(
        "POST" if body is not None else "GET",
        path,
        body=json.dumps(body) if body is not None else None,
        headers=headers,
    )
    response = connection.getresponse()
    status = response.status
    data = json.loads(response.read())
    connection.close()
    return status, data


def test_access_session_authentication_and_csrf(access_http):
    server, service, _ = access_http
    assert request(server, "/api/v1/access", token=False)[0] == 401
    before = service.view()
    body = {
        "base_digest": before.digest,
        "mutations": [{"kind": "member.remove", "entity_id": "owner"}],
    }
    assert request(server, "/api/v1/access/proposals", body, csrf=False)[0] == 403
    assert service.view().digest == before.digest


def test_public_onboarding_packet_contains_grants_without_trust_material(access_http):
    server, service, _ = access_http
    status, packet = request(server, "/api/v1/access/onboarding?principal=owner")
    assert status == 200
    packet = packet["data"]
    assert packet["principal_id"] == "owner"
    assert packet["source_root_commit"] == service.view().binding.source_root_commit
    assert "changeset.apply" in packet["assigned_capabilities"]
    assert packet["steps"]
    assert not {"private_key", "trust_root", "session_token", "state", "anchor"} & packet.keys()


def test_slow_directory_request_does_not_block_other_http_requests(access_http, monkeypatch):
    server, _, _ = access_http
    entered = threading.Event()
    release = threading.Event()

    class SlowDirectory:
        def members(self, directory_request):
            entered.set()
            assert release.wait(5), "directory fixture was not released"
            return GitDirectoryResult(request=directory_request, repository_id="123", members=())

    monkeypatch.setattr(
        "migration_agent.adapters.control_api.server.ProviderGitDirectory",
        lambda _: SlowDirectory(),
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            request,
            server,
            "/api/v1/access/repository-preview",
            {"provider": "github", "host": "github.com", "repository": "org/governance"},
        )
        try:
            assert entered.wait(5)
            assert request(server, "/api/v1/access/session")[0] == 200
            assert not pending.done()
        finally:
            release.set()
        assert pending.result(timeout=5)[0] == 200


def test_owner_http_proposal_and_exact_signed_activation(access_http):
    server, service, key = access_http
    before = service.view()
    member = AccessMember(principal_id="new-reviewer", label="Reviewer", roles=("reviewer",))
    status, data = request(
        server,
        "/api/v1/access/proposals",
        {
            "base_digest": before.digest,
            "mutations": [{"kind": "member.set", "member": member.model_dump(mode="json")}],
        },
    )
    assert status == 201
    proposal = service.store.proposal(data["data"]["proposal"]["proposal_id"])
    revision = signed(proposal, key, before.members[0])
    raw = revision.model_copy(
        update={
            "proofs": (
                revision.proofs[0].model_copy(
                    update={
                        "signature": "ed25519-base64:"
                        + base64.b64encode(key.sign(proposal.signing_digest.encode())).decode()
                    }
                ),
            )
        }
    )
    assert request(server, "/api/v1/access/activate", raw.model_dump(mode="json"))[0] == 403
    assert service.view().digest == before.digest
    status, data = request(server, "/api/v1/access/activate", revision.model_dump(mode="json"))
    assert status == 200 and data["data"]["revision"] == 2
    assert request(server, "/api/v1/access/activate", revision.model_dump(mode="json"))[0] == 403
    assert service.view().revision == 2


def test_session_token_does_not_allow_viewer_to_self_elevate(access_http):
    server, service, key = access_http
    before = service.view()
    viewer = AccessMember(
        principal_id="viewer",
        label="Viewer",
        roles=("viewer",),
        status="active",
        os_identity="test:viewer",
    )
    candidate = before.model_copy(
        update={
            "revision": 2,
            "previous_digest": before.digest,
            "members": (*before.members, viewer),
        }
    )
    service.commit(signed(service.propose(candidate), key, before.members[0]))
    server.authorization.actor = server.authorization.actor.model_copy(
        update={"os_identity": "test:viewer"}
    )
    status, data = request(server, "/api/v1/access/session")
    assert status == 200 and data["data"]["principal_id"] == "viewer"
    current = service.view()
    status, data = request(
        server,
        "/api/v1/access/proposals",
        {
            "base_digest": current.digest,
            "mutations": [
                {
                    "kind": "member.set",
                    "member": viewer.model_copy(update={"roles": ("owner",)}).model_dump(
                        mode="json"
                    ),
                }
            ],
        },
    )
    assert status == 403 and data["error"]["code"] == "POLICY_BLOCKED"
    assert service.view().digest == current.digest


def test_unsigned_owner_activation_and_extra_actor_fields_rejected(access_http):
    server, service, key = access_http
    before = service.view()
    candidate = before.model_copy(update={"revision": 2, "previous_digest": before.digest})
    proposal = service.propose(candidate)
    revision = signed(proposal, key, before.members[0])
    forged = revision.model_copy(
        update={
            "proofs": (
                revision.proofs[0].model_copy(update={"signature": "ed25519:public-key-hmac"}),
            )
        }
    )
    assert request(server, "/api/v1/access/activate", forged.model_dump(mode="json"))[0] == 403
    assert (
        request(
            server,
            "/api/v1/access/proposals",
            {"actor": "owner", "base_digest": before.digest, "mutations": []},
        )[0]
        == 409
    )
    assert service.view().digest == before.digest
