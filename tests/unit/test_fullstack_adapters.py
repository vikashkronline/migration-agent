"""Unit tests for fullstack discovery adapters across Frontend, Backend,
Database, and Infrastructure.
"""

from pathlib import Path

from migration_agent.adapters.fullstack_adapters import (
    BackendApiAdapter,
    FrontendDomainAdapter,
    InfrastructureAdapter,
    SqlDatabaseAdapter,
)
from migration_agent.application import CrossDomainLinker
from migration_agent.domain import (
    CrossDomainNode,
    DependencyRelation,
    ExclusionSummary,
    FileCategory,
    InspectedTextFile,
    MigrationDomain,
    RepositoryDescriptor,
    RepositorySnapshot,
)


def _make_snapshot(files: list[InspectedTextFile]) -> RepositorySnapshot:
    return RepositorySnapshot(
        repository=RepositoryDescriptor(name="test-repo", root=Path(".")),
        files=tuple(files),
        exclusions=ExclusionSummary(),
    )


def test_frontend_domain_adapter() -> None:
    content = """
    import { Component, inject } from '@angular/core';
    import { HttpClient } from '@angular/common/http';

    @Component({
      selector: 'app-users',
      template: '<div>users</div>'
    })
    export class UsersComponent {
      private http = inject(HttpClient);
      load() {
        this.http.get('/api/users').subscribe();
      }
    }
    """
    file = InspectedTextFile(
        path="src/app/users.component.ts",
        category=FileCategory.SOURCE,
        size_bytes=len(content),
        sha256="a" * 64,
        content=content,
    )
    adapter = FrontendDomainAdapter()
    nodes = adapter.discover_nodes(_make_snapshot([file]))

    assert len(nodes) == 1
    node = nodes[0]
    assert node.domain == MigrationDomain.FRONTEND
    assert node.node_id == "frontend:users.component"
    assert node.metadata.get("api_calls") == ["/api/users"]


def test_backend_api_adapter_fastapi() -> None:
    content = """
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/api/users")
    def get_users():
        return db.query("SELECT * FROM users")

    @app.post("/api/items")
    async def create_item():
        return {"status": "created"}
    """
    file = InspectedTextFile(
        path="app/main.py",
        category=FileCategory.SOURCE,
        size_bytes=len(content),
        sha256="b" * 64,
        content=content,
    )
    adapter = BackendApiAdapter()
    nodes = adapter.discover_nodes(_make_snapshot([file]))

    assert len(nodes) == 2
    get_node = next(n for n in nodes if "GET" in n.node_id)
    assert get_node.node_id == "api:GET:/api/users"
    assert get_node.metadata.get("http_method") == "GET"
    assert get_node.metadata.get("route_path") == "/api/users"
    assert get_node.metadata.get("tables_accessed") == ["users"]


def test_backend_api_adapter_express() -> None:
    content = """
    const express = require('express');
    const app = express();

    app.get('/api/orders', async (req, res) => {
        const rows = await db.query('SELECT id, total FROM orders');
        res.json(rows);
    });
    """
    file = InspectedTextFile(
        path="server.js",
        category=FileCategory.SOURCE,
        size_bytes=len(content),
        sha256="c" * 64,
        content=content,
    )
    adapter = BackendApiAdapter()
    nodes = adapter.discover_nodes(_make_snapshot([file]))

    assert len(nodes) == 1
    node = nodes[0]
    assert node.node_id == "api:GET:/api/orders"
    assert node.metadata.get("http_method") == "GET"
    assert node.metadata.get("route_path") == "/api/orders"
    assert node.metadata.get("tables_accessed") == ["orders"]


def test_sql_database_adapter_ddl() -> None:
    sql = """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username VARCHAR(50) NOT NULL
    );

    CREATE TABLE orders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        amount DECIMAL(10, 2),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """
    file = InspectedTextFile(
        path="schema.sql",
        category=FileCategory.SOURCE,
        size_bytes=len(sql),
        sha256="d" * 64,
        content=sql,
    )
    adapter = SqlDatabaseAdapter()
    nodes = adapter.discover_nodes(_make_snapshot([file]))

    assert len(nodes) == 2
    table_names = {n.name for n in nodes}
    assert table_names == {"users", "orders"}

    orders_node = next(n for n in nodes if n.name == "orders")
    assert "user_id" in orders_node.metadata.get("columns", [])
    fks = orders_node.metadata.get("foreign_keys", [])
    assert len(fks) == 1
    assert fks[0]["target_table"] == "users"

    # Test intra-database foreign key edge discovery
    edges = adapter.discover_edges(_make_snapshot([file]), nodes)
    assert len(edges) == 1
    assert edges[0].source_node_id == "db:orders"
    assert edges[0].target_node_id == "db:users"
    assert edges[0].relation == DependencyRelation.DEPENDS_ON


