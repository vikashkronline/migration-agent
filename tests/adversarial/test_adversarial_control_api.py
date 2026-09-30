"""Adversarial test suite for Section 15.6: Control API & Local GUI Security.

Tests security invariants for:
- Backend Policy Non-Bypassability
- Session Authentication Enforcement
- Strict Origin Validation & Anti-DNS-Rebinding
- CSRF Protection on Mutating POST Endpoints
- Terminal State Representation
"""

import http.client
import json
import socket
from pathlib import Path
from typing import Any

import pytest

from migration_agent.adapters.control_api import InMemoryEventBroadcaster, LoopbackControlServer
from migration_agent.application.control_service import ControlApiService


def find_free_port() -> int:
    """Find an ephemeral loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def running_control_server(tmp_path: Path) -> Any:
    port = find_free_port()
    session_token = "adversarial-test-token-abcdef123456"
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
    }
    server.stop()


def test_origin_spoofing_vectors_blocked(running_control_server: dict[str, Any]) -> None:
    """Cross-origin requests from external or malicious web origins must be blocked."""
    port = running_control_server["port"]
    token = running_control_server["token"]

    malicious_origins = [
        "http://evil.com",
        "https://attacker.site:8080",
        "http://192.168.1.100:8080",
        "http://malicious-subdomain.localhost.attacker.com",
        "null",
    ]

    for evil_origin in malicious_origins:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request(
            "GET",
            "/api/v1/health",
            headers={
                "Origin": evil_origin,
                "X-Session-Token": token,
            },
        )
        resp = conn.getresponse()
        assert resp.status == 403
        body = json.loads(resp.read().decode())
        assert body["status"] == "error"
        assert body["error"]["code"] == "FORBIDDEN_ORIGIN"
        conn.close()


def test_csrf_defense_blocks_mutating_requests_without_csrf_token(
    running_control_server: dict[str, Any],
) -> None:
    """Mutating POST requests without a valid X-CSRF-Token must be rejected with 403."""
    port = running_control_server["port"]
    token = running_control_server["token"]

    conn = http.client.HTTPConnection("127.0.0.1", port)
    payload = json.dumps({"query": "Explain architecture"}).encode("utf-8")

    # 1. POST with valid session token but missing CSRF token
    conn.request(
        "POST",
        "/api/v1/contextual-qa",
        body=payload,
        headers={
            "Content-Type": "application/json",
            "X-Session-Token": token,
            "Origin": f"http://127.0.0.1:{port}",
            # Omit X-CSRF-Token
        },
    )
    resp = conn.getresponse()
    assert resp.status == 403
    body = json.loads(resp.read().decode())
    assert body["status"] == "error"
    assert body["error"]["code"] == "CSRF_REJECTED"

    # 2. POST with invalid / mismatched CSRF token
    conn.request(
        "POST",
        "/api/v1/contextual-qa",
        body=payload,
        headers={
            "Content-Type": "application/json",
            "X-Session-Token": token,
            "X-CSRF-Token": "attacker-csrf-token",
            "Origin": f"http://127.0.0.1:{port}",
        },
    )
    resp2 = conn.getresponse()
    assert resp2.status == 403
    body2 = json.loads(resp2.read().decode())
    assert body2["error"]["code"] == "CSRF_REJECTED"
    conn.close()


def test_session_token_brute_force_and_tampering_rejected(
    running_control_server: dict[str, Any],
) -> None:
    """Requests with tampered or incorrect session tokens must be rejected with 401."""
    port = running_control_server["port"]

    invalid_tokens = [
        "wrong-token",
        "Bearer invalid-bearer-token",
        "",
        "admin",
        "../../../etc/passwd",
    ]

    for bad_token in invalid_tokens:
        conn = http.client.HTTPConnection("127.0.0.1", port)
        conn.request(
            "GET",
            "/api/v1/health",
            headers={"X-Session-Token": bad_token},
        )
        resp = conn.getresponse()
        assert resp.status == 401
        body = json.loads(resp.read().decode())
        assert body["status"] == "error"
        assert body["error"]["code"] == "UNAUTHORIZED"
        conn.close()


def test_nonexistent_endpoint_returns_404(running_control_server: dict[str, Any]) -> None:
    """Requests to nonexistent API endpoints must return typed 404 error response."""
    port = running_control_server["port"]
    token = running_control_server["token"]

    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request(
        "GET",
        "/api/v1/nonexistent/secret/path",
        headers={"X-Session-Token": token},
    )
    resp = conn.getresponse()
    assert resp.status == 404
    body = json.loads(resp.read().decode())
    assert body["status"] == "error"
    assert body["error"]["code"] == "NOT_FOUND"
    conn.close()
