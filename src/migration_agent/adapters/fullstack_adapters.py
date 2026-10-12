"""Read-only discovery adapters for multi-layer full-stack migration domains."""

import contextlib
import re
import sqlite3
from pathlib import Path, PurePosixPath
from typing import Any

from migration_agent.domain import (
    CrossDomainEdge,
    CrossDomainNode,
    DependencyRelation,
    FileCategory,
    FrameworkEvidence,
    MigrationDomain,
    RepositorySnapshot,
)
from migration_agent.ports.fullstack import DatabaseInspectorPort, DomainDiscoveryAdapterPort

# Regular expressions for Frontend API invocations
_FRONTEND_HTTP_PATTERNS = [
    re.compile(
        r"""(?:fetch|http\.(?:get|post|put|delete|patch)|axios\.(?:get|post|put|delete|patch))\s*\(\s*['"`]([a-zA-Z0-9_\-\/]+)['"`]"""
    ),
    re.compile(r"""(?:url|endpoint)\s*:\s*['"`]([a-zA-Z0-9_\-\/]+)['"`]"""),
]

# Regular expressions for Backend API endpoints
# FastAPI / Flask: @app.get("/api/users"), @router.post("/api/items")
_PYTHON_ENDPOINT_PATTERN = re.compile(
    r"""@(?:app|router|api)\.(get|post|put|delete|patch)\s*\(\s*['"]([a-zA-Z0-9_\-\/]+)['"](?:[^\)]*)\)\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)""",
    re.MULTILINE,
)
# Express.js: app.get('/api/users', ...), router.post('/api/items', ...)
_EXPRESS_ENDPOINT_PATTERN = re.compile(
    r"""(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['"]([a-zA-Z0-9_\-\/]+)['"]\s*,\s*(?:async\s*)?(?:function\s*([a-zA-Z0-9_]*)|\((?:[^)]*)\)\s*=>)""",
    re.MULTILINE,
)

# SQL Table queries in backend code: matches table in SELECT ... FROM table, INSERT INTO table, etc.
_SQL_TABLE_ACCESS_PATTERN = re.compile(
    r"""(?:SELECT\s+[\s\S]+?\s+FROM|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+['"`]?([a-zA-Z0-9_]+)['"`]?""",
    re.IGNORECASE,
)

# Regular expressions for SQL DDL
_SQL_CREATE_TABLE_PATTERN = re.compile(
    r"""CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?['"`]?([a-zA-Z0-9_]+)['"`]?\s*\(([^;]*?)\);""",
    re.IGNORECASE | re.DOTALL,
)
_SQL_FOREIGN_KEY_PATTERN = re.compile(
    r"""FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+['"`]?([a-zA-Z0-9_]+)['"`]?\s*\(([^)]+)\)""",
    re.IGNORECASE,
)


class FrontendDomainAdapter(DomainDiscoveryAdapterPort):
    """Discovers frontend UI components, templates, and outbound HTTP/API invocations."""

    @property
    def domain(self) -> MigrationDomain:
        return MigrationDomain.FRONTEND

    @property
    def adapter_id(self) -> str:
        return "frontend-domain-adapter"

    def discover_nodes(self, snapshot: RepositorySnapshot) -> tuple[CrossDomainNode, ...]:
        nodes: list[CrossDomainNode] = []
        for file in snapshot.files:
            if file.category not in (FileCategory.SOURCE, FileCategory.TEMPLATE):
                continue

            path_lower = file.path.lower()
            is_frontend_file = any(
                part in path_lower
                for part in (
                    "component",
                    "directive",
                    "template",
                    "view",
                    "frontend",
                    "/app/",
                    "/src/",
                )
            ) or path_lower.endswith((".hbs", ".html", ".css", ".scss"))

            if not is_frontend_file:
                continue

            api_calls: list[str] = []
            for pattern in _FRONTEND_HTTP_PATTERNS:
                for match in pattern.finditer(file.content):
                    endpoint = match.group(1).strip()
                    if endpoint.startswith("/") and len(endpoint) > 1:
                        api_calls.append(endpoint)

            name = PurePosixPath(file.path).stem
            node_id = f"frontend:file:{file.path}"

            if (
                "component" in path_lower
                or "directive" in path_lower
                or path_lower.endswith((".hbs", ".component.ts", ".component.js"))
                or api_calls
            ):
                nodes.append(
                    CrossDomainNode(
                        node_id=node_id,
                        domain=MigrationDomain.FRONTEND,
                        name=name,
                        entity_type="component",
                        path=file.path,
                        metadata={
                            "api_calls": sorted(set(api_calls)),
                            "is_template": path_lower.endswith((".hbs", ".html")),
                        },
                        evidence=(
                            FrameworkEvidence(
                                path=file.path,
                                kind="frontend_component",
                                description=f"Frontend component in {file.path}",
                                weight=0.8,
                            ),
                        ),
                    )
                )

        return tuple(sorted(nodes, key=lambda n: n.node_id))

    def discover_edges(
        self, snapshot: RepositorySnapshot, nodes: tuple[CrossDomainNode, ...]
    ) -> tuple[CrossDomainEdge, ...]:
        return ()


