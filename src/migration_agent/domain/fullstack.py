"""Typed domain contracts for multi-layer full-stack migration architectures
and cross-domain dependency graphs.
"""

import hashlib
from collections import defaultdict, deque
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.inventory import FrameworkEvidence, RepositoryDescriptor


class MigrationDomain(StrEnum):
    """The four primary architectural layers in full-stack migration."""

    FRONTEND = "frontend"
    BACKEND_API = "backend_api"
    DATABASE_SCHEMA = "database_schema"
    INFRASTRUCTURE = "infrastructure"


class DependencyRelation(StrEnum):
    """Semantic relationship types between cross-domain components."""

    INVOKES_API = "invokes_api"  # e.g., UI Component -> HTTP API Endpoint
    CALLS_SERVICE = "calls_service"  # e.g., API Controller -> Backend Service
    QUERIES_DB = "queries_db"  # e.g., Service / Endpoint -> Database Table
    DEFINES_SCHEMA = "defines_schema"  # e.g., DDL / Migration -> Database Table
    CONFIGURES = "configures"  # e.g., Docker / Compose -> Service / Component
    DEPENDS_ON = "depends_on"  # Generic dependency relation


class CrossDomainNode(BaseModel):
    """An immutable, typed entity residing in one of the migration domains."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(min_length=1)
    domain: MigrationDomain
    name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)  # e.g. "component", "endpoint", "table", "container"
    path: str = Field(min_length=1)  # Normalized POSIX repository path
    line_number: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[FrameworkEvidence, ...] = Field(default_factory=tuple)


class CrossDomainEdge(BaseModel):
    """A directed dependency or invocation relationship from source to target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    relation: DependencyRelation
    description: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImpactReport(BaseModel):
    """Detailed ripple/impact analysis when a particular node is altered or migrated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_node_id: str
    target_domain: MigrationDomain
    dependents: tuple[str, ...]  # Nodes that depend on target (impacted if target changes)
    dependencies: tuple[str, ...]  # Nodes target depends upon
    impacted_domains: tuple[MigrationDomain, ...]
    impact_summary: str


class CrossDomainDependencyGraph(BaseModel):
    """Immutable, typed directed graph capturing cross-layer dependencies
    (UI -> API -> Service -> DB).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: tuple[CrossDomainNode, ...] = Field(default_factory=tuple)
    edges: tuple[CrossDomainEdge, ...] = Field(default_factory=tuple)

    def get_node(self, node_id: str) -> CrossDomainNode | None:
        """Find a node by its unique node_id."""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_nodes_by_domain(self, domain: MigrationDomain) -> tuple[CrossDomainNode, ...]:
        """Return all nodes belonging to the specified domain."""
        return tuple(node for node in self.nodes if node.domain == domain)

    def get_outgoing_edges(self, node_id: str) -> tuple[CrossDomainEdge, ...]:
        """Return all edges originating from node_id (dependencies of node_id)."""
        return tuple(edge for edge in self.edges if edge.source_node_id == node_id)

    def get_incoming_edges(self, node_id: str) -> tuple[CrossDomainEdge, ...]:
        """Return all edges terminating at node_id (nodes that depend on node_id)."""
        return tuple(edge for edge in self.edges if edge.target_node_id == node_id)

    def detect_cycles(self) -> list[list[str]]:
        """Detect any directed cycles in the graph using DFS."""
        adj: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            adj[edge.source_node_id].append(edge.target_node_id)

        visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        cycles: list[list[str]] = []

        def dfs(curr: str, path: list[str]) -> None:
            visited[curr] = 1
            path.append(curr)
            for neighbor in sorted(adj.get(curr, [])):
                state = visited.get(neighbor, 0)
                if state == 1:
                    # Cycle found
                    cycle_start = path.index(neighbor)
                    cycles.append([*path[cycle_start:], neighbor])
                elif state == 0:
                    dfs(neighbor, path)
            path.pop()
            visited[curr] = 2

        all_node_ids = sorted(node.node_id for node in self.nodes)
        for nid in all_node_ids:
            if visited.get(nid, 0) == 0:
                dfs(nid, [])

        return cycles

    def topological_sort(self) -> tuple[CrossDomainNode, ...]:
        """Topological sort of nodes (dependencies before dependents).

        Raises ValueError if the graph contains directed cycles.
        """
        node_map = {node.node_id: node for node in self.nodes}
        in_degree: dict[str, int] = {node.node_id: 0 for node in self.nodes}
        adj: dict[str, list[str]] = defaultdict(list)

        for edge in self.edges:
            if edge.source_node_id in node_map and edge.target_node_id in node_map:
                adj[edge.target_node_id].append(edge.source_node_id)
                in_degree[edge.source_node_id] += 1

        ready = sorted([nid for nid, deg in in_degree.items() if deg == 0])
        ordered: list[CrossDomainNode] = []

        while ready:
            curr = ready.pop(0)
            ordered.append(node_map[curr])
            for dependent in sorted(adj.get(curr, [])):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort()

        if len(ordered) < len(self.nodes):
            unresolved = sorted([nid for nid, deg in in_degree.items() if deg > 0])
            raise ValueError(f"Graph contains dependency cycles involving: {', '.join(unresolved)}")

        return tuple(ordered)

    def compute_impact(self, node_id: str) -> ImpactReport:
        """Analyze impact: which callers/dependents are affected if node_id is changed."""
        target = self.get_node(node_id)
        if target is None:
            raise ValueError(f"Node '{node_id}' not found in dependency graph.")

        # Breadth-first search along incoming edges (dependents/callers)
        incoming_map: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            incoming_map[edge.target_node_id].append(edge.source_node_id)

        visited_dependents: set[str] = set()
        queue: deque[str] = deque([node_id])
        while queue:
            curr = queue.popleft()
            for parent in incoming_map.get(curr, []):
                if parent not in visited_dependents and parent != node_id:
                    visited_dependents.add(parent)
                    queue.append(parent)

        # Breadth-first search along outgoing edges (direct/transitive dependencies)
        outgoing_map: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            outgoing_map[edge.source_node_id].append(edge.target_node_id)

        visited_dependencies: set[str] = set()
        queue = deque([node_id])
        while queue:
            curr = queue.popleft()
            for child in outgoing_map.get(curr, []):
                if child not in visited_dependencies and child != node_id:
                    visited_dependencies.add(child)
                    queue.append(child)

        sorted_dependents = tuple(sorted(visited_dependents))
        sorted_dependencies = tuple(sorted(visited_dependencies))

        impacted_domains_set: set[MigrationDomain] = {target.domain}
        for dep_id in sorted_dependents:
            dep_node = self.get_node(dep_id)
            if dep_node:
                impacted_domains_set.add(dep_node.domain)

        sorted_impacted_domains = tuple(
            domain for domain in MigrationDomain if domain in impacted_domains_set
        )

        summary = (
            f"Altering '{node_id}' ({target.domain.value}) impacts {len(sorted_dependents)} "
            f"dependent component(s) across {len(sorted_impacted_domains)} domain(s): "
            f"{', '.join(d.value for d in sorted_impacted_domains)}."
        )

        return ImpactReport(
            target_node_id=node_id,
            target_domain=target.domain,
            dependents=sorted_dependents,
            dependencies=sorted_dependencies,
            impacted_domains=sorted_impacted_domains,
            impact_summary=summary,
        )

    def to_mermaid(self, direction: str = "TD") -> str:
        """Render a deterministic, secure Mermaid flowchart organized by domain subgraphs."""
        lines = [f"flowchart {direction}"]

        # Domain title mapping
        domain_titles = {
            MigrationDomain.FRONTEND: "Frontend (UI)",
            MigrationDomain.BACKEND_API: "Backend API & Services",
            MigrationDomain.DATABASE_SCHEMA: "Database Schema",
            MigrationDomain.INFRASTRUCTURE: "Infrastructure & Deployment",
        }

        # Subgraphs per domain
        for domain in (
            MigrationDomain.FRONTEND,
            MigrationDomain.BACKEND_API,
            MigrationDomain.DATABASE_SCHEMA,
            MigrationDomain.INFRASTRUCTURE,
        ):
            domain_nodes = sorted(
                [node for node in self.nodes if node.domain == domain],
                key=lambda n: n.node_id,
            )
            if not domain_nodes:
                continue

            subgraph_id = f"subgraph_{domain.value}"
            title = domain_titles[domain]
            lines.append(f'    subgraph {subgraph_id} ["{title}"]')
            for node in domain_nodes:
                safe_id = _sanitize_mermaid_id(node.node_id)
                label = f"{node.name} ({node.entity_type})"
                lines.append(f'        {safe_id}["{label}"]')
            lines.append("    end")

        # Directed Edges
        sorted_edges = sorted(
            self.edges,
            key=lambda e: (e.source_node_id, e.target_node_id, e.relation.value),
        )
        for edge in sorted_edges:
            src_id = _sanitize_mermaid_id(edge.source_node_id)
            tgt_id = _sanitize_mermaid_id(edge.target_node_id)
            relation_label = edge.relation.value.replace("_", " ")
            lines.append(f'    {src_id} -->|"{relation_label}"| {tgt_id}')

        return "\n".join(lines)


def _sanitize_mermaid_id(raw_id: str) -> str:
    """Sanitize raw node ID into a safe Mermaid node identifier."""
    return "n_" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


class FullStackInventory(BaseModel):
    """Comprehensive multi-layer repository inventory with cross-domain dependency graph."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    repository: RepositoryDescriptor
    domains_detected: tuple[MigrationDomain, ...]
    graph: CrossDomainDependencyGraph
    summary: dict[str, int]
