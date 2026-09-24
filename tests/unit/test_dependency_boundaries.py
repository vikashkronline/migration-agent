import ast
from pathlib import Path


def test_domain_does_not_import_outer_layers() -> None:
    repository_root = Path(__file__).parents[2]
    domain_root = repository_root / "src" / "migration_agent" / "domain"
    forbidden_roots = {
        "agents",
        "google",
        "openai",
        "typer",
        "migration_agent.adapters",
        "migration_agent.application",
        "migration_agent.orchestration",
        "migration_agent.persistence",
        "migration_agent.ports",
        "migration_agent.tools",
        "migration_agent.workspace",
    }

    imported_modules: set[str] = set()
    for module_path in domain_root.glob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    violations = {
        imported
        for imported in imported_modules
        if any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for forbidden in forbidden_roots
        )
    }
    assert violations == set()


def test_application_does_not_import_adapters_or_providers() -> None:
    repository_root = Path(__file__).parents[2]
    application_root = repository_root / "src" / "migration_agent" / "application"
    forbidden_roots = {
        "agents",
        "google",
        "openai",
        "typer",
        "migration_agent.adapters",
    }

    imported_modules: set[str] = set()
    for module_path in application_root.glob("*.py"):
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    violations = {
        imported
        for imported in imported_modules
        if any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for forbidden in forbidden_roots
        )
    }
    assert violations == set()