class BackendApiAdapter(DomainDiscoveryAdapterPort):
    """Discovers backend HTTP endpoints, route handlers, and database interactions."""

    @property
    def domain(self) -> MigrationDomain:
        return MigrationDomain.BACKEND_API

    @property
    def adapter_id(self) -> str:
        return "backend-api-adapter"

    def discover_nodes(self, snapshot: RepositorySnapshot) -> tuple[CrossDomainNode, ...]:
        nodes: list[CrossDomainNode] = []

        for file in snapshot.files:
            if file.category not in (FileCategory.SOURCE, FileCategory.MANIFEST):
                continue

            content = file.content

            # Check Python endpoints (FastAPI / Flask)
            if file.path.endswith(".py"):
                for match in _PYTHON_ENDPOINT_PATTERN.finditer(content):
                    method = match.group(1).upper()
                    route = match.group(2)
                    handler = match.group(3)
                    line_no = content[: match.start()].count("\n") + 1

                    tables = self._extract_table_mentions(content)

                    node_id = f"api:{method}:{route}"
                    nodes.append(
                        CrossDomainNode(
                            node_id=node_id,
                            domain=MigrationDomain.BACKEND_API,
                            name=f"{method} {route}",
                            entity_type="endpoint",
                            path=file.path,
                            line_number=line_no,
                            metadata={
                                "http_method": method,
                                "route_path": route,
                                "handler_name": handler,
                                "tables_accessed": sorted(tables),
                                "framework": "fastapi",
                            },
                            evidence=(
                                FrameworkEvidence(
                                    path=file.path,
                                    kind="backend_endpoint",
                                    description=f"FastAPI route {method} {route} in {file.path}",
                                    weight=0.9,
                                ),
                            ),
                        )
                    )

            # Check JavaScript/TypeScript endpoints (Express.js)
            if file.path.endswith((".js", ".ts")) and not file.path.endswith(
                (".spec.js", ".test.js", ".spec.ts", ".test.ts")
            ):
                for match in _EXPRESS_ENDPOINT_PATTERN.finditer(content):
                    method = match.group(1).upper()
                    route = match.group(2)
                    handler = match.group(3) or "anonymous_handler"
                    line_no = content[: match.start()].count("\n") + 1

                    tables = self._extract_table_mentions(content)

                    node_id = f"api:{method}:{route}"
                    nodes.append(
                        CrossDomainNode(
                            node_id=node_id,
                            domain=MigrationDomain.BACKEND_API,
                            name=f"{method} {route}",
                            entity_type="endpoint",
                            path=file.path,
                            line_number=line_no,
                            metadata={
                                "http_method": method,
                                "route_path": route,
                                "handler_name": handler,
                                "tables_accessed": sorted(tables),
                                "framework": "express",
                            },
                            evidence=(
                                FrameworkEvidence(
                                    path=file.path,
                                    kind="backend_endpoint",
                                    description=f"Express route {method} {route} in {file.path}",
                                    weight=0.9,
                                ),
                            ),
                        )
                    )

        unique_nodes = {node.node_id: node for node in nodes}
        return tuple(sorted(unique_nodes.values(), key=lambda n: n.node_id))

    def _extract_table_mentions(self, content: str) -> set[str]:
        tables: set[str] = set()
        for match in _SQL_TABLE_ACCESS_PATTERN.finditer(content):
            tbl = match.group(1).lower()
            if tbl not in (
                "select",
                "where",
                "set",
                "values",
                "null",
                "dual",
                "fastapi",
                "express",
                "true",
                "false",
            ):
                tables.add(tbl)
        return tables

    def discover_edges(
        self, snapshot: RepositorySnapshot, nodes: tuple[CrossDomainNode, ...]
    ) -> tuple[CrossDomainEdge, ...]:
        return ()


