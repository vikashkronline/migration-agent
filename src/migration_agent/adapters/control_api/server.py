"""Loopback Control API server implementing strict browser security and REST/WebSocket protocols."""

import base64
import contextlib
import hashlib
import http.cookies
import http.server
import json
import mimetypes
import re
import secrets
import socket
import struct
import subprocess
import threading
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.control_api.broadcaster import InMemoryEventBroadcaster
from migration_agent.adapters.git_directory import ProviderGitDirectory
from migration_agent.application.access_api import (
    AccessAdministration,
    AccessChangeRequest,
    GitImportRequest,
)
from migration_agent.application.control_service import ControlApiService
from migration_agent.application.workbench import WorkbenchService, WorkCommand, WorkQuestion
from migration_agent.config import Settings
from migration_agent.domain import (
    ApplyRunPayload,
    ApprovePlanPayload,
    ControlApiError,
    ControlApiErrorCode,
    ControlApiResponse,
    WebSocketEventMessage,
)
from migration_agent.domain.access import AccessDenied, AccessRevision
from migration_agent.domain.git_directory import GitDirectoryRequest
from migration_agent.domain.inspection_access import InspectionCapability, authorize_inspection
from migration_agent.domain.knowledge import DecisionStatus
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.ports import ControlApiServerPort
from migration_agent.ports.access import AuthorizationPort

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class _WebSocketClientChannel:
    """Channel wrapping a raw socket for RFC 6455 WebSocket communication."""

    def __init__(self, sock: socket.socket, permission: Callable[[], None] | None = None) -> None:
        self.sock = sock
        self._lock = threading.Lock()
        self.closed = False
        self.permission = permission

    def send_event(self, event: WebSocketEventMessage) -> None:
        """Encode and dispatch an event message as a WebSocket text frame."""
        if self.closed:
            return
        if self.permission:
            try:
                self.permission()
            except ValueError:
                self.close()
                return
        payload = json.dumps(event.model_dump(), separators=(",", ":"))
        frame = self._encode_text_frame(payload)
        with self._lock:
            try:
                self.sock.sendall(frame)
            except OSError:
                self.closed = True

    def close(self) -> None:
        """Close the underlying client socket."""
        self.closed = True
        with contextlib.suppress(OSError):
            self.sock.close()

    @staticmethod
    def _encode_text_frame(payload_str: str) -> bytes:
        data = payload_str.encode("utf-8")
        length = len(data)
        if length < 126:
            header = bytes([0x81, length])
        elif length <= 0xFFFF:
            header = bytes([0x81, 126]) + struct.pack("!H", length)
        else:
            header = bytes([0x81, 127]) + struct.pack("!Q", length)
        return header + data


