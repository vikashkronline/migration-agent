"""Actual loopback adapter rejects unbound, stale and forged workbench requests."""

import http.client
import json
from pathlib import Path

from migration_agent.adapters.control_api.server import LoopbackControlServer
from migration_agent.adapters.workbench import CanonicalWorkbench
from migration_agent.application.control_service import ControlApiService
from migration_agent.application.workbench import WorkbenchService
from migration_agent.config import Settings
from migration_agent.domain.inspection_access import InspectionCapability, InspectionContext
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.workflow_access import WorkflowCapability, WorkflowContext


def test_real_workbench_http_boundary(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    source = CanonicalWorkbench(
        root,
        Settings(
            state_dir=tmp_path / "state",
            staging_root=tmp_path / "staging",
        ),
        WorkflowContext(
            actor="operator",
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(WorkflowCapability),
        ),
    )
    api = WorkbenchService(
        source,
        InspectionContext(
            actor="operator",
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(InspectionCapability),
        ),
    )
    server = LoopbackControlServer(
        ControlApiService(),
        source.binding.project_root,
        workbench=api,
        authorization=source.authorization,
    )
    server.start("127.0.0.1", 0, "fixture-session")
    conn = http.client.HTTPConnection("127.0.0.1", server.port)
    headers = {
        "X-Session-Token": "fixture-session",
        "X-CSRF-Token": server.csrf_token,
        "Content-Type": "application/json",
    }
    try:
        conn.request("GET", "/api/v1/workbench", headers=headers)
        response = conn.getresponse()
        assert response.status == 200
        project = json.loads(response.read())["data"]["project_id"]
        assert "unsafe-eval" not in response.getheader("Content-Security-Policy")
        snapshot = api.snapshot()
        conn.request(
            "POST",
            "/api/v1/workbench/answer",
            json.dumps(
                {
                    "project_id": project,
                    "node_id": "project",
                    "revision": snapshot.revision,
                    "question": "What is the current status?",
                }
            ),
            headers=headers,
        )
        answer_response = conn.getresponse()
        assert answer_response.status == 200
        assert json.loads(answer_response.read())["data"]["mode"] == "recorded_evidence"
        cookies = [v.split(";", 1)[0] for k, v in response.getheaders() if k == "Set-Cookie"]
        conn.request("GET", "/api/v1/workbench", headers={"Cookie": "; ".join(cookies)})
        response = conn.getresponse()
        assert response.status == 200
        response.read()
        conn.request(
            "GET", "/api/v1/workbench", headers={**headers, "Origin": "http://localhost:invalid"}
        )
        response = conn.getresponse()
        assert response.status == 403
        response.read()
        conn.request(
            "POST",
            "/api/v1/workbench/command",
            "{}",
            headers={**headers, "X-CSRF-Token": "fixture-session"},
        )
        response = conn.getresponse()
        assert response.status == 403
        response.read()
        conn.request("GET", "/api/v1/ws", headers=headers)
        response = conn.getresponse()
        assert response.status == 404
        response.read()
        conn.request("GET", "/api/v1/workbench/tree?project=foreign", headers=headers)
        response = conn.getresponse()
        assert response.status == 409
        response.read()
        conn.request("GET", "/api/v1/plans/foreign", headers=headers)
        response = conn.getresponse()
        assert response.status == 404
        response.read()
        conn.request(
            "POST",
            "/api/v1/workbench/command",
            json.dumps(
                {
                    "project_id": project,
                    "node_id": "project",
                    "expected_revision": "old",
                    "request_id": "r-1",
                    "kind": "approve",
                    "actor": "admin",
                }
            ),
            headers=headers,
        )
        response = conn.getresponse()
        assert response.status == 409
        response.read()
        conn.request("GET", "/../../pyproject.toml", headers=headers)
        response = conn.getresponse()
        assert response.status == 404
        response.read()
    finally:
        conn.close()
        server.stop()
        source.close()