class SqlDatabaseAdapter(DomainDiscoveryAdapterPort, DatabaseInspectorPort):
    """Strict read-only database schema inspection via static DDL analysis
    and read-only SQLite inspection.
    """

    @property
    def domain(self) -> MigrationDomain:
        return MigrationDomain.DATABASE_SCHEMA

    @property
    def adapter_id(self) -> str:
        return "sql-database-adapter"

    @staticmethod
    def _split_table_body(body_str: str) -> list[str]:
        items: list[str] = []
        current: list[str] = []
        paren_depth = 0
        for char in body_str:
            if char == "(":
                paren_depth += 1
                current.append(char)
            elif char == ")":
                paren_depth -= 1
                current.append(char)
            elif char == "," and paren_depth == 0:
                item = "".join(current).strip()
                if item:
                    items.append(item)
                current = []
            else:
                current.append(char)
        last = "".join(current).strip()
        if last:
            items.append(last)
        return items

    def inspect_schema_file(self, file_path: str, content: str) -> tuple[CrossDomainNode, ...]:
        nodes: list[CrossDomainNode] = []
        for match in _SQL_CREATE_TABLE_PATTERN.finditer(content):
            table_name = match.group(1).lower()
            body = match.group(2)
            line_no = content[: match.start()].count("\n") + 1

            columns: list[str] = []
            foreign_keys: list[dict[str, str]] = []

            for line_str in self._split_table_body(body):
                line_str = line_str.strip()
                if not line_str or line_str.startswith("--"):
                    continue
                fk_match = _SQL_FOREIGN_KEY_PATTERN.search(line_str)
                if fk_match:
                    foreign_keys.append(
                        {
                            "column": fk_match.group(1).strip(),
                            "target_table": fk_match.group(2).strip().lower(),
                            "target_column": fk_match.group(3).strip(),
                        }
                    )
                elif not line_str.upper().startswith(
                    ("PRIMARY KEY", "CONSTRAINT", "UNIQUE", "CHECK")
                ):
                    parts = line_str.split()
                    if parts:
                        col_name = parts[0].replace('"', "").replace("`", "")
                        columns.append(col_name)

            node_id = f"db:{table_name}"
            nodes.append(
                CrossDomainNode(
                    node_id=node_id,
                    domain=MigrationDomain.DATABASE_SCHEMA,
                    name=table_name,
                    entity_type="table",
                    path=file_path,
                    line_number=line_no,
                    metadata={
                        "table_name": table_name,
                        "columns": columns,
                        "foreign_keys": foreign_keys,
                        "dialect": "sql",
                    },
                    evidence=(
                        FrameworkEvidence(
                            path=file_path,
                            kind="database_table",
                            description=f"Table definition '{table_name}' in {file_path}",
                            weight=1.0,
                        ),
                    ),
                )
            )
        return tuple(nodes)

    def inspect_sqlite_database(self, db_path: Path) -> tuple[CrossDomainNode, ...]:
        """Inspect local SQLite database strictly using read-only URI mode without writes."""
        nodes: list[CrossDomainNode] = []
        posix_path = db_path.as_posix()
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"

        try:
            conn = sqlite3.connect(uri, uri=True)
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = cursor.fetchall()
                for table_name, sql in tables:
                    table_name_clean = table_name.lower()
                    cursor.execute(f"PRAGMA foreign_key_list('{table_name}')")
                    fks = cursor.fetchall()
                    foreign_keys = [
                        {
                            "column": fk[3],
                            "target_table": fk[2].lower(),
                            "target_column": fk[4],
                        }
                        for fk in fks
                    ]

                    cursor.execute(f"PRAGMA table_info('{table_name}')")
                    cols = cursor.fetchall()
                    columns = [col[1] for col in cols]

                    node_id = f"db:{table_name_clean}"
                    nodes.append(
                        CrossDomainNode(
                            node_id=node_id,
                            domain=MigrationDomain.DATABASE_SCHEMA,
                            name=table_name_clean,
                            entity_type="table",
                            path=posix_path,
                            metadata={
                                "table_name": table_name_clean,
                                "columns": columns,
                                "foreign_keys": foreign_keys,
                                "dialect": "sqlite",
                                "raw_sql": sql or "",
                            },
                            evidence=(
                                FrameworkEvidence(
                                    path=posix_path,
                                    kind="sqlite_table",
                                    description=(
                                        f"SQLite table '{table_name_clean}' in {posix_path}"
                                    ),
                                    weight=1.0,
                                ),
                            ),
                        )
                    )
            finally:
                conn.close()
        except Exception:
            return ()

        return tuple(nodes)

    def discover_nodes(self, snapshot: RepositorySnapshot) -> tuple[CrossDomainNode, ...]:
        nodes: list[CrossDomainNode] = []

        # 1. Static inspection of SQL DDL / migration files
        for file in snapshot.files:
            if file.path.endswith(".sql") or "migrations" in file.path:
                nodes.extend(self.inspect_schema_file(file.path, file.content))

        # 2. Strict read-only inspection of SQLite databases in repository root
        for file in snapshot.files:
            if file.path.endswith((".db", ".sqlite", ".sqlite3")):
                db_file = snapshot.repository.root / file.path
                if db_file.is_file():
                    nodes.extend(self.inspect_sqlite_database(db_file))

        unique_nodes = {node.node_id: node for node in nodes}
        return tuple(sorted(unique_nodes.values(), key=lambda n: n.node_id))

    def discover_edges(
        self, snapshot: RepositorySnapshot, nodes: tuple[CrossDomainNode, ...]
    ) -> tuple[CrossDomainEdge, ...]:
        edges: list[CrossDomainEdge] = []
        table_nodes = {n.node_id: n for n in nodes if n.domain == MigrationDomain.DATABASE_SCHEMA}

        for node in table_nodes.values():
            foreign_keys = node.metadata.get("foreign_keys", [])
            for fk in foreign_keys:
                target_table = fk.get("target_table")
                target_node_id = f"db:{target_table}"
                if target_node_id in table_nodes and target_node_id != node.node_id:
                    edges.append(
                        CrossDomainEdge(
                            source_node_id=node.node_id,
                            target_node_id=target_node_id,
                            relation=DependencyRelation.DEPENDS_ON,
                            description=(
                                f"Table '{node.name}' foreign key references '{target_table}'"
                            ),
                            metadata=fk,
                        )
                    )

        return tuple(sorted(edges, key=lambda e: (e.source_node_id, e.target_node_id)))


