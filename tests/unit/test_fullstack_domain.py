"""Unit tests for full-stack migration domain models and dependency graph operations."""

import pytest
from pydantic import ValidationError

from migration_agent.domain import (
    CrossDomainDependencyGraph,
    CrossDomainEdge,
    CrossDomainNode,
    DependencyRelation,
    FullStackInventory,
    MigrationDomain,
    RepositoryDescriptor,
)


def _make_node(
    node_id: str, domain: MigrationDomain, name: str, entity_type: str = "component"
) -> CrossDomainNode:
    return CrossDomainNode(
        node_id=node_id,
        domain=domain,
        name=name,
        entity_type=entity_type,
        path=f"src/{name}.ts",
    )


def test_domain_enum_values() -> None:
    assert MigrationDomain.FRONTEND.value == "frontend"
    assert MigrationDomain.BACKEND_API.value == "backend_api"
    assert MigrationDomain.DATABASE_SCHEMA.value == "database_schema"
    assert MigrationDomain.INFRASTRUCTURE.value == "infrastructure"


def test_cross_domain_node_immutability() -> None:
    node = _make_node("frontend:user-card", MigrationDomain.FRONTEND, "user-card")
    assert node.node_id == "frontend:user-card"
    assert node.domain == MigrationDomain.FRONTEND

    with pytest.raises(ValidationError):
        node.name = "new-name"  # type: ignore[misc]


def test_cross_domain_edge_relations() -> None:
    edge = CrossDomainEdge(
        source_node_id="frontend:user-card",
        target_node_id="api:GET:/api/users",
        relation=DependencyRelation.INVOKES_API,
        description="Calls user endpoint",
    )
    assert edge.relation == DependencyRelation.INVOKES_API
    assert edge.source_node_id == "frontend:user-card"
    assert edge.target_node_id == "api:GET:/api/users"


def test_graph_queries() -> None:
    n1 = _make_node("frontend:user-card", MigrationDomain.FRONTEND, "user-card")
    n2 = _make_node("api:GET:/api/users", MigrationDomain.BACKEND_API, "GET /api/users", "endpoint")
    n3 = _make_node("db:users", MigrationDomain.DATABASE_SCHEMA, "users", "table")

    e1 = CrossDomainEdge(
        source_node_id=n1.node_id,
        target_node_id=n2.node_id,
        relation=DependencyRelation.INVOKES_API,
    )
    e2 = CrossDomainEdge(
        source_node_id=n2.node_id,
        target_node_id=n3.node_id,
        relation=DependencyRelation.QUERIES_DB,
    )

    graph = CrossDomainDependencyGraph(nodes=(n1, n2, n3), edges=(e1, e2))

    assert graph.get_node("frontend:user-card") == n1
    assert graph.get_node("non-existent") is None

    assert graph.get_nodes_by_domain(MigrationDomain.FRONTEND) == (n1,)
    assert graph.get_nodes_by_domain(MigrationDomain.BACKEND_API) == (n2,)
    assert graph.get_nodes_by_domain(MigrationDomain.DATABASE_SCHEMA) == (n3,)
    assert graph.get_nodes_by_domain(MigrationDomain.INFRASTRUCTURE) == ()

    assert graph.get_outgoing_edges(n1.node_id) == (e1,)
    assert graph.get_incoming_edges(n1.node_id) == ()
    assert graph.get_outgoing_edges(n2.node_id) == (e2,)
    assert graph.get_incoming_edges(n2.node_id) == (e1,)


def test_graph_cycle_detection_and_topological_sort() -> None:
    n1 = _make_node("frontend:user-card", MigrationDomain.FRONTEND, "user-card")
    n2 = _make_node("api:GET:/api/users", MigrationDomain.BACKEND_API, "GET /api/users")
    n3 = _make_node("db:users", MigrationDomain.DATABASE_SCHEMA, "users")

    # Acyclic graph: UI -> API -> DB
    # in dependency terms: DB is required by API, API is required by UI
    e1 = CrossDomainEdge(
        source_node_id=n1.node_id,
        target_node_id=n2.node_id,
        relation=DependencyRelation.INVOKES_API,
    )
    e2 = CrossDomainEdge(
        source_node_id=n2.node_id,
        target_node_id=n3.node_id,
        relation=DependencyRelation.QUERIES_DB,
    )
    acyclic_graph = CrossDomainDependencyGraph(nodes=(n1, n2, n3), edges=(e1, e2))

    assert acyclic_graph.detect_cycles() == []

    # Topological sort puts dependencies before dependents
    sorted_nodes = acyclic_graph.topological_sort()
    sorted_ids = [n.node_id for n in sorted_nodes]
    # db:users must precede api:GET:/api/users, which must precede frontend:user-card
    assert sorted_ids.index("db:users") < sorted_ids.index("api:GET:/api/users")
    assert sorted_ids.index("api:GET:/api/users") < sorted_ids.index("frontend:user-card")

    # Cyclic graph: n1 -> n2 -> n3 -> n1
    e3 = CrossDomainEdge(
        source_node_id=n3.node_id,
        target_node_id=n1.node_id,
        relation=DependencyRelation.DEPENDS_ON,
    )
    cyclic_graph = CrossDomainDependencyGraph(nodes=(n1, n2, n3), edges=(e1, e2, e3))
    cycles = cyclic_graph.detect_cycles()
    assert len(cycles) > 0

    with pytest.raises(ValueError, match="cycles"):
        cyclic_graph.topological_sort()


