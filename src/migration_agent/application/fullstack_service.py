"""Application service for multi-layer full-stack repository discovery
and cross-domain dependency graph creation.
"""

from collections import Counter
from pathlib import Path

from migration_agent.domain import (
    CrossDomainDependencyGraph,
    CrossDomainEdge,
    CrossDomainNode,
    DependencyRelation,
    FullStackInventory,
    ImpactReport,
    MigrationDomain,
)
from migration_agent.ports import FilesystemInspectorPort, InspectionPolicy
from migration_agent.ports.fullstack import DomainDiscoveryAdapterPort


class CrossDomainLinker:
    """Deterministically synthesizes cross-domain edges connecting UI -> API -> Service -> DB."""

    def link_domains(
        self,
        nodes: tuple[CrossDomainNode, ...],
        intra_edges: tuple[CrossDomainEdge, ...] = (),
    ) -> tuple[CrossDomainEdge, ...]:
        edges: list[CrossDomainEdge] = list(intra_edges)

        node_map = {n.node_id: n for n in nodes}
        frontend_nodes = [n for n in nodes if n.domain == MigrationDomain.FRONTEND]
        api_nodes = [n for n in nodes if n.domain == MigrationDomain.BACKEND_API]
        infra_nodes = [n for n in nodes if n.domain == MigrationDomain.INFRASTRUCTURE]

        # 1. Connect Frontend (UI) -> Backend API (INVOKES_API)
        for fe in frontend_nodes:
            api_calls = fe.metadata.get("api_calls", [])
            for call_path in api_calls:
                clean_call_path = call_path.rstrip("/")
                for api in api_nodes:
                    route_path = api.metadata.get("route_path", "").rstrip("/")
                    if clean_call_path == route_path or clean_call_path.startswith(route_path):
                        edges.append(
                            CrossDomainEdge(
                                source_node_id=fe.node_id,
                                target_node_id=api.node_id,
                                relation=DependencyRelation.INVOKES_API,
                                description=f"Frontend '{fe.name}' invokes endpoint '{api.name}'",
                                metadata={"call_path": call_path},
                            )
                        )

        # 2. Connect Backend API -> Database Schema (QUERIES_DB)
        for api in api_nodes:
            tables_accessed = api.metadata.get("tables_accessed", [])
            for tbl in tables_accessed:
                clean_tbl = tbl.lower()
                target_node_id = f"db:{clean_tbl}"
                if target_node_id in node_map:
                    edges.append(
                        CrossDomainEdge(
                            source_node_id=api.node_id,
                            target_node_id=target_node_id,
                            relation=DependencyRelation.QUERIES_DB,
                            description=f"API '{api.name}' queries table '{clean_tbl}'",
                            metadata={"table": clean_tbl},
                        )
                    )

        # 3. Connect Infrastructure -> Services (CONFIGURES)
        for infra in infra_nodes:
            service_name = infra.metadata.get("service_name", "").lower()
            if not service_name:
                continue

            for target in nodes:
                if target.domain == MigrationDomain.INFRASTRUCTURE:
                    continue
                target_name_lower = target.name.lower()
                matches = (
                    (
                        service_name in ("web", "frontend", "ui")
                        and target.domain == MigrationDomain.FRONTEND
                    )
                    or (
                        service_name in ("api", "server", "backend")
                        and target.domain == MigrationDomain.BACKEND_API
                    )
                    or (
                        service_name in ("db", "database", "postgres", "mysql")
                        and target.domain == MigrationDomain.DATABASE_SCHEMA
                    )
                    or service_name in target_name_lower
                )
                if matches:
                    edges.append(
                        CrossDomainEdge(
                            source_node_id=infra.node_id,
                            target_node_id=target.node_id,
                            relation=DependencyRelation.CONFIGURES,
                            description=f"Infrastructure '{infra.name}' configures '{target.name}'",
                        )
                    )

        # Deduplicate edges deterministically
        edge_set: set[tuple[str, str, str]] = set()
        unique_edges: list[CrossDomainEdge] = []
        for e in sorted(
            edges, key=lambda x: (x.source_node_id, x.target_node_id, x.relation.value)
        ):
            key = (e.source_node_id, e.target_node_id, e.relation.value)
            if key not in edge_set:
                edge_set.add(key)
                unique_edges.append(e)

        return tuple(unique_edges)


class FullStackDiscoveryService:
    """Coordinates deterministic full-stack discovery across frontend, backend,
    database, and infrastructure.
    """

    def __init__(
        self,
        filesystem: FilesystemInspectorPort,
        adapters: tuple[DomainDiscoveryAdapterPort, ...],
        linker: CrossDomainLinker | None = None,
    ) -> None:
        self._filesystem = filesystem
        self._adapters = adapters
        self._linker = linker if linker is not None else CrossDomainLinker()

    def discover(
        self,
        root: Path,
        *,
        policy: InspectionPolicy | None = None,
    ) -> FullStackInventory:
        """Inspect repository and construct a multi-layer cross-domain dependency graph."""
        snapshot = self._filesystem.inspect(root, policy or InspectionPolicy())

        all_nodes_list: list[CrossDomainNode] = []
        all_intra_edges_list: list[CrossDomainEdge] = []

        for adapter in self._adapters:
            nodes = adapter.discover_nodes(snapshot)
            edges = adapter.discover_edges(snapshot, nodes)
            all_nodes_list.extend(nodes)
            all_intra_edges_list.extend(edges)

        unique_nodes = {node.node_id: node for node in all_nodes_list}
        sorted_nodes = tuple(
            sorted(unique_nodes.values(), key=lambda n: (n.domain.value, n.node_id))
        )

        all_edges = self._linker.link_domains(sorted_nodes, tuple(all_intra_edges_list))

        graph = CrossDomainDependencyGraph(
            nodes=sorted_nodes,
            edges=all_edges,
        )

        detected_domains = tuple(
            domain for domain in MigrationDomain if any(n.domain == domain for n in sorted_nodes)
        )

        domain_counts = Counter(node.domain.value for node in sorted_nodes)
        summary = {domain.value: domain_counts[domain.value] for domain in MigrationDomain}
        summary["total_nodes"] = len(sorted_nodes)
        summary["total_edges"] = len(all_edges)

        return FullStackInventory(
            repository=snapshot.repository,
            domains_detected=detected_domains,
            graph=graph,
            summary=summary,
        )

    def analyze_impact(
        self,
        root: Path,
        node_id: str,
        *,
        policy: InspectionPolicy | None = None,
    ) -> ImpactReport:
        """Run full-stack discovery and compute downstream and upstream ripples
        for a specific node.
        """
        inventory = self.discover(root, policy=policy)
        return inventory.graph.compute_impact(node_id)