class InfrastructureAdapter(DomainDiscoveryAdapterPort):
    """Discovers deployment and container infrastructure (Dockerfile, Docker Compose)."""

    @property
    def domain(self) -> MigrationDomain:
        return MigrationDomain.INFRASTRUCTURE

    @property
    def adapter_id(self) -> str:
        return "infrastructure-adapter"

    def discover_nodes(self, snapshot: RepositorySnapshot) -> tuple[CrossDomainNode, ...]:
        nodes: list[CrossDomainNode] = []

        for file in snapshot.files:
            path_lower = file.path.lower()

            # Dockerfile discovery
            if path_lower.endswith("dockerfile") or "dockerfile" in path_lower:
                base_image = "unknown"
                ports: list[int] = []
                for line in file.content.splitlines():
                    line_s = line.strip()
                    if line_s.upper().startswith("FROM "):
                        parts = line_s.split()
                        if len(parts) > 1:
                            base_image = parts[1]
                    elif line_s.upper().startswith("EXPOSE "):
                        with contextlib.suppress(ValueError, IndexError):
                            ports.append(int(line_s.split()[1]))

                parent_dir = Path(file.path).parent.name
                suffix_name = (
                    parent_dir if parent_dir and parent_dir != "." else Path(file.path).name
                )
                node_id = f"infra:dockerfile:{suffix_name}"
                nodes.append(
                    CrossDomainNode(
                        node_id=node_id,
                        domain=MigrationDomain.INFRASTRUCTURE,
                        name=Path(file.path).name,
                        entity_type="container",
                        path=file.path,
                        metadata={
                            "base_image": base_image,
                            "exposed_ports": sorted(ports),
                        },
                        evidence=(
                            FrameworkEvidence(
                                path=file.path,
                                kind="dockerfile",
                                description=f"Container specification in {file.path}",
                                weight=0.9,
                            ),
                        ),
                    )
                )

            # Docker Compose discovery
            if any(
                path_lower.endswith(name)
                for name in (
                    "docker-compose.yml",
                    "docker-compose.yaml",
                    "compose.yml",
                    "compose.yaml",
                )
            ):
                services = self._parse_compose_services(file.content)
                for s_name, s_meta in services.items():
                    node_id = f"infra:compose:{s_name}"
                    nodes.append(
                        CrossDomainNode(
                            node_id=node_id,
                            domain=MigrationDomain.INFRASTRUCTURE,
                            name=f"compose:{s_name}",
                            entity_type="service",
                            path=file.path,
                            metadata=s_meta,
                            evidence=(
                                FrameworkEvidence(
                                    path=file.path,
                                    kind="compose_service",
                                    description=f"Compose service '{s_name}' in {file.path}",
                                    weight=0.95,
                                ),
                            ),
                        )
                    )

        unique_nodes = {node.node_id: node for node in nodes}
        return tuple(sorted(unique_nodes.values(), key=lambda n: n.node_id))

    def _parse_compose_services(self, content: str) -> dict[str, dict[str, Any]]:
        services: dict[str, dict[str, Any]] = {}
        in_services = False
        service_indent: int | None = None
        current_service: str | None = None
        current_meta: dict[str, Any] = {}

        for line in content.splitlines():
            raw_line = line
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(raw_line) - len(raw_line.lstrip())

            if stripped == "services:":
                in_services = True
                service_indent = None
                continue

            if in_services:
                if (
                    service_indent is not None
                    and indent < service_indent
                    and not stripped.startswith("-")
                    and (not stripped.endswith(":") or indent == 0)
                ):
                    in_services = False
                    if current_service:
                        services[current_service] = current_meta
                        current_service = None
                    continue

                if service_indent is None:
                    if stripped.endswith(":") and not stripped.startswith("-"):
                        service_indent = indent
                    else:
                        continue

                if indent == service_indent and stripped.endswith(":"):
                    if current_service:
                        services[current_service] = current_meta
                    current_service = stripped[:-1].strip()
                    current_meta = {"service_name": current_service, "depends_on": []}
                elif indent > service_indent and current_service:
                    if stripped.startswith("image:"):
                        current_meta["image"] = stripped.split("image:", 1)[1].strip()
                    elif stripped.startswith("build:"):
                        current_meta["build"] = stripped.split("build:", 1)[1].strip()
                    elif stripped.startswith("- ") and "depends_on" in current_meta:
                        dep_val = stripped[2:].strip()
                        current_meta["depends_on"].append(dep_val)

        if current_service:
            services[current_service] = current_meta

        return services

    def discover_edges(
        self, snapshot: RepositorySnapshot, nodes: tuple[CrossDomainNode, ...]
    ) -> tuple[CrossDomainEdge, ...]:
        edges: list[CrossDomainEdge] = []
        infra_nodes = {n.node_id: n for n in nodes if n.domain == MigrationDomain.INFRASTRUCTURE}

        for node in infra_nodes.values():
            depends_on = node.metadata.get("depends_on", [])
            for dep in depends_on:
                target_node_id = f"infra:compose:{dep}"
                if target_node_id in infra_nodes:
                    edges.append(
                        CrossDomainEdge(
                            source_node_id=node.node_id,
                            target_node_id=target_node_id,
                            relation=DependencyRelation.DEPENDS_ON,
                            description=f"Service '{node.name}' depends on '{dep}'",
                        )
                    )

        return tuple(sorted(edges, key=lambda e: (e.source_node_id, e.target_node_id)))


def create_default_domain_adapters() -> tuple[DomainDiscoveryAdapterPort, ...]:
    """Factory creating the default domain discovery adapters."""
    return (
        FrontendDomainAdapter(),
        BackendApiAdapter(),
        SqlDatabaseAdapter(),
        InfrastructureAdapter(),
    )
