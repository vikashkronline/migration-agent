"""Unit tests for FullStackDiscoveryService and FullStackReportWriter
against the synthetic fixture.
"""

from pathlib import Path

import pytest

from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.fullstack_adapters import create_default_domain_adapters
from migration_agent.adapters.fullstack_reporting import FullStackReportWriter
from migration_agent.application.fullstack_service import FullStackDiscoveryService
from migration_agent.domain import DependencyRelation, MigrationDomain

FIXTURE_PATH = Path("tests/fixtures/fullstack-ecommerce-mini")
FRONTEND_NODE_ID = "frontend:file:frontend/src/user-card.component.ts"


def test_fullstack_discovery_on_synthetic_fixture() -> None:
    service = FullStackDiscoveryService(
        filesystem=SafeFilesystemInspector(),
        adapters=create_default_domain_adapters(),
    )
    inventory = service.discover(FIXTURE_PATH)

    # 1. Check all 4 domains detected
    assert len(inventory.domains_detected) == 4
    for domain in MigrationDomain:
        assert domain in inventory.domains_detected

    # 2. Check nodes in each layer
    node_ids = {n.node_id for n in inventory.graph.nodes}

    # Frontend
    assert FRONTEND_NODE_ID in node_ids
    # Backend
    assert "api:GET:/api/users" in node_ids
    assert "api:POST:/api/orders" in node_ids
    # Database
    assert "db:users" in node_ids
    assert "db:orders" in node_ids
    # Infrastructure
    assert "infra:compose:web" in node_ids
    assert "infra:compose:api" in node_ids
    assert "infra:compose:db" in node_ids
    assert "infra:dockerfile:frontend" in node_ids
    assert "infra:dockerfile:backend" in node_ids

    # 3. Check cross-domain dependency chain: UI -> API -> DB
    edges = inventory.graph.edges
    edge_triples = {(e.source_node_id, e.relation, e.target_node_id) for e in edges}

    # Frontend calls Backend API
    assert (
        FRONTEND_NODE_ID,
        DependencyRelation.INVOKES_API,
        "api:GET:/api/users",
    ) in edge_triples

    # Backend API queries DB
    assert (
        "api:GET:/api/users",
        DependencyRelation.QUERIES_DB,
        "db:users",
    ) in edge_triples

    assert (
        "api:POST:/api/orders",
        DependencyRelation.QUERIES_DB,
        "db:orders",
    ) in edge_triples

    # Intra-DB foreign key
    assert (
        "db:orders",
        DependencyRelation.DEPENDS_ON,
        "db:users",
    ) in edge_triples

    # Compose depends_on
    assert (
        "infra:compose:web",
        DependencyRelation.DEPENDS_ON,
        "infra:compose:api",
    ) in edge_triples
    assert (
        "infra:compose:api",
        DependencyRelation.DEPENDS_ON,
        "infra:compose:db",
    ) in edge_triples


def test_fullstack_impact_analysis_on_fixture() -> None:
    service = FullStackDiscoveryService(
        filesystem=SafeFilesystemInspector(),
        adapters=create_default_domain_adapters(),
    )

    # Impact of modifying db:users table:
    # Upstream/callers affected must include api:GET:/api/users,
    # frontend:user-card.component, and db:orders
    impact = service.analyze_impact(FIXTURE_PATH, "db:users")

    assert impact.target_node_id == "db:users"
    assert impact.target_domain == MigrationDomain.DATABASE_SCHEMA

    assert "api:GET:/api/users" in impact.dependents
    assert FRONTEND_NODE_ID in impact.dependents
    assert "db:orders" in impact.dependents

    assert MigrationDomain.FRONTEND in impact.impacted_domains
    assert MigrationDomain.BACKEND_API in impact.impacted_domains
    assert MigrationDomain.DATABASE_SCHEMA in impact.impacted_domains


def test_discovery_refuses_conflicting_adapter_node_ids(tmp_path: Path) -> None:
    from unittest.mock import Mock

    from migration_agent.domain import CrossDomainNode

    node = CrossDomainNode(
        node_id="duplicate",
        domain=MigrationDomain.FRONTEND,
        name="first",
        entity_type="component",
        path="app/first.js",
    )
    adapter = Mock()
    adapter.discover_nodes.return_value = (
        node,
        node.model_copy(update={"path": "app/second.js"}),
    )
    adapter.discover_edges.return_value = ()
    service = FullStackDiscoveryService(SafeFilesystemInspector(), (adapter,))
    with pytest.raises(ValueError, match="DISCOVERY_ID_CONFLICT"):
        service.discover(tmp_path)


def test_fullstack_reporting_writer(tmp_path: Path) -> None:
    service = FullStackDiscoveryService(
        filesystem=SafeFilesystemInspector(),
        adapters=create_default_domain_adapters(),
    )
    inventory = service.discover(FIXTURE_PATH)

    writer = FullStackReportWriter()
    out_dir = tmp_path / "reports"
    json_path, mermaid_path, md_path = writer.write(inventory, out_dir)

    assert json_path.is_file()
    assert mermaid_path.is_file()
    assert md_path.is_file()

    # Verify JSON content
    json_text = json_path.read_text(encoding="utf-8")
    assert '"schema_version": 1' in json_text
    assert '"db:users"' in json_text

    # Verify Mermaid content
    mermaid_text = mermaid_path.read_text(encoding="utf-8")
    assert "flowchart TD" in mermaid_text
    assert "subgraph_frontend" in mermaid_text
    assert "subgraph_backend_api" in mermaid_text
    assert "subgraph_database_schema" in mermaid_text

    # Verify Markdown content
    md_text = md_path.read_text(encoding="utf-8")
    assert "# Full-Stack Migration Inventory" in md_text
    assert "```mermaid" in md_text


def test_fullstack_reporting_overlap_rejection(tmp_path: Path) -> None:
    service = FullStackDiscoveryService(
        filesystem=SafeFilesystemInspector(),
        adapters=create_default_domain_adapters(),
    )
    inventory = service.discover(FIXTURE_PATH)

    writer = FullStackReportWriter()
    # Attempting to write into the source repository itself must raise ValueError
    with pytest.raises(ValueError, match="overlap"):
        writer.write(inventory, FIXTURE_PATH)
