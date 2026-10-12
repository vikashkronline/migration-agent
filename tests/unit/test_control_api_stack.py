"""Unit tests for Control API stack recommender and foundation endpoints (Milestone F3)."""

import http.client
import json
import socket
from pathlib import Path
from typing import Any

import pytest
from security_project import security_project
from test_access import signed

from migration_agent.adapters.control_api import InMemoryEventBroadcaster, LoopbackControlServer
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.application.control_service import ControlApiService


def find_free_port() -> int:
    """Find an available local port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def running_server(tmp_path: Path) -> Any:
    port = find_free_port()
    session_token = "secret-session-token-1234567890abcdef"
    broadcaster = InMemoryEventBroadcaster()
    service = ControlApiService(event_broadcaster=broadcaster)

    # Prepare minimal source package.json
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "sample-legacy-app",
                "dependencies": {
                    "angular": "1.8.2",
                    "angular-route": "1.8.2",
                    "lodash": "4.17.21",
                },
                "devDependencies": {
                    "karma": "6.3.0",
                },
            }
        ),
        encoding="utf-8",
    )

    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    authorization, owner, key = security_project(tmp_path, source_dir)
    authorization.settings = authorization.settings.model_copy(
        update={
            "local_config_root": tmp_path / "preferences",
            "final_target_root": tmp_path / "target",
        }
    )

    server = LoopbackControlServer(
        control_service=service,
        target_root=source_dir,
        broadcaster=broadcaster,
        staging_root=staging_dir,
        state_dir=state_dir,
        authorization=authorization,
        settings=authorization.settings,
    )
    server.start(host="127.0.0.1", port=port, session_token=session_token)
    yield {
        "server": server,
        "service": service,
        "port": port,
        "token": session_token,
        "source_dir": source_dir,
        "staging_dir": staging_dir,
        "state_dir": state_dir,
        "project_id": ProjectBinding(source_dir).project_id,
        "authorization": authorization,
        "owner": owner,
        "key": key,
    }
    server.stop()


def _request(
    server_info: dict[str, Any],
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    sign: bool = True,
) -> tuple[int, dict[str, Any]]:
    conn = http.client.HTTPConnection("127.0.0.1", server_info["port"])
    headers = {
        "X-Session-Token": server_info["token"],
        "X-CSRF-Token": server_info["server"].csrf_token,
        "Content-Type": "application/json",
    }
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else None
    path = path.replace("/projects/default/", "/projects/" + server_info["project_id"] + "/")
    conn.request(method, path, body=body_bytes, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw}
    if isinstance(data, dict) and data.get("status") == "ok" and "data" in data:
        data = data["data"]
    if (
        sign
        and resp.status == 200
        and path.endswith("/stack/accept-architecture")
        and data.get("proposal_id")
    ):
        # HTTP only prepares the proposal; this fixture supplies genuine independent owner signing.
        owner = server_info["owner"]
        proposal = owner.store.proposal(data["proposal_id"])
        assert proposal.candidate.digest != owner.view().digest
        owner.commit(signed(proposal, server_info["key"], owner.view().members[0]))
    return resp.status, data


def test_get_presets(running_server: dict[str, Any]) -> None:
    status, data = _request(running_server, "GET", "/api/v1/projects/default/stack/presets")
    assert status == 200
    assert "presets" in data
    assert len(data["presets"]) >= 1
    assert data["default_preset_id"] == "angular-21-bootstrap5"

    # Also test shorthand path
    status2, data2 = _request(running_server, "GET", "/api/v1/stack/presets")
    assert status2 == 200
    assert data2["default_preset_id"] == "angular-21-bootstrap5"


def test_get_analysis(running_server: dict[str, Any]) -> None:
    status, data = _request(running_server, "GET", "/api/v1/projects/default/stack/analysis")
    assert status == 200
    assert "dependencies" in data
    assert len(data["dependencies"]) == 4
    assert data["readiness_status"]["architecture_accepted"] is False
    assert len(data["readiness_status"]["accepted_decision_ids"]) == 0


def test_draft_synthesis_and_retrieval(running_server: dict[str, Any]) -> None:
    payload = {
        "preset_id": "angular-17-lts-bootstrap5",
        "custom_mappings": {
            "lodash": "replace",
        },
    }
    status, data = _request(
        running_server, "POST", "/api/v1/projects/default/stack/draft", body=payload
    )
    assert status in (200, 201)
    draft = data
    assert draft["preset"]["preset_id"] == "angular-17-lts-bootstrap5"
    digest = draft["content_digest"]
    assert digest.startswith("sha256:")

    # Retrieve saved draft
    get_status, get_data = _request(running_server, "GET", "/api/v1/projects/default/stack/draft")
    assert get_status == 200
    assert get_data["content_digest"] == digest


def test_accept_architecture_lifecycle(running_server: dict[str, Any]) -> None:
    # 1. First synthesize draft
    _request(
        running_server,
        "POST",
        "/api/v1/projects/default/stack/draft",
        body={"preset_id": "angular-17-lts-bootstrap5", "custom_mappings": {"karma": "deferred"}},
    )
    _, get_data = _request(running_server, "GET", "/api/v1/projects/default/stack/draft")
    valid_digest = get_data["content_digest"]

    # 2. Reject stale digest (409 Conflict)
    bad_status, _ = _request(
        running_server,
        "POST",
        "/api/v1/projects/default/stack/accept-architecture",
        body={"expected_draft_digest": "sha256:stale-invalid-digest"},
    )
    assert bad_status in (400, 409)

    # 3. Accept with valid digest
    ok_status, ok_data = _request(
        running_server,
        "POST",
        "/api/v1/projects/default/stack/accept-architecture",
        body={"expected_draft_digest": valid_digest},
    )
    assert ok_status == 200
    assert ok_data["status"] == "approval_required"
    assert len(ok_data["accepted_decision_ids"]) == 3


def test_accepted_flags_require_owner_signature_and_sealed_adrs(running_server) -> None:
    from migration_agent.adapters.foundation_transformation import (
        BoundFoundationTransformationAdapter,
    )

    _request(
        running_server,
        "POST",
        "/api/v1/stack/draft",
        body={
            "preset_id": "angular-21-bootstrap5",
            "custom_mappings": {
                "angular": "deferred",
                "angular-route": "deferred",
                "karma": "deferred",
            },
        },
    )
    _, draft = _request(running_server, "GET", "/api/v1/stack/draft")
    _, handoff = _request(
        running_server,
        "POST",
        "/api/v1/stack/accept-architecture",
        body={"expected_draft_digest": draft["content_digest"]},
        sign=False,
    )
    adapter = BoundFoundationTransformationAdapter(running_server["authorization"])
    with pytest.raises(ValueError, match="FOUNDATION_ARCHITECTURE_REQUIRED"):
        adapter.confirmed_draft()
    owner = running_server["owner"]
    owner.commit(
        signed(
            owner.store.proposal(handoff["proposal_id"]),
            running_server["key"],
            owner.view().members[0],
        )
    )
    assert adapter.confirmed_draft().content_digest == draft["content_digest"]
    governance = Path(owner.view().binding.governance_root)
    decision = next((governance / ".agent/decisions").glob("*.md"))
    original = decision.read_bytes()
    decision.write_bytes(original + b"\nUnapproved architecture change\n")
    with pytest.raises(ValueError, match=r"RULES_CHANGED|ARCHITECTURE_CHANGED"):
        adapter.confirmed_draft()


def test_stage_foundation_prerequisite_and_staging(running_server: dict[str, Any]) -> None:
    # 1. Synthesize draft
    _request(
        running_server,
        "POST",
        "/api/v1/projects/default/stack/draft",
        body={"preset_id": "angular-17-lts-bootstrap5"},
    )

    # 2. Try to stage foundation before accepting ADRs -> PREREQUISITE_FAILED (409 Conflict)
    fail_status, _ = _request(
        running_server,
        "POST",
        "/api/v1/projects/default/stack/stage-foundation",
        body={},
    )
    assert fail_status in (400, 409)

    # 3. Accept architecture ADRs
    _, get_data = _request(running_server, "GET", "/api/v1/projects/default/stack/draft")
    valid_digest = get_data["content_digest"]
    acc_status, _ = _request(
        running_server,
        "POST",
        "/api/v1/projects/default/stack/accept-architecture",
        body={"expected_draft_digest": valid_digest},
    )
    assert acc_status == 200

    # Accepted architecture cannot manufacture a missing grounded foundation plan.
    stage_status, stage_data = _request(
        running_server,
        "POST",
        "/api/v1/projects/default/stack/stage-foundation",
        body={},
    )
    assert stage_status in (400, 409)
    assert "FOUNDATION_PLAN_REQUIRED" in json.dumps(stage_data)

    # 5. Check status endpoint reflects accepted architecture and staged foundation
    stat_status, stat_data = _request(
        running_server, "GET", "/api/v1/projects/default/stack/status"
    )
    assert stat_status == 200
    assert stat_data["architecture_accepted"] is True
    assert stat_data["foundation_staged"] is False
    assert stat_data["ready_for_migration"] is False
    assert not (running_server["source_dir"] / ".agent").exists()


def test_foundation_uses_grounded_plan_and_durable_stage_without_fake_approval(running_server):
    import hashlib

    from migration_agent.adapters.workflow_runtime import WorkflowRuntime
    from migration_agent.domain.analysis import AnalysisFinding, EvidenceReference
    from migration_agent.domain.host_workflow import (
        AnalysisProposal,
        EvidenceCitation,
        OperationStatus,
        PlanProposal,
    )
    from migration_agent.domain.planning import MigrationStep

    info = running_server
    _request(
        info,
        "POST",
        "/api/v1/projects/default/stack/draft",
        body={
            "preset_id": "angular-17-lts-bootstrap5",
            "custom_mappings": {
                "karma": "deferred",
                "angular-route": "deferred",
                "angular": "deferred",
                "lodash": "deferred",
            },
        },
    )
    _, draft = _request(info, "GET", "/api/v1/projects/default/stack/draft")
    assert (
        _request(
            info,
            "POST",
            "/api/v1/projects/default/stack/accept-architecture",
            body={"expected_draft_digest": draft["content_digest"]},
        )[0]
        == 200
    )
    authorization = info["authorization"]
    runtime = WorkflowRuntime(
        ProjectBinding(info["source_dir"]), authorization.settings, authorization=authorization
    )
    try:
        host = runtime.proposals
        state = host.evidence.repository_state()
        text = host.evidence.read_text("package.json")
        citation = EvidenceCitation(
            path="package.json", sha256=hashlib.sha256(text.encode()).hexdigest()
        )
        evidence = EvidenceReference(
            path="package.json", description="Declared source dependencies"
        )
        analysis = host.submit_analysis(
            "foundation-analysis",
            AnalysisProposal(
                base_revision=state.revision,
                worktree_fingerprint=state.fingerprint,
                summary="Initialize the accepted foundation",
                citations=(citation,),
                findings=(
                    AnalysisFinding(
                        id="foundation-dependencies",
                        title="Dependencies",
                        description="Source package inventory",
                        category="dependency",
                        severity="low",
                        confidence=1,
                        evidence_references=(evidence,),
                    ),
                ),
            ),
        )
        assert analysis.status == OperationStatus.SUCCEEDED, analysis.message
        plan = host.submit_plan(
            "foundation-plan",
            PlanProposal(
                base_revision=state.revision,
                worktree_fingerprint=state.fingerprint,
                analysis_id=analysis.analysis_id,
                citations=(citation,),
                steps=(
                    MigrationStep(
                        step_id="foundation",
                        title="Initialize accepted foundation",
                        description="Use the accepted preset",
                        scope="foundation",
                        evidence=[evidence],
                        expected_files=[
                            "package.json",
                            "tsconfig.json",
                            "tsconfig.app.json",
                            "angular.json",
                            "src/main.ts",
                            "src/index.html",
                            "src/app/app.config.ts",
                            "src/app/app.routes.ts",
                            "src/app/app.component.ts",
                            "src/styles.scss",
                        ],
                        validation_strategy=["build"],
                    ),
                    MigrationStep(
                        step_id="later-functional",
                        title="Dependent functional task",
                        description="Generate only after validated foundation",
                        scope="component",
                        dependencies=["foundation"],
                        evidence=[evidence],
                        expected_files=["package.json"],
                        validation_strategy=["typecheck"],
                    ),
                ),
            ),
        )
        assert plan.status == OperationStatus.SUCCEEDED, plan.message
        status, result = _request(
            info,
            "POST",
            "/api/v1/projects/default/stack/stage-foundation",
            body={
                "plan_id": plan.plan_id,
                "step_id": "foundation",
                "request_id": "stage-foundation",
            },
        )
        assert status == 200, result
        assert result["file_count"] == 15
        assert host.checkpoints.get_plan(plan.plan_id).approval is None
        assert host.evidence.repository_state() == state
        status, result = _request(info, "GET", "/api/v1/projects/default/stack/status")
        assert status == 200 and result["foundation_staged"] is True
        assert result["foundation_validated"] is False and result["ready_for_migration"] is False
        dependent = runtime.dispatch(
            "stage", plan.plan_id, "later-functional", "blocked-functional", background=False
        )
        assert dependent.status == OperationStatus.FAILED
        assert "FOUNDATION_PUBLICATION_REQUIRED" in dependent.message
    finally:
        runtime.close()
