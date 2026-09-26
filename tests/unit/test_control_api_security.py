"""Adversarial security validation for the Local Control API (Master Plan Section 15.6)."""

import http.client
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from migration_agent.adapters.control_api import InMemoryEventBroadcaster, LoopbackControlServer
from migration_agent.application.control_service import ControlApiService
from migration_agent.ports.checkpoints import OperationalCheckpoint


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
    server = LoopbackControlServer(
        control_service=service,
        target_root=tmp_path,
        broadcaster=broadcaster,
    )
    server.start(host="127.0.0.1", port=port, session_token=session_token)
    yield {
        "server": server,
        "service": service,
        "port": port,
        "token": session_token,
        "target_root": tmp_path,
        "broadcaster": broadcaster,
    }
    server.stop()


def test_loopback_only_binding_enforced(tmp_path: Path) -> None:
    service = ControlApiService()
    server = LoopbackControlServer(control_service=service, target_root=tmp_path)
    with pytest.raises(ValueError, match="must bind strictly to loopback"):
        server.start(host="0.0.0.0", port=9000, session_token="tok")

    with pytest.raises(ValueError, match="must bind strictly to loopback"):
        server.start(host="192.168.1.100", port=9000, session_token="tok")


def test_session_authentication_required(running_server: dict[str, Any]) -> None:
    port = running_server["port"]
    # Request without token returns 401 Unauthorized
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request("GET", "/api/v1/health")
    resp = conn.getresponse()
    assert resp.status == 401
    body = json.loads(resp.read().decode())
    assert body["status"] == "error"
    assert body["error"]["code"] == "UNAUTHORIZED"

    # Request with invalid token returns 401
    conn.request("GET", "/api/v1/health", headers={"X-Session-Token": "bad-token"})
    resp = conn.getresponse()
    assert resp.status == 401

    # Request with valid X-Session-Token returns 200 OK
    conn.request("GET", "/api/v1/health", headers={"X-Session-Token": running_server["token"]})
    resp = conn.getresponse()
    assert resp.status == 200
    body = json.loads(resp.read().decode())
    assert body["status"] == "ok"
    assert body["data"]["status"] == "ok"

    # Request with Authorization: Bearer <token> returns 200 OK
    conn.request(
        "GET", "/api/v1/health", headers={"Authorization": f"Bearer {running_server['token']}"}
    )
    resp = conn.getresponse()
    assert resp.status == 200

    # Request with query parameter ?token=<token> returns 200 OK
    conn.request("GET", f"/api/v1/health?token={running_server['token']}")
    resp = conn.getresponse()
    assert resp.status == 200
    conn.close()


def test_strict_origin_validation(running_server: dict[str, Any]) -> None:
    port = running_server["port"]
    token = running_server["token"]
    conn = http.client.HTTPConnection("127.0.0.1", port)

    # Cross-origin request from malicious website is blocked with 403 Forbidden
    headers = {
        "X-Session-Token": token,
        "Origin": "http://evil-attacker.com:8080",
    }
    conn.request("GET", "/api/v1/health", headers=headers)
    resp = conn.getresponse()
    assert resp.status == 403
    body = json.loads(resp.read().decode())
    assert body["error"]["code"] == "FORBIDDEN_ORIGIN"

    # Same-origin loopback request is allowed
    loopback_origin_headers = {
        "X-Session-Token": token,
        "Origin": f"http://127.0.0.1:{port}",
    }
    conn.request("GET", "/api/v1/health", headers=loopback_origin_headers)
    resp = conn.getresponse()
    assert resp.status == 200
    conn.close()