class _ControlApiRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP & WebSocket request handler enforcing loopback security guardrails."""

    server: "LoopbackControlServer"  # type: ignore[assignment]

    def log_message(self, format: str, *args: Any) -> None:
        """Silence default stderr request logging."""

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests securely for loopback origin."""
        if not self._validate_origin():
            self._send_error_response(
                ControlApiErrorCode.FORBIDDEN_ORIGIN, "Origin not allowed.", 403
            )
            return
        self.send_response(204)
        self._send_security_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Session-Token, X-CSRF-Token, Authorization",
        )
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for Control API, WebSocket upgrade, SSE, or SPA static files."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. Validate Origin if present
        if not self._validate_origin():
            self._send_error_response(
                ControlApiErrorCode.FORBIDDEN_ORIGIN, "Cross-origin request rejected.", 403
            )
            return

        # 2. Check WebSocket Upgrade on /api/v1/ws
        if path == "/api/v1/ws":
            if self.server.workbench is not None:
                self._send_error_response(
                    ControlApiErrorCode.NOT_FOUND, "Use the scoped workbench event cursor.", 404
                )
                return
            if not self._validate_session(query):
                self._send_error_response(
                    ControlApiErrorCode.UNAUTHORIZED, "Valid session token required.", 401
                )
                return
            try:
                self.server.authorization.require("operation.read")
            except AccessDenied as error:
                self._send_error_response(ControlApiErrorCode.POLICY_BLOCKED, str(error), 403)
                return
            self._handle_websocket_upgrade()
            return

        # 3. Check Session Authentication for API endpoints
        if path.startswith("/api/"):
            if not self._validate_session(query):
                self._send_error_response(
                    ControlApiErrorCode.UNAUTHORIZED, "Valid session token required.", 401
                )
                return
            self._handle_api_get(path, query)
            return

        # 4. Handle Static SPA Serving (with cookie set if token passed in query)
        self._serve_static_asset(path, query)

    def do_POST(self) -> None:
        """Handle state-changing POST requests with Origin, Session, and CSRF enforcement."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. Validate Origin
        if not self._validate_origin():
            self._discard_request_body()
            self._send_error_response(
                ControlApiErrorCode.FORBIDDEN_ORIGIN, "Cross-origin request rejected.", 403
            )
            return

        # 2. Validate Session Token
        if not self._validate_session(query):
            self._discard_request_body()
            self._send_error_response(
                ControlApiErrorCode.UNAUTHORIZED, "Valid session token required.", 401
            )
            return

        # 3. Validate CSRF Token on all mutating POST requests
        if not self._validate_csrf():
            self._discard_request_body()
            self._send_error_response(
                ControlApiErrorCode.CSRF_REJECTED,
                "Valid X-CSRF-Token header required for mutating operations.",
                403,
            )
            return

        # 4. Parse request body
        body = self._read_json_body()
        self._handle_api_post(path, body)

    # ---------------- Security Checks ----------------

    def _discard_request_body(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if 0 < length <= 2_000_000:
                self.connection.settimeout(2)
                self.rfile.read(length)
        except (ValueError, OSError):
            pass

    def _validate_origin(self) -> bool:
        """Verify that Origin or Referer header matches loopback address and listening port."""
        request_host = self.headers.get("Host", "")
        if request_host not in {f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}"}:
            return False
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if not origin:
            # Direct non-browser requests or same-origin navigation
            # without Origin header are permitted
            return True

        try:
            parsed = urllib.parse.urlparse(origin)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            return False
        if parsed.username or parsed.password:
            return False

        # Allow 127.0.0.1 or localhost on the server's listening port
        if parsed.scheme == "http" and host in ("127.0.0.1", "localhost"):
            expected_port = self.server.port
            if port == expected_port:
                return True
        return False

    def _validate_session(self, query: dict[str, list[str]]) -> bool:
        """Verify the per-launch session token via headers, query params, or cookies."""
        expected_token = self.server.session_token

        # Check X-Session-Token header
        header_token = self.headers.get("X-Session-Token")
        if header_token and header_token.strip() == expected_token:
            return True

        # Check Authorization Bearer header
        auth_header = self.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            if token == expected_token:
                return True

        # Check URL query parameter (?token=...)
        if "token" in query and query["token"] and query["token"][0].strip() == expected_token:
            return True

        # Check Cookie header
        cookie_header = self.headers.get("Cookie")
        if cookie_header:
            try:
                cookies = http.cookies.SimpleCookie(cookie_header)
            except http.cookies.CookieError:
                return False
            if (
                "session_token" in cookies
                and cookies["session_token"].value.strip() == expected_token
            ):
                return True

        return False

    def _validate_csrf(self) -> bool:
        """Verify the independent workbench nonce (legacy sessions use their token)."""
        csrf_header = self.headers.get("X-CSRF-Token")
        if not csrf_header:
            return False
        expected = (
            self.server.csrf_token
            if self.server.workbench
            or self.path.startswith("/api/v1/access")
            or "/configuration" in self.path
            or "/stack" in self.path
            else self.server.session_token
        )
        return csrf_header.strip() == expected

    def _send_security_headers(self) -> None:
        """Inject strict security headers into all responses."""
        csp = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            f"connect-src 'self' ws://127.0.0.1:{self.server.port} "
            f"ws://localhost:{self.server.port}; "
            "img-src 'self' data:;"
        )
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        origin = self.headers.get("Origin")
        if origin and self._validate_origin():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")

    # ---------------- REST Handlers ----------------

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        service = self.server.control_service
        target_root = self.server.target_root

        try:
            if path == "/api/v1/session":
                from migration_agent.adapters.mcp.binding import ProjectBinding

                decision = self.server.authorization.require("project.read")
                self._send_json_response(
                    {
                        "project_id": ProjectBinding(self.server.target_root).project_id,
                        "schema_version": 1,
                        "revision": decision.access_digest or "inspection",
                        "cursor": 0,
                        "actor": self.server.actor,
                        "assurance": "MODE_B" if decision.access_digest else "MODE_C",
                        "access": decision.model_dump(mode="json"),
                    }
                )
                return
            if "/configuration" in path:
                self._handle_configuration(path, query=query)
                return
            if path.startswith("/api/v1/access"):
                self._handle_access_get(path, query)
                return
            if "/stack" in path:
                self._handle_stack_get(path, query)
                return
            self.server.authorization.require(
                "system.diagnostics"
                if path in {"/api/v1/health", "/api/v1/doctor"}
                else "project.read"
            )
            if self.server.workbench is not None and not (
                path.startswith("/api/v1/workbench") or path in {"/api/v1/health", "/api/v1/doctor"}
            ):
                raise KeyError("LEGACY_ENDPOINT_UNAVAILABLE")
            if path.startswith("/api/v1/workbench"):
                workbench = self.server.workbench
                if workbench is None:
                    raise KeyError("WORKBENCH_UNAVAILABLE")
                if path == "/api/v1/workbench":
                    snap = workbench.snapshot()
                    self._send_json_response(
                        {
                            "project_id": snap.project_id,
                            "schema_version": 1,
                            "actor": snap.actor,
                            "assurance": snap.assurance,
                            "access": self.server.authorization.require("project.read").model_dump(
                                mode="json"
                            ),
                        }
                    )
                elif path == "/api/v1/workbench/tree":
                    page = workbench.page(
                        query.get("project", [""])[0],
                        query.get("parent", [None])[0],
                        query.get("query", [""])[0],
                        int(query.get("offset", ["0"])[0]),
                        attention=query.get("attention", ["0"])[0] == "1",
                        kind=query.get("kind", [None])[0],
                    )
                    self._send_json_response(page.model_dump(mode="json"))
                elif path == "/api/v1/workbench/detail":
                    detail = workbench.detail(
                        query.get("project", [""])[0],
                        query.get("node", [""])[0],
                        query.get("revision", [""])[0],
                    )
                    self._send_json_response(detail.model_dump(mode="json"))
                elif path == "/api/v1/workbench/image":
                    image = workbench.image(
                        query.get("project", [""])[0],
                        query.get("node", [""])[0],
                        query.get("revision", [""])[0],
                        int(query.get("index", ["-1"])[0]),
                    )
                    self._send_json_response(image.model_dump(mode="json"))
                elif path == "/api/v1/workbench/diff":
                    file_diff = workbench.file_diff(
                        query.get("project", [""])[0],
                        query.get("node", [""])[0],
                        query.get("revision", [""])[0],
                        query.get("artifact", [""])[0],
                        int(query.get("index", ["-1"])[0]),
                    )
                    self._send_json_response(file_diff.model_dump(mode="json"))
                elif path == "/api/v1/workbench/events":
                    events = workbench.events(
                        query.get("project", [""])[0],
                        int(query.get("cursor", ["0"])[0]),
                        query.get("revision", [""])[0],
                    )
                    self._send_json_response(events.model_dump(mode="json"))
                else:
                    raise KeyError("ENDPOINT_NOT_FOUND")
            elif path in ("/api/v1/health", "/api/v1/doctor"):
                if self.server.workbench is not None:
                    authorize_inspection(
                        self.server.workbench.context, InspectionCapability.DIAGNOSTICS
                    )
                health = service.get_health()
                self._send_json_response(health.model_dump())
            elif path == "/api/v1/runs":
                runs = service.list_runs(target_root)
                self._send_json_response([r.model_dump() for r in runs])
            elif path.startswith("/api/v1/runs/") and path.endswith("/diff"):
                run_id = path.removeprefix("/api/v1/runs/").removesuffix("/diff")
                diff = service.get_diff(run_id, target_root)
                self._send_json_response(diff.model_dump())
            elif path.startswith("/api/v1/runs/"):
                run_id = path.removeprefix("/api/v1/runs/")
                run_detail = service.get_run(run_id, target_root)
                self._send_json_response(run_detail.model_dump())
            elif path.startswith("/api/v1/plans/"):
                plan_id = path.removeprefix("/api/v1/plans/")
                plan_view = service.get_plan(plan_id, target_root)
                self._send_json_response(plan_view.model_dump())
            elif path == "/api/v1/graph":
                graph_view = service.get_graph(target_root)
                self._send_json_response(graph_view.model_dump())
            elif path == "/api/v1/learnings":
                learnings_view = service.get_learnings(target_root)
                self._send_json_response(learnings_view.model_dump())
            elif path == "/api/v1/events":
                self._handle_sse_stream()
            else:
                self._send_error_response(
                    ControlApiErrorCode.NOT_FOUND, f"Endpoint '{path}' not found.", 404
                )
        except AccessDenied as err:
            self._send_error_response(ControlApiErrorCode.POLICY_BLOCKED, str(err), 403)
        except KeyError as err:
            self._send_error_response(ControlApiErrorCode.NOT_FOUND, str(err), 404)
        except ValueError as err:
            self._send_error_response(
                ControlApiErrorCode.INVALID_REQUEST,
                RedactionPolicy().redact_text(str(err))[:512],
                409,
            )
        except Exception:
            self._send_error_response(
                ControlApiErrorCode.INTERNAL_ERROR, "INSPECTION_FAILED: inspect local state.", 500
            )

    def _handle_api_post(self, path: str, body: dict[str, Any]) -> None:
        service = self.server.control_service
        target_root = self.server.target_root

        try:
            if "/configuration" in path:
                self._handle_configuration(path, body=body)
                return
            if path.startswith("/api/v1/access"):
                self._handle_access_post(path, body)
                return
            if "/stack" in path:
                self._handle_stack_post(path, body)
                return
            capability = (
                "provider.use"
                if path in {"/api/v1/ask", "/api/v1/contextual-qa"}
                else "evidence.read"
                if path == "/api/v1/workbench/answer"
                else "project.read"
                if path == "/api/v1/workbench/command"
                else "changeset.apply"
                if path.endswith("/apply")
                else "approval.sign"
            )
            self.server.authorization.require(capability)
            if self.server.workbench is not None and path not in {
                "/api/v1/workbench/command",
                "/api/v1/workbench/answer",
            }:
                raise ValueError("LEGACY_ACTION_UNAVAILABLE")
            if path == "/api/v1/workbench/answer":
                if self.server.workbench is None:
                    raise KeyError("WORKBENCH_UNAVAILABLE")
                try:
                    question = WorkQuestion.model_validate(body)
                except ValueError:
                    raise ValueError("QUESTION_INVALID: use a bounded scoped question.") from None
                answer = self.server.workbench.answer(question)
                self._send_json_response(answer.model_dump(mode="json"))
                return
            if path == "/api/v1/workbench/command":
                if self.server.workbench is None:
                    raise KeyError("WORKBENCH_UNAVAILABLE")
                try:
                    command = WorkCommand.model_validate(body)
                except ValueError:
                    raise ValueError(
                        "COMMAND_INVALID: use a typed, exact action request."
                    ) from None
                receipt = self.server.workbench.dispatch(command)
                self._send_json_response(receipt.model_dump(mode="json"), 202)
            elif path.startswith("/api/v1/runs/") and path.endswith("/approve"):
                run_id = path.removeprefix("/api/v1/runs/").removesuffix("/approve")
                approve_payload = ApprovePlanPayload(**body)
                # Approve plan associated with the run
                run_detail = service.get_run(run_id, target_root)
                plan_view = service.approve_plan(run_detail.plan_id, approve_payload, target_root)
                self._send_json_response(plan_view.model_dump())
            elif path.startswith("/api/v1/plans/") and path.endswith("/approve"):
                plan_id = path.removeprefix("/api/v1/plans/").removesuffix("/approve")
                approve_payload = ApprovePlanPayload(**body)
                plan_view = service.approve_plan(plan_id, approve_payload, target_root)
                self._send_json_response(plan_view.model_dump())
            elif path.startswith("/api/v1/runs/") and path.endswith("/apply"):
                run_id = path.removeprefix("/api/v1/runs/").removesuffix("/apply")
                apply_payload = ApplyRunPayload(**body)
                run_detail = service.apply_run(run_id, apply_payload, target_root)
                self._send_json_response(run_detail.model_dump())
            elif path in ("/api/v1/contextual-qa", "/api/v1/ask"):
                query_str = body.get("query", "")
                if not query_str:
                    self._send_error_response(
                        ControlApiErrorCode.INVALID_REQUEST, "Missing 'query' in request body.", 400
                    )
                    return
                qa_res = service.contextual_qa(
                    target_root,
                    query_str,
                    entity=body.get("entity"),
                    run_id=body.get("run_id"),
                )
                self._send_json_response(qa_res)
            else:
                self._send_error_response(
                    ControlApiErrorCode.NOT_FOUND, f"Endpoint '{path}' not found.", 404
                )
        except AccessDenied as err:
            self._send_error_response(ControlApiErrorCode.POLICY_BLOCKED, str(err), 403)
        except KeyError as err:
            self._send_error_response(ControlApiErrorCode.NOT_FOUND, str(err), 404)
        except ValueError as error:
            message = "ACTION_REJECTED: inspect state, scope and trusted approval."
            if path.startswith("/api/v1/access") or "/configuration" in path:
                public = (
                    str(error)
                    if not isinstance(error, ValidationError)
                    else str(error.errors(include_input=False, include_context=False)[0]["msg"])
                )
                public = public.removeprefix("Value error, ")
                if public.startswith(
                    (
                        "ACCESS_",
                        "LAST_OWNER:",
                        "GIT_",
                        "KEY_",
                        "OWNER_",
                        "ENROLLMENT_",
                        "CONFIGURATION_",
                    )
                ):
                    message = RedactionPolicy().redact_text(public)[:512]
            elif "/stack" in path:
                public = (
                    str(error)
                    if not isinstance(error, ValidationError)
                    else str(error.errors(include_input=False, include_context=False)[0]["msg"])
                )
                public = public.removeprefix("Value error, ")
                message = RedactionPolicy().redact_text(public)[:512]
            self._send_error_response(
                ControlApiErrorCode.INVALID_REQUEST,
                message,
                400 if isinstance(error, ValidationError) and "/configuration" in path else 409,
            )
        except Exception:
            self._send_error_response(
                ControlApiErrorCode.INTERNAL_ERROR, "ACTION_FAILED: inspect local state.", 500
            )

    # ---------------- WebSocket & SSE Handlers ----------------

    def _handle_configuration(
        self,
        path: str,
        *,
        query: dict[str, list[str]] | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        from migration_agent.adapters.configuration_api import ConfigurationApi
        from migration_agent.adapters.mcp.binding import ProjectBinding

        parsed = re.fullmatch(r"/api/v1/projects/([^/]+)/configuration(.*)", path)
        if (
            not parsed
            or urllib.parse.unquote(parsed.group(1))
            != ProjectBinding(self.server.target_root).project_id
        ):
            raise ValueError("CONFIGURATION_PROJECT_MISMATCH: select the bound project.")
        if not isinstance(self.server.authorization, ProjectAuthorization):
            raise AccessDenied(
                "CONFIGURATION_UNAVAILABLE: verified project authorization is required."
            )
        values: dict[str, Any] = {}
        if self.server.state_dir:
            values["state_dir"] = self.server.state_dir
        if self.server.staging_root:
            values["staging_root"] = self.server.staging_root
        api = ConfigurationApi(
            self.server.authorization, self.server.settings.model_copy(update=values)
        )
        response = (
            api.get(parsed.group(2), query or {})
            if body is None
            else api.post(parsed.group(2), body)
        )
        self._send_json_response(
            response.model_dump(mode="json") if isinstance(response, BaseModel) else response,
            202 if parsed.group(2) == "/checks" and body is not None else 200,
        )

    def _access_admin(self) -> AccessAdministration:
        authorization = self.server.authorization
        if not isinstance(authorization, ProjectAuthorization):
            raise AccessDenied(
                "ACCESS_ADMIN_UNAVAILABLE: verified project administration is required."
            )
        service = authorization.service()
        return AccessAdministration(
            service,
            ProviderGitDirectory(
                (
                    self.server.target_root,
                    Path(service.store.binding.governance_root),
                    authorization.state,
                )
            ),
            ("--state-dir", str(authorization.state), "--trust-root", str(authorization.trust)),
        )

    def _handle_access_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/v1/access/session":
            decision = self.server.authorization.require("project.read")
            self._send_json_response(decision.model_dump(mode="json"))
        elif path == "/api/v1/access":
            self._send_json_response(self._access_admin().service.view().model_dump(mode="json"))
        elif path == "/api/v1/access/capabilities":
            self.server.authorization.require("access.read")
            self._send_json_response(self._access_admin().service.catalog())
        elif path == "/api/v1/access/proposal":
            self._send_json_response(
                self._access_admin().review(query.get("id", [""])[0]).model_dump(mode="json")
            )
        elif path == "/api/v1/access/onboarding":
            self._send_json_response(
                self._access_admin()
                .onboarding(query.get("principal", [""])[0])
                .model_dump(mode="json")
            )
        else:
            raise KeyError("ACCESS_ENDPOINT_NOT_FOUND")

    def _handle_access_post(self, path: str, body: dict[str, Any]) -> None:
        admin = self._access_admin()
        if path == "/api/v1/access/proposals":
            result = admin.propose(AccessChangeRequest.model_validate_json(json.dumps(body)))
            self._send_json_response(result.model_dump(mode="json"), 201)
        elif path == "/api/v1/access/repository-preview":
            directory = admin.preview_repository(
                GitDirectoryRequest.model_validate_json(json.dumps(body))
            )
            self._send_json_response(directory.model_dump(mode="json"))
        elif path == "/api/v1/access/git-members":
            result_directory = admin.git_members(
                GitDirectoryRequest.model_validate_json(json.dumps(body))
            )
            self._send_json_response(result_directory.model_dump(mode="json"))
        elif path == "/api/v1/access/git-import":
            result = admin.import_members(GitImportRequest.model_validate_json(json.dumps(body)))
            self._send_json_response(result.model_dump(mode="json"), 201)
        elif path == "/api/v1/access/activate":
            policy = admin.service.commit(AccessRevision.model_validate_json(json.dumps(body)))
            self._send_json_response(policy.model_dump(mode="json"))
        else:
            raise KeyError("ACCESS_ENDPOINT_NOT_FOUND")

    def _parse_stack_path(self, path: str) -> tuple[str, str] | None:
        m = re.match(r"^/api/v1/projects/(?P<project_id>[^/]+)/stack/(?P<subpath>[^/?#]+)$", path)
        if m:
            return m.group("project_id"), m.group("subpath")
        m = re.match(r"^/api/v1/stack/(?P<subpath>[^/?#]+)$", path)
        if m:
            return self._bound_project_id(), m.group("subpath")
        return None

    def _bound_project_id(self) -> str:
        if self.server.workbench is not None:
            try:
                return self.server.workbench.snapshot().project_id
            except Exception:
                pass
        from migration_agent.adapters.mcp.binding import ProjectBinding

        try:
            return ProjectBinding(self.server.target_root).project_id
        except Exception:
            return "project"

    def _resolve_governance_root(self) -> Path:
        if not isinstance(self.server.authorization, ProjectAuthorization):
            raise AccessDenied(
                "SIGNED_PROJECT_REQUIRED: bootstrap an owner and external governance first."
            )
        service = self.server.authorization.service()
        service.require("project.read")
        return Path(service.store.binding.governance_root)

    def _stack_readiness(self, governance: Path) -> dict[str, Any]:
        from migration_agent.adapters.configuration_runtime import ConfigurationFacade
        from migration_agent.adapters.controlled_files import (
            LocalControlledFiles,
            destination_fingerprint,
        )
        from migration_agent.adapters.filesystem import read_repository_text
        from migration_agent.adapters.foundation_transformation import (
            FoundationTransformationAdapter,
        )
        from migration_agent.adapters.knowledge import GitKnowledgeAdapter
        from migration_agent.adapters.mcp.tools import _create_default_framework_registry
        from migration_agent.adapters.project_evidence import LocalProjectEvidence
        from migration_agent.adapters.workflow_store import SqliteWorkflowStore
        from migration_agent.domain.host_workflow import Lifecycle
        from migration_agent.domain.stack import (
            FoundationTaskChoice,
            StackReadiness,
            StackRecommendationDraft,
            compute_draft_digest,
        )
        from migration_agent.ports.filesystem import InspectionPolicy

        decisions = GitKnowledgeAdapter().list_decisions(str(governance))
        draft = None
        draft_file = governance / ".agent/drafts/stack_recommendation.json"
        if draft_file.exists():
            draft = StackRecommendationDraft.model_validate_json(
                read_repository_text(
                    governance,
                    ".agent/drafts/stack_recommendation.json",
                    policy=InspectionPolicy(max_text_file_bytes=65536),
                )
            )
            if draft.content_digest != compute_draft_digest(draft):
                draft = None
        accepted = [
            d
            for d in decisions
            if d.status == DecisionStatus.ACCEPTED
            and draft is not None
            and d.metadata.get("draft_digest") == draft.content_digest
        ]
        scopes = {d.metadata.get("scope") for d in accepted}
        architecture = {"target_framework", "ui_styling", "reactivity_state"} <= scopes
        if (
            architecture
            and draft is not None
            and isinstance(self.server.authorization, ProjectAuthorization)
        ):
            from migration_agent.adapters.foundation_transformation import verified_architecture

            try:
                manifest = verified_architecture(self.server.authorization, draft)
                accepted = [
                    decision
                    for decision in accepted
                    if f".agent/decisions/{decision.decision_id}.md" in manifest.decision_digests
                ]
                architecture = {"target_framework", "ui_styling", "reactivity_state"} <= {
                    decision.metadata.get("scope") for decision in accepted
                }
            except ValueError:
                architecture = False
        store = SqliteWorkflowStore(self._resolve_state_dir())
        authorization = self.server.authorization
        if not isinstance(authorization, ProjectAuthorization):
            raise AccessDenied("SIGNED_PROJECT_REQUIRED: bind external governance first.")
        source = LocalProjectEvidence(
            self.server.target_root, _create_default_framework_registry(), authorization
        )
        base = source.repository_state()
        architecture = architecture and draft is not None and draft.source_revision == base.revision
        rendered = {}
        if architecture:
            package = read_repository_text(
                self.server.target_root,
                "package.json",
                policy=InspectionPolicy(max_text_file_bytes=65536),
            )
            project_name = str(json.loads(package).get("name", "modern-app"))
            rendered = FoundationTransformationAdapter().render_foundation_files(
                project_name, draft=draft
            )
        effective = ConfigurationFacade(authorization, authorization.settings).runtime_settings()
        files = LocalControlledFiles(
            self.server.target_root,
            self._resolve_staging_root(),
            self._resolve_state_dir(),
            effective.final_target_root,
        )
        staged = validated = published = False
        choices = []
        try:
            authorization.require("plan.read")
            show_tasks = True
        except AccessDenied:
            show_tasks = False
        for plan in store.list_plans():
            if Path(plan.source_root).resolve() != self.server.target_root.resolve():
                continue
            for step in plan.steps:
                if step.scope != "foundation":
                    continue
                try:
                    record = store.get_workflow(
                        self._bound_project_id(), plan.plan_id, step.step_id
                    )
                    if (
                        show_tasks
                        and record.state == Lifecycle.PLAN_SAVED
                        and base.clean
                        and record.base_revision == base.revision
                        and record.worktree_fingerprint == base.fingerprint
                        and record.policy_digest == source.policy_digest()
                    ):
                        choices.append(
                            FoundationTaskChoice(
                                plan_id=plan.plan_id,
                                step_id=step.step_id,
                                title=step.title,
                                state=record.state.value,
                            )
                        )
                    changeset = store.get_changeset(record.changeset_id or "")
                    if (
                        not architecture
                        or not changeset
                        or changeset.destination is None
                        or changeset.destination.root != files.destination_root
                        or (
                            draft is not None and record.architecture_digest != draft.content_digest
                        )
                        or not base.clean
                        or (
                            record.base_revision != base.revision
                            or record.worktree_fingerprint != base.fingerprint
                            or record.policy_digest != source.policy_digest()
                            or {c.path: c.content_bytes for c in changeset.changes}
                            != {p: c.encode() for p, c in rendered.items()}
                            or not record.staging_path
                            or files.verify_staging(record.staging_path, changeset)
                            != record.staging_fingerprint
                        )
                    ):
                        continue
                    staged = staged or record.state in {
                        Lifecycle.STAGE_VERIFIED,
                        Lifecycle.VALIDATION_PASSED,
                        Lifecycle.APPROVAL_PENDING,
                        Lifecycle.APPROVAL_RECORDED,
                        Lifecycle.APPLY_COMPLETED,
                    }
                    validated = validated or record.state in {
                        Lifecycle.VALIDATION_PASSED,
                        Lifecycle.APPROVAL_PENDING,
                        Lifecycle.APPROVAL_RECORDED,
                        Lifecycle.APPLY_COMPLETED,
                    }
                    if (
                        record.state == Lifecycle.APPLY_COMPLETED
                        and record.destination
                        and draft
                        and record.architecture_digest == draft.content_digest
                        and record.destination.root == files.destination_root
                        and effective.final_target_root
                    ):
                        published = store.destination_head(
                            record.project_id, record.destination.root
                        ) == destination_fingerprint(effective.final_target_root)
                except ValueError:
                    continue
        return StackReadiness(
            ready=architecture and published,
            architecture_accepted=architecture,
            foundation_staged=staged,
            foundation_validated=validated,
            foundation_published=published,
            accepted_decision_ids=tuple(d.decision_id for d in accepted),
            ready_for_migration=architecture and published,
            target_root=files.destination_root,
            foundation_tasks=tuple(choices),
        ).model_dump(mode="json")

    def _resolve_staging_root(self) -> Path:
        if self.server.staging_root is not None:
            return self.server.staging_root
        return self.server.settings.resolve_staging_root()

    def _resolve_state_dir(self) -> Path:
        if self.server.state_dir is not None:
            return self.server.state_dir
        return self.server.settings.resolve_state_dir()

    def _stack_draft_view(self, draft: Any, governance: Path) -> dict[str, Any]:
        from migration_agent.adapters.knowledge import GitKnowledgeAdapter
        from migration_agent.application.stack_service import StackRecommendationService
        from migration_agent.domain.stack import StackRecommendationView

        actor = self.server.authorization.require("project.read").principal_id or self.server.actor
        decisions = StackRecommendationService(
            knowledge_port=GitKnowledgeAdapter()
        ).generate_foundation_adrs(draft, str(governance), decided_by=actor)
        return StackRecommendationView(**draft.model_dump(), decisions=decisions).model_dump(
            mode="json"
        )

    def _handle_stack_get(self, path: str, query: dict[str, list[str]]) -> None:
        parsed = self._parse_stack_path(path)
        if parsed is None:
            self._send_error_response(
                ControlApiErrorCode.NOT_FOUND, f"Stack endpoint '{path}' not found.", 404
            )
            return
        project_id, subpath = parsed
        if project_id != self._bound_project_id():
            raise ValueError("PROJECT_MISMATCH: wizard request is outside the bound project.")

        if subpath == "presets":
            from migration_agent.adapters.stack_catalog import (
                get_available_target_presets,
                get_default_target_preset,
            )

            presets = get_available_target_presets()
            default = get_default_target_preset()
            self._send_json_response(
                {
                    "presets": [p.model_dump(mode="json") for p in presets],
                    "default_preset_id": default.preset_id,
                }
            )
            return

        self.server.authorization.require("project.read")
        gov_root = self._resolve_governance_root()

        from migration_agent.adapters.knowledge import GitKnowledgeAdapter

        knowledge = GitKnowledgeAdapter()

        if subpath == "analysis":
            from migration_agent.adapters.filesystem import SafeFilesystemInspector
            from migration_agent.application.stack_service import StackAnalysisService

            inspector = SafeFilesystemInspector()
            analysis_svc = StackAnalysisService(inspector=inspector, knowledge_port=knowledge)
            result = analysis_svc.analyze_source(self.server.target_root, gov_root)
            existing_adrs = knowledge.list_decisions(str(gov_root))
            self._send_json_response(
                {
                    "project_id": project_id,
                    "source_framework": result.source_framework,
                    "dependencies": [d.model_dump(mode="json") for d in result.dependencies],
                    "existing_adrs": [a.model_dump(mode="json") for a in existing_adrs],
                    "detected_presets": [
                        p.model_dump(mode="json") for p in result.detected_presets
                    ],
                    "unmapped_dependencies": [
                        d.model_dump(mode="json") for d in result.unmapped_dependencies
                    ],
                    "readiness_status": self._stack_readiness(gov_root),
                }
            )
            return

        if subpath == "status":
            self._send_json_response({"project_id": project_id, **self._stack_readiness(gov_root)})
            return

        if subpath == "draft":
            from migration_agent.domain.stack import StackRecommendationDraft

            draft_file = gov_root / ".agent" / "drafts" / "stack_recommendation.json"
            if not draft_file.exists():
                self._send_error_response(
                    ControlApiErrorCode.NOT_FOUND, "No saved draft found.", 404
                )
                return
            content = draft_file.read_text(encoding="utf-8")
            draft = StackRecommendationDraft.model_validate_json(content)
            self._send_json_response(self._stack_draft_view(draft, gov_root))
            return

        self._send_error_response(
            ControlApiErrorCode.NOT_FOUND, f"Stack endpoint '{path}' not found.", 404
        )

    def _handle_stack_post(self, path: str, body: dict[str, Any]) -> None:
        parsed = self._parse_stack_path(path)
        if parsed is None:
            self._send_error_response(
                ControlApiErrorCode.NOT_FOUND, f"Stack endpoint '{path}' not found.", 404
            )
            return
        project_id, subpath = parsed
        if project_id != self._bound_project_id():
            raise ValueError("PROJECT_MISMATCH: wizard request is outside the bound project.")
        gov_root = self._resolve_governance_root()

        from migration_agent.adapters.knowledge import GitKnowledgeAdapter

        knowledge = GitKnowledgeAdapter()

        if subpath == "draft":
            self.server.authorization.require("knowledge.write")
            preset_id = body.get("preset_id")
            custom_mappings_raw = body.get("custom_mappings") or {}

            from migration_agent.application.stack_service import (
                StackAnalysisService,
                StackRecommendationService,
            )
            from migration_agent.domain.stack import ReplacementStrategy

            custom_mappings: dict[str, ReplacementStrategy] = {}
            for k, v in custom_mappings_raw.items():
                if isinstance(v, str):
                    custom_mappings[k] = ReplacementStrategy(v)
                elif isinstance(v, ReplacementStrategy):
                    custom_mappings[k] = v

            from migration_agent.adapters.filesystem import SafeFilesystemInspector

            inspector = SafeFilesystemInspector()
            analysis_svc = StackAnalysisService(inspector=inspector, knowledge_port=knowledge)
            analysis = analysis_svc.analyze_source(self.server.target_root, gov_root)

            source_rev = "HEAD"
            gov_rev = "HEAD"
            with contextlib.suppress(Exception):
                source_rev = (
                    subprocess.run(
                        ["git", "-C", str(self.server.target_root), "rev-parse", "HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    ).stdout.strip()
                    or "HEAD"
                )
            with contextlib.suppress(Exception):
                gov_rev = (
                    subprocess.run(
                        ["git", "-C", str(gov_root), "rev-parse", "HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    ).stdout.strip()
                    or "HEAD"
                )

            rec_svc = StackRecommendationService(knowledge_port=knowledge)
            draft = rec_svc.synthesize_draft(
                analysis=analysis,
                project_id=project_id,
                preset_id=preset_id,
                custom_mappings=custom_mappings,
                source_revision=source_rev,
                governance_revision=gov_rev,
            )

            drafts_dir = gov_root / ".agent" / "drafts"
            drafts_dir.mkdir(parents=True, exist_ok=True)
            draft_path = drafts_dir / "stack_recommendation.json"
            draft_path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")

            self._send_json_response(self._stack_draft_view(draft, gov_root), 201)
            return

        if subpath == "accept-architecture":
            approving_actor = self.server.authorization.require("knowledge.approve")
            self.server.authorization.require("access.propose")
            self.server.authorization.require("rules.manage")

            expected_digest = body.get("expected_draft_digest")
            from migration_agent.application.stack_service import StackRecommendationService
            from migration_agent.domain.stack import StackRecommendationDraft

            draft_file = gov_root / ".agent" / "drafts" / "stack_recommendation.json"
            if not draft_file.exists():
                self._send_error_response(
                    ControlApiErrorCode.NOT_FOUND, "No saved draft found to accept.", 404
                )
                return

            content = draft_file.read_text(encoding="utf-8")
            draft = StackRecommendationDraft.model_validate_json(content)
            if not expected_digest or draft.content_digest != expected_digest:
                raise ValueError("DRAFT_STALE: expected digest does not match current saved draft.")

            rec_svc = StackRecommendationService(knowledge_port=knowledge)
            actor = approving_actor.principal_id or self.server.actor
            adrs = rec_svc.generate_foundation_adrs(draft, str(gov_root), decided_by=actor)
            rec_svc.accept_foundation_adrs(adrs, str(gov_root))
            accepted_adrs = [a.model_copy(update={"status": DecisionStatus.ACCEPTED}) for a in adrs]
            accepted_ids = [a.decision_id for a in accepted_adrs]
            from migration_agent.adapters.foundation_transformation import prepare_architecture

            if not isinstance(self.server.authorization, ProjectAuthorization):
                raise AccessDenied("SIGNED_PROJECT_REQUIRED: owner governance is required.")
            proposal = prepare_architecture(self.server.authorization, draft)

            self._send_json_response(
                {
                    "status": "approval_required",
                    "proposal_id": proposal.proposal_id,
                    "signing_digest": proposal.signing_digest,
                    "review_command": [
                        "agent",
                        "access",
                        "approve",
                        str(self.server.target_root),
                        proposal.proposal_id,
                        "--state-dir",
                        str(self._resolve_state_dir()),
                        "--trust-root",
                        str(self.server.authorization.trust),
                    ],
                    "accepted_adrs": [a.model_dump(mode="json") for a in accepted_adrs],
                    "accepted_decision_ids": accepted_ids,
                }
            )
            return

        if subpath == "stage-foundation":
            self.server.authorization.require("changeset.stage")
            from migration_agent.adapters.mcp.binding import ProjectBinding
            from migration_agent.adapters.workflow_runtime import WorkflowRuntime
            from migration_agent.domain.host_workflow import OperationStatus
            from migration_agent.domain.stack import FoundationStageRequest

            if not self._stack_readiness(gov_root)["architecture_accepted"]:
                raise ValueError(
                    "PREREQUISITE_FAILED: accept this draft's exact foundation ADRs first."
                )
            if not {"plan_id", "step_id", "request_id"} <= body.keys():
                raise ValueError(
                    "FOUNDATION_PLAN_REQUIRED: submit a grounded foundation plan, "
                    "then select its plan and step IDs; approval is never "
                    "fabricated."
                )
            request = FoundationStageRequest.model_validate_json(json.dumps(body))
            runtime = WorkflowRuntime(
                ProjectBinding(self.server.target_root),
                self.server.settings.model_copy(
                    update={
                        "state_dir": self._resolve_state_dir(),
                        "staging_root": self._resolve_staging_root(),
                    }
                ),
                authorization=self.server.authorization,
            )
            try:
                plan = runtime.store.get_plan(request.plan_id)
                if plan is None or not any(
                    step.step_id == request.step_id and step.scope == "foundation"
                    for step in plan.steps
                ):
                    raise ValueError("FOUNDATION_PLAN_REQUIRED: select a recorded foundation step.")
                operation = runtime.dispatch(
                    "stage", request.plan_id, request.step_id, request.request_id, background=False
                )
                if operation.status != OperationStatus.SUCCEEDED:
                    raise ValueError("FOUNDATION_STAGE_BLOCKED: " + operation.message)
                record = runtime.store.get_workflow(project_id, request.plan_id, request.step_id)
                changeset = runtime.current_changeset(record.changeset_id or "")
                self._send_json_response(
                    {
                        "status": "staged",
                        "run_id": plan.run_id,
                        "staged_directory": record.staging_path,
                        "changeset_digest": changeset.changeset_digest,
                        "file_count": len(changeset.changes),
                        "files": [c.path for c in changeset.changes],
                    }
                )
            finally:
                runtime.close()
            return

        self._send_error_response(
            ControlApiErrorCode.NOT_FOUND, f"Stack endpoint '{path}' not found.", 404
        )

    def _handle_websocket_upgrade(self) -> None:
        """Perform RFC 6455 handshake and transfer connection to client channel."""
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self._send_error_response(
                ControlApiErrorCode.INVALID_REQUEST, "Missing Sec-WebSocket-Key.", 400
            )
            return

        accept_raw = hashlib.sha1((key + _WS_GUID).encode("utf-8")).digest()
        accept_str = base64.b64encode(accept_raw).decode("utf-8")

        # Detach socket from HTTP handler and register client
        def permit_events() -> None:
            self.server.authorization.require("operation.read")

        permit_events()
        client_channel = _WebSocketClientChannel(self.connection, permit_events)
        self.server.broadcaster.register_client(client_channel)

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_str)
        self.end_headers()

        # Dispatch recent events for catch-up
        for ev in self.server.broadcaster.get_recent_events():
            self.server.authorization.require("operation.read")
            client_channel.send_event(ev)

        # Keep connection open reading incoming ping/pong/close frames
        try:
            while not client_channel.closed:
                permit_events()
                data = self.connection.recv(1024)
                if not data:
                    break
                # Opcode 8 is close frame
                if (data[0] & 0x0F) == 0x08:
                    break
        except (OSError, ValueError):
            pass
        finally:
            self.server.broadcaster.unregister_client(client_channel)
            client_channel.close()

    def _handle_sse_stream(self) -> None:
        """Fallback Server-Sent Events stream for event updates."""
        self.send_response(200)
        self._send_security_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        # Send existing recent events
        for ev in self.server.broadcaster.get_recent_events():
            payload = json.dumps(ev.model_dump())
            chunk = f"event: {ev.event_type}\ndata: {payload}\n\n".encode()
            try:
                self.wfile.write(chunk)
                self.wfile.flush()
            except OSError:
                return

    # ---------------- Static SPA Serving ----------------

    def _serve_static_asset(self, path: str, query: dict[str, list[str]]) -> None:
        """Serve pre-compiled Angular Control Center assets or fallback to index.html."""
        static_dir = self.server.static_dir
        rel_path = path.lstrip("/")
        requested = (static_dir / urllib.parse.unquote(rel_path)).resolve()
        if not requested.is_relative_to(static_dir.resolve()):
            self._send_error_response(ControlApiErrorCode.NOT_FOUND, "Asset not found.", 404)
            return
        if not rel_path or rel_path == "index.html":
            file_path = static_dir / "index.html"
        else:
            file_path = static_dir / rel_path

        # If file does not exist and no file extension in path, fallback to index.html (SPA routing)
        if not file_path.is_file() and "." not in Path(rel_path).name:
            file_path = static_dir / "index.html"

        if not file_path.is_file():
            self._send_error_response(
                ControlApiErrorCode.NOT_FOUND, f"Asset '{path}' not found.", 404
            )
            return

        try:
            content = file_path.read_bytes()
        except OSError:
            self._send_error_response(
                ControlApiErrorCode.INTERNAL_ERROR, "Failed to read asset.", 500
            )
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "text/html" if file_path.suffix == ".html" else "application/octet-stream"

        self.send_response(200)
        self._send_security_headers()
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))

        # If token query parameter was supplied on index page, set session cookie for SPA requests
        if "token" in query and query["token"] and file_path.name == "index.html":
            token = query["token"][0].strip()
            if token == self.server.session_token:
                cookie = f"session_token={token}; Path=/; HttpOnly; SameSite=Strict"
                self.send_header("Set-Cookie", cookie)

        self.end_headers()
        self.wfile.write(content)

    # ---------------- Response Helpers ----------------

    def _read_json_body(self) -> dict[str, Any]:
        content_length_str = self.headers.get("Content-Length")
        if not content_length_str:
            return {}
        try:
            length = int(content_length_str)
            maximum = (
                2_000_000
                if self.path.startswith("/api/v1/access") or "/configuration" in self.path
                else 65536
            )
            if not 0 <= length <= maximum:
                return {}
            raw = self.rfile.read(length)
            from migration_agent.domain.configuration import unique_json_object

            data = (
                json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json_object) if raw else {}
            )
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _send_json_response(self, data: Any, status_code: int = 200) -> None:
        envelope = ControlApiResponse(status="ok", data=data)
        body = envelope.model_dump_json().encode("utf-8")
        self.send_response(status_code)
        self._send_security_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if self.headers.get("X-Session-Token") == self.server.session_token:
            self.send_header(
                "Set-Cookie",
                f"session_token={self.server.session_token}; Path=/; HttpOnly; SameSite=Strict",
            )
            self.send_header(
                "Set-Cookie", f"csrf_token={self.server.csrf_token}; Path=/; SameSite=Strict"
            )
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.wfile.write(body)

    def _send_error_response(
        self, code: ControlApiErrorCode, message: str, status_code: int
    ) -> None:
        err = ControlApiError(code=code, message=message)
        envelope = ControlApiResponse(status="error", error=err)
        body = envelope.model_dump_json().encode("utf-8")
        self.send_response(status_code)
        self._send_security_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        with contextlib.suppress(BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.end_headers()
            self.wfile.write(body)


class LoopbackControlServer(ControlApiServerPort):
    """Localhost HTTP/WebSocket server strictly bound to 127.0.0.1 loopback."""

    def __init__(
        self,
        control_service: ControlApiService,
        target_root: Path,
        static_dir: Path | None = None,
        broadcaster: InMemoryEventBroadcaster | None = None,
        workbench: WorkbenchService | None = None,
        authorization: AuthorizationPort | None = None,
        staging_root: Path | None = None,
        state_dir: Path | None = None,
        settings: Settings | None = None,
        actor: str = "maintainer",
    ) -> None:
        self.control_service = control_service
        self.workbench = workbench
        self.settings = settings or (
            authorization.settings
            if isinstance(authorization, ProjectAuthorization)
            else Settings()
        )
        self.authorization = authorization or ProjectAuthorization(target_root, self.settings)
        self.target_root = target_root
        self.static_dir = static_dir or (Path(__file__).parents[2] / "ui" / "static")
        self.broadcaster = broadcaster or InMemoryEventBroadcaster()
        self.staging_root = staging_root
        self.state_dir = state_dir
        self.actor = actor
        self.host: str = "127.0.0.1"
        self.port: int = 8080
        self.session_token: str = ""
        self.csrf_token = secrets.token_urlsafe(32)
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self, host: str, port: int, session_token: str) -> None:
        """Start the loopback server binding strictly to 127.0.0.1 or localhost."""
        if host not in ("127.0.0.1", "localhost"):
            raise ValueError(
                f"Control API server must bind strictly to loopback (127.0.0.1). Rejected '{host}'."
            )

        self.host = host
        self.port = port
        self.session_token = session_token

        # Bind with SO_REUSEADDR
        handler_class = _ControlApiRequestHandler
        self._httpd = http.server.ThreadingHTTPServer((host, port), handler_class)
        self.port = self._httpd.server_port
        # Pass server reference to handler
        self._httpd.server = self  # type: ignore[attr-defined]
        self._httpd.control_service = self.control_service  # type: ignore[attr-defined]
        self._httpd.workbench = self.workbench  # type: ignore[attr-defined]
        self._httpd.authorization = self.authorization  # type: ignore[attr-defined]
        self._httpd.target_root = self.target_root  # type: ignore[attr-defined]
        self._httpd.static_dir = self.static_dir  # type: ignore[attr-defined]
        self._httpd.broadcaster = self.broadcaster  # type: ignore[attr-defined]
        self._httpd.session_token = self.session_token  # type: ignore[attr-defined]
        self._httpd.csrf_token = self.csrf_token  # type: ignore[attr-defined]
        self._httpd.port = self.port  # type: ignore[attr-defined]
        self._httpd.staging_root = self.staging_root  # type: ignore[attr-defined]
        self._httpd.state_dir = self.state_dir  # type: ignore[attr-defined]
        self._httpd.settings = self.settings  # type: ignore[attr-defined]
        self._httpd.actor = self.actor  # type: ignore[attr-defined]

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def server_port(self) -> int:
        """Return the active server port."""
        return self.port

    def stop(self) -> None:
        """Shut down the HTTP server and wait for thread termination."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_url(self) -> str:
        """Return the loopback base URL."""
        return f"http://{self.host}:{self.port}"