def test_infrastructure_adapter() -> None:
    dockerfile_content = """
    FROM python:3.12-slim
    WORKDIR /app
    COPY . .
    EXPOSE 8000
    CMD ["uvicorn", "app.main:app"]
    """
    compose_content = """
    version: '3.8'
    services:
      web:
        build: .
        ports:
          - "80:80"
        depends_on:
          - api
      api:
        image: my-api:latest
        depends_on:
          - db
      db:
        image: postgres:15
    """
    f1 = InspectedTextFile(
        path="Dockerfile",
        category=FileCategory.BUILD_CONFIG,
        size_bytes=len(dockerfile_content),
        sha256="e" * 64,
        content=dockerfile_content,
    )
    f2 = InspectedTextFile(
        path="docker-compose.yml",
        category=FileCategory.BUILD_CONFIG,
        size_bytes=len(compose_content),
        sha256="f" * 64,
        content=compose_content,
    )

    adapter = InfrastructureAdapter()
    nodes = adapter.discover_nodes(_make_snapshot([f1, f2]))

    node_ids = {n.node_id for n in nodes}
    assert "infra:dockerfile:Dockerfile" in node_ids
    assert "infra:compose:web" in node_ids
    assert "infra:compose:api" in node_ids
    assert "infra:compose:db" in node_ids

    dockerfile_node = next(n for n in nodes if "dockerfile" in n.node_id)
    assert dockerfile_node.metadata.get("base_image") == "python:3.12-slim"
    assert dockerfile_node.metadata.get("exposed_ports") == [8000]

    # Test compose dependency edges
    edges = adapter.discover_edges(_make_snapshot([f1, f2]), nodes)
    edge_pairs = {(e.source_node_id, e.target_node_id) for e in edges}
    assert ("infra:compose:web", "infra:compose:api") in edge_pairs
    assert ("infra:compose:api", "infra:compose:db") in edge_pairs


def test_cross_domain_linker() -> None:
    ui_node = CrossDomainNode(
        node_id="frontend:user-card",
        domain=MigrationDomain.FRONTEND,
        name="user-card",
        entity_type="component",
        path="frontend/user-card.ts",
        metadata={"api_calls": ["/api/users"]},
    )
    api_node = CrossDomainNode(
        node_id="api:GET:/api/users",
        domain=MigrationDomain.BACKEND_API,
        name="GET /api/users",
        entity_type="endpoint",
        path="backend/server.js",
        metadata={"route_path": "/api/users", "tables_accessed": ["users"]},
    )
    db_node = CrossDomainNode(
        node_id="db:users",
        domain=MigrationDomain.DATABASE_SCHEMA,
        name="users",
        entity_type="table",
        path="database/schema.sql",
        metadata={"table_name": "users"},
    )
    compose_node = CrossDomainNode(
        node_id="infra:compose:web",
        domain=MigrationDomain.INFRASTRUCTURE,
        name="compose:web",
        entity_type="service",
        path="docker-compose.yml",
        metadata={"service_name": "web"},
    )

    nodes = (ui_node, api_node, db_node, compose_node)
    linker = CrossDomainLinker()
    edges = linker.link_domains(nodes)

    edge_tuples = [(e.source_node_id, e.relation, e.target_node_id) for e in edges]

    # UI -> API
    assert (
        "frontend:user-card",
        DependencyRelation.INVOKES_API,
        "api:GET:/api/users",
    ) in edge_tuples

    # API -> DB
    assert (
        "api:GET:/api/users",
        DependencyRelation.QUERIES_DB,
        "db:users",
    ) in edge_tuples

    # Infrastructure -> Frontend
    assert (
        "infra:compose:web",
        DependencyRelation.CONFIGURES,
        "frontend:user-card",
    ) in edge_tuples
