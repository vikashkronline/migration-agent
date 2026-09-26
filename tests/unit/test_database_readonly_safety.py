"""Safety tests ensuring strict read-only database inspection (zero mutations)."""

import sqlite3
from pathlib import Path

from migration_agent.adapters.fullstack_adapters import SqlDatabaseAdapter
from migration_agent.domain import MigrationDomain


def test_sqlite_readonly_inspection(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"

    # Setup a genuine SQLite database
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, sku TEXT, price REAL);")
    cursor.execute("INSERT INTO products (sku, price) VALUES ('ABC', 19.99);")
    conn.commit()
    conn.close()

    adapter = SqlDatabaseAdapter()
    nodes = adapter.inspect_sqlite_database(db_file)

    assert len(nodes) == 1
    node = nodes[0]
    assert node.domain == MigrationDomain.DATABASE_SCHEMA
    assert node.node_id == "db:products"
    assert node.metadata.get("table_name") == "products"
    assert "sku" in node.metadata.get("columns", [])
    assert "price" in node.metadata.get("columns", [])

    # Verify that the DB was not modified
    verify_conn = sqlite3.connect(f"file:{db_file.resolve().as_posix()}?mode=ro", uri=True)
    v_cursor = verify_conn.cursor()
    v_cursor.execute("SELECT COUNT(*) FROM products;")
    assert v_cursor.fetchone()[0] == 1
    verify_conn.close()


def test_sqlite_readonly_enforcement(tmp_path: Path) -> None:
    """Verify that read-only mode rejects write attempts."""
    db_file = tmp_path / "protected.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE records (id INT);")
    conn.commit()
    conn.close()

    # Attempting to open in ?mode=ro prevents writes
    ro_conn = sqlite3.connect(f"file:{db_file.resolve().as_posix()}?mode=ro", uri=True)
    try:
        import sqlite3 as s

        try:
            ro_conn.execute("INSERT INTO records VALUES (1);")
            raise AssertionError("Write succeeded on read-only SQLite connection!")
        except s.OperationalError as e:
            assert "readonly" in str(e).lower() or "attempt to write" in str(e).lower()
    finally:
        ro_conn.close()


def test_corrupted_or_missing_database_handling(tmp_path: Path) -> None:
    adapter = SqlDatabaseAdapter()

    # 1. Non-existent file
    missing_file = tmp_path / "missing.db"
    assert adapter.inspect_sqlite_database(missing_file) == ()

    # 2. Corrupt / text file pretending to be sqlite
    fake_file = tmp_path / "fake.sqlite"
    fake_file.write_text("NOT A REAL SQLITE FILE")
    assert adapter.inspect_sqlite_database(fake_file) == ()


def test_malformed_ddl_handling() -> None:
    adapter = SqlDatabaseAdapter()
    malformed_sql = """
    -- Malformed SQL DDL
    CREATE TABLE;
    DROP DATABASE production;
    SELECT * FROM secret_passwords;
    CREATE TABLE valid_table (id INT, label TEXT);
    """
    nodes = adapter.inspect_schema_file("migrations/001.sql", malformed_sql)

    # Only valid table is extracted; DROP or SELECT statements do not execute or produce table nodes
    assert len(nodes) == 1
    assert nodes[0].name == "valid_table"
    assert nodes[0].metadata.get("columns") == ["id", "label"]
