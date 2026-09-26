"""Loopback Control API server implementing strict browser security and REST/WebSocket protocols."""

import base64
import contextlib
import hashlib
import http.cookies
import http.server
import json
import mimetypes
import socket
import struct
import threading
import urllib.parse
from pathlib import Path
from typing import Any

from migration_agent.adapters.control_api.broadcaster import InMemoryEventBroadcaster
from migration_agent.application.control_service import ControlApiService
from migration_agent.domain import (
    ApplyRunPayload,
    ApprovePlanPayload,
    ControlApiError,
    ControlApiErrorCode,
    ControlApiResponse,
    WebSocketEventMessage,
)
from migration_agent.ports import ControlApiServerPort

_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class _WebSocketClientChannel:
    """Channel wrapping a raw socket for RFC 6455 WebSocket communication."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self._lock = threading.Lock()
        self.closed = False

    def send_event(self, event: WebSocketEventMessage) -> None:
        """Encode and dispatch an event message as a WebSocket text frame."""
        if self.closed:
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
            if not self._validate_session(query):
                self._send_error_response(
                    ControlApiErrorCode.UNAUTHORIZED, "Valid session token required.", 401
                )
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
            self._send_error_response(
                ControlApiErrorCode.FORBIDDEN_ORIGIN, "Cross-origin request rejected.", 403
            )
            return

        # 2. Validate Session Token
        if not self._validate_session(query):
            self._send_error_response(
                ControlApiErrorCode.UNAUTHORIZED, "Valid session token required.", 401
            )
            return

        # 3. Validate CSRF Token on all mutating POST requests
        if not self._validate_csrf():
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

    def _validate_origin(self) -> bool:
        """Verify that Origin or Referer header matches loopback address and listening port."""
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if not origin:
            # Direct non-browser requests or same-origin navigation
            # without Origin header are permitted
            return True

        parsed = urllib.parse.urlparse(origin)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Allow 127.0.0.1 or localhost on the server's listening port
        if host in ("127.0.0.1", "localhost"):
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
            cookies = http.cookies.SimpleCookie(cookie_header)
            if (
                "session_token" in cookies
                and cookies["session_token"].value.strip() == expected_token
            ):
                return True

        return False

    def _validate_csrf(self) -> bool:
        """Verify X-CSRF-Token matches the active session token."""
        csrf_header = self.headers.get("X-CSRF-Token")
        if not csrf_header:
            return False
        return csrf_header.strip() == self.server.session_token

    def _send_security_headers(self) -> None:
        """Inject strict security headers into all responses."""
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            f"connect-src 'self' ws://127.0.0.1:{self.server.port} "
            f"ws://localhost:{self.server.port}; "
            "img-src 'self' data:;"
        )
        self.send_header("Content-Security-Policy", csp)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        origin = self.headers.get("Origin")
        if origin and self._validate_origin():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")

    # ---------------- REST Handlers ----------------

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        service = self.server.control_service
        target_root = self.server.target_root

        try:
            if path in ("/api/v1/health", "/api/v1/doctor"):
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
        except KeyError as err:
            self._send_error_response(ControlApiErrorCode.NOT_FOUND, str(err), 404)
        except Exception as err:
            self._send_error_response(ControlApiErrorCode.INTERNAL_ERROR, str(err), 500)

    def _handle_api_post(self, path: str, body: dict[str, Any]) -> None:
        service = self.server.control_service
        target_root = self.server.target_root

        try:
            if path.startswith("/api/v1/runs/") and path.endswith("/approve"):
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
        except KeyError as err:
            self._send_error_response(ControlApiErrorCode.NOT_FOUND, str(err), 404)
        except Exception as err:
            self._send_error_response(ControlApiErrorCode.INTERNAL_ERROR, str(err), 500)

    # ---------------- WebSocket & SSE Handlers ----------------

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
        client_channel = _WebSocketClientChannel(self.connection)
        self.server.broadcaster.register_client(client_channel)

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_str)
        self.end_headers()

        # Dispatch recent events for catch-up
        for ev in self.server.broadcaster.get_recent_events():
            client_channel.send_event(ev)

        # Keep connection open reading incoming ping/pong/close frames
        try:
            while not client_channel.closed:
                data = self.connection.recv(1024)
                if not data:
                    break
                # Opcode 8 is close frame
                if (data[0] & 0x0F) == 0x08:
                    break
        except OSError:
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
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def _send_json_response(self, data: Any, status_code: int = 200) -> None:
        envelope = ControlApiResponse(status="ok", data=data)
        body = envelope.model_dump_json().encode("utf-8")
        self.send_response(status_code)
        self._send_security_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
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
    ) -> None:
        self.control_service = control_service
        self.target_root = target_root
        self.static_dir = static_dir or (Path(__file__).parents[2] / "ui" / "static")
        self.broadcaster = broadcaster or InMemoryEventBroadcaster()
        self.host: str = "127.0.0.1"
        self.port: int = 8080
        self.session_token: str = ""
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
        self._httpd.target_root = self.target_root  # type: ignore[attr-defined]
        self._httpd.static_dir = self.static_dir  # type: ignore[attr-defined]
        self._httpd.broadcaster = self.broadcaster  # type: ignore[attr-defined]
        self._httpd.session_token = self.session_token  # type: ignore[attr-defined]
        self._httpd.port = self.port  # type: ignore[attr-defined]

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
