"""Ports for Control API server and real-time event broadcasting."""

from typing import Any, Protocol

from migration_agent.domain import WebSocketEventMessage


class ControlApiServerPort(Protocol):
    """Port interface for hosting the loopback Control API server."""

    def start(self, host: str, port: int, session_token: str) -> None:
        """Start the loopback server binding strictly to host and port."""

    def stop(self) -> None:
        """Stop the loopback server and release all resources."""

    def get_url(self) -> str:
        """Return the loopback base URL (e.g. http://127.0.0.1:8080)."""


class EventBroadcasterPort(Protocol):
    """Port interface for publishing real-time events to connected clients."""

    def broadcast(self, event: WebSocketEventMessage) -> None:
        """Broadcast a structured event message to all connected clients."""

    def register_client(self, client: Any) -> None:
        """Register a connected WebSocket or streaming client."""

    def unregister_client(self, client: Any) -> None:
        """Unregister a disconnected client."""

    def client_count(self) -> int:
        """Return the number of actively connected clients."""
