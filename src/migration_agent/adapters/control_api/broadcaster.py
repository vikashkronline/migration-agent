"""In-memory event broadcaster for real-time WebSocket and SSE event streaming."""

import collections
import threading
from typing import Any

from migration_agent.domain import WebSocketEventMessage
from migration_agent.ports import EventBroadcasterPort


class InMemoryEventBroadcaster(EventBroadcasterPort):
    """Thread-safe event broadcaster maintaining recent events and active client channels."""

    def __init__(self, history_limit: int = 100) -> None:
        self._lock = threading.Lock()
        self._clients: set[Any] = set()
        self._recent_events: collections.deque[WebSocketEventMessage] = collections.deque(
            maxlen=history_limit
        )

    def broadcast(self, event: WebSocketEventMessage) -> None:
        """Deliver an event to all registered client channels."""
        with self._lock:
            self._recent_events.append(event)
            dead_clients: list[Any] = []
            for client in self._clients:
                try:
                    if hasattr(client, "send_event"):
                        client.send_event(event)
                    elif hasattr(client, "put_nowait"):
                        client.put_nowait(event)
                except Exception:
                    dead_clients.append(client)
            for dead in dead_clients:
                self._clients.discard(dead)

    def register_client(self, client: Any) -> None:
        """Register an active client connection."""
        with self._lock:
            self._clients.add(client)

    def unregister_client(self, client: Any) -> None:
        """Remove a disconnected client connection."""
        with self._lock:
            self._clients.discard(client)

    def client_count(self) -> int:
        """Return the number of actively registered clients."""
        with self._lock:
            return len(self._clients)

    def get_recent_events(self) -> list[WebSocketEventMessage]:
        """Return a copy of recent events for initial client state catch-up."""
        with self._lock:
            return list(self._recent_events)