def test_impact_analysis() -> None:
    # Full-stack chain: UI -> API -> DB
    n_ui = _make_node("frontend:user-card", MigrationDomain.FRONTEND, "user-card")
    n_api = _make_node("api:GET:/api/users", MigrationDomain.BACKEND_API, "GET /api/users")
    n_db = _make_node("db:users", MigrationDomain.DATABASE_SCHEMA, "users")
    n_orders = _make_node("db:orders", MigrationDomain.DATABASE_SCHEMA, "orders")

    # Edges:
    # UI -> API
    # API -> DB:users
    # DB:orders -> DB:users (foreign key dependency)
    edges = (
        CrossDomainEdge(
            source_node_id=n_ui.node_id,
            target_node_id=n_api.node_id,
            relation=DependencyRelation.INVOKES_API,
        ),
        CrossDomainEdge(
            source_node_id=n_api.node_id,
            target_node_id=n_db.node_id,
            relation=DependencyRelation.QUERIES_DB,
        ),
        CrossDomainEdge(
            source_node_id=n_orders.node_id,
            target_node_id=n_db.node_id,
            relation=DependencyRelation.DEPENDS_ON,
        ),
    )

    graph = CrossDomainDependencyGraph(nodes=(n_ui, n_api, n_db, n_orders), edges=edges)

    # Impact of changing db:users:
    # Dependents are api:GET:/api/users, frontend:user-card (transitively!), and db:orders
    impact = graph.compute_impact("db:users")
    assert impact.target_node_id == "db:users"
    assert impact.target_domain == MigrationDomain.DATABASE_SCHEMA
    assert set(impact.dependents) == {
        "api:GET:/api/users",
        "frontend:user-card",
        "db:orders",
    }
    assert MigrationDomain.FRONTEND in impact.impacted_domains
    assert MigrationDomain.BACKEND_API in impact.impacted_domains
    assert MigrationDomain.DATABASE_SCHEMA in impact.impacted_domains
    assert "impacts 3 dependent component(s)" in impact.impact_summary

    # Impact of changing frontend:user-card (leaf node with no dependents)
    ui_impact = graph.compute_impact("frontend:user-card")
    assert ui_impact.dependents == ()
    assert set(ui_impact.dependencies) == {"api:GET:/api/users", "db:users"}


def test_mermaid_rendering() -> None:
    n1 = _make_node("frontend:user-card", MigrationDomain.FRONTEND, "user-card", "component")
    n2 = _make_node("api:GET:/api/users", MigrationDomain.BACKEND_API, "GET /api/users", "endpoint")
    n3 = _make_node("db:users", MigrationDomain.DATABASE_SCHEMA, "users", "table")

    e1 = CrossDomainEdge(
        source_node_id=n1.node_id,
        target_node_id=n2.node_id,
        relation=DependencyRelation.INVOKES_API,
    )
    e2 = CrossDomainEdge(
        source_node_id=n2.node_id,
        target_node_id=n3.node_id,
        relation=DependencyRelation.QUERIES_DB,
    )

    graph = CrossDomainDependencyGraph(nodes=(n1, n2, n3), edges=(e1, e2))
    mermaid = graph.to_mermaid(direction="TD")

    assert "flowchart TD" in mermaid
    assert 'subgraph subgraph_frontend ["Frontend (UI)"]' in mermaid
    assert 'subgraph subgraph_backend_api ["Backend API & Services"]' in mermaid
    assert 'subgraph subgraph_database_schema ["Database Schema"]' in mermaid
    assert '-->|"invokes api"|' in mermaid
    assert '-->|"queries db"|' in mermaid


def test_fullstack_inventory_serialization() -> None:
    repo = RepositoryDescriptor(name="test-repo", root=pytest.importorskip("pathlib").Path("."))
    n = _make_node("frontend:user-card", MigrationDomain.FRONTEND, "user-card")
    graph = CrossDomainDependencyGraph(nodes=(n,), edges=())

    inv = FullStackInventory(
        repository=repo,
        domains_detected=(MigrationDomain.FRONTEND,),
        graph=graph,
        summary={"frontend": 1, "total_nodes": 1, "total_edges": 0},
    )

    dumped = inv.model_dump(mode="json")
    assert dumped["schema_version"] == 1
    assert dumped["domains_detected"] == ["frontend"]
    assert dumped["summary"]["total_nodes"] == 1