def test_csrf_defense_for_state_changing_operations(running_server: dict[str, Any]) -> None:
    port = running_server["port"]
    token = running_server["token"]
    conn = http.client.HTTPConnection("127.0.0.1", port)

    # POST request without X-CSRF-Token is rejected with 403 Forbidden
    headers_without_csrf = {
        "X-Session-Token": token,
        "Content-Type": "application/json",
    }
    conn.request(
        "POST",
        "/api/v1/plans/p-1/approve",
        body=json.dumps({"actor": "admin"}),
        headers=headers_without_csrf,
    )
    resp = conn.getresponse()
    assert resp.status == 403
    body = json.loads(resp.read().decode())
    assert body["error"]["code"] == "CSRF_REJECTED"

    # POST request with mismatched X-CSRF-Token is rejected
    headers_bad_csrf = {
        "X-Session-Token": token,
        "X-CSRF-Token": "wrong-csrf-token",
        "Content-Type": "application/json",
    }
    conn.request(
        "POST",
        "/api/v1/plans/p-1/approve",
        body=json.dumps({"actor": "admin"}),
        headers=headers_bad_csrf,
    )
    resp = conn.getresponse()
    assert resp.status == 403

    conn.close()


def test_websocket_handshake_security(running_server: dict[str, Any]) -> None:
    port = running_server["port"]
    token = running_server["token"]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", port))

    # Handshake without token returns 401
    unauth_req = (
        f"GET /api/v1/ws HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(unauth_req.encode())
    resp = sock.recv(1024).decode()
    assert "401 Unauthorized" in resp
    sock.close()

    # Handshake with external origin is blocked (403)
    sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock2.connect(("127.0.0.1", port))
    evil_req = (
        f"GET /api/v1/ws?token={token} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Origin: http://evil.com:8080\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock2.sendall(evil_req.encode())
    resp2 = sock2.recv(1024).decode()
    assert "403 Forbidden" in resp2
    sock2.close()

    # Handshake with valid token and loopback origin succeeds (101 Switching Protocols)
    sock3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock3.connect(("127.0.0.1", port))
    valid_req = (
        f"GET /api/v1/ws?token={token} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Origin: http://127.0.0.1:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock3.sendall(valid_req.encode())
    resp3 = sock3.recv(1024).decode()
    assert "101 Switching Protocols" in resp3
    assert "Sec-WebSocket-Accept" in resp3
    assert running_server["broadcaster"].client_count() >= 1

    # Send close frame
    sock3.sendall(bytes([0x88, 0x00]))
    sock3.close()


def test_terminal_states_presentation(tmp_path: Path) -> None:
    """Validate that RecoveryRequired and BaseChanged terminal states are formatted cleanly."""
    from migration_agent.adapters.checkpoints import SqliteCheckpointStore
    from migration_agent.domain import ExecutionStep, RunRecord

    db_path = tmp_path / "checkpoints.db"
    store = SqliteCheckpointStore(db_path)

    # Record failed run with RECOVERY_REQUIRED checkpoint
    store.save_run_record(
        RunRecord(
            run_id="run-recovery-test",
            plan_id="plan-rec",
            source_root=str(tmp_path),
            status=ExecutionStep.FAILED,
        )
    )
    store.save_checkpoint(
        OperationalCheckpoint(
            checkpoint_id="cp-rec-1",
            run_id="run-recovery-test",
            checkpoint_type="RECOVERY_REQUIRED",
            state_data={
                "reason": "Mid-apply disk write failure.",
                "affected_files": ["src/app.component.ts"],
                "recovery_actions": ["Manually review disk state", "Re-run controlled apply"],
            },
        )
    )

    service = ControlApiService(checkpoint_port=store)
    detail = service.get_run("run-recovery-test", tmp_path)
    assert detail.terminal_state == "RECOVERY_REQUIRED"
    assert detail.terminal_reason == "Mid-apply disk write failure."
    assert "src/app.component.ts" in detail.affected_files
    assert len(detail.recovery_actions) == 2

    # Check summary view
    summaries = service.list_runs(tmp_path)
    assert len(summaries) == 1
    assert summaries[0].has_recovery_required is True
    assert summaries[0].terminal_state == "RECOVERY_REQUIRED"
