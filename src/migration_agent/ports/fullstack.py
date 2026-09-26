"""Ports for full-stack multi-layer discovery and strict read-only database schema inspection."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from migration_agent.domain import (
    CrossDomainEdge,
    CrossDomainNode,
    MigrationDomain,
    RepositorySnapshot,
)


@runtime_checkable
class DomainDiscoveryAdapterPort(Protocol):
    """Protocol implemented by domain-specific discovery adapters."""

    @property
    def domain(self) -> MigrationDomain:
        """The architectural migration domain owned by this adapter."""

    @property
    def adapter_id(self) -> str:
        """Stable unique identifier of this adapter."""

    def discover_nodes(self, snapshot: RepositorySnapshot) -> tuple[CrossDomainNode, ...]:
        """Detect and extract domain nodes from the inspected repository snapshot."""

    def discover_edges(
        self, snapshot: RepositorySnapshot, nodes: tuple[CrossDomainNode, ...]
    ) -> tuple[CrossDomainEdge, ...]:
        """Detect and extract internal or outgoing dependencies from discovered nodes."""


@runtime_checkable
class DatabaseInspectorPort(Protocol):
    """Protocol for strict read-only database schema inspection (zero mutations)."""

    def inspect_schema_file(self, file_path: str, content: str) -> tuple[CrossDomainNode, ...]:
        """Parse DDL/migration file text and extract database schema nodes."""

    def inspect_sqlite_database(self, db_path: Path) -> tuple[CrossDomainNode, ...]:
        """Inspect a local SQLite database file strictly in read-only mode."""
