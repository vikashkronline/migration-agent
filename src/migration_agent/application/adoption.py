"""Project adoption and new project initialization service (Master Plan Section 7)."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from migration_agent.application.fullstack_service import FullStackDiscoveryService
from migration_agent.application.inventory import InventoryService
from migration_agent.ports.governance import GovernancePort, ProjectManifest


@dataclass(frozen=True)
class AdoptionReport:
    """Outcome report from adopting an existing project repository."""

    project_id: str
    target_path: str
    docs_directory: str
    eligible_files_count: int
    detected_frameworks: tuple[str, ...]
    cross_domain_nodes_count: int
    architecture_doc_path: str
    mermaid_diagram_path: str


class ProjectAdoptionService:
    """Orchestrates Scenario A (init) and Scenario B (adopt) project lifecycle flows."""

    def __init__(
        self,
        governance: GovernancePort,
        inventory_service: InventoryService,
        fullstack_service: FullStackDiscoveryService,
    ) -> None:
        self._governance = governance
        self._inventory = inventory_service
        self._fullstack = fullstack_service

    def init(self, target_path: Path, project_id: str | None = None) -> ProjectManifest:
        """Scenario A: Initialize a new project with Git-native .agent/ governance layout."""
        resolved = target_path.resolve()
        resolved.mkdir(parents=True, exist_ok=True)

        self._governance.ensure_governance_layout(str(resolved), project_id=project_id)
        manifest = self._governance.get_manifest(str(resolved))
        if manifest is None:
            raise RuntimeError(f"Failed to initialize project manifest at '{resolved}'.")
        return manifest

    def adopt(
        self,
        target_path: Path,
        *,
        allow_dirty: bool = False,
        docs_dir: Path | None = None,
        project_id: str | None = None,
    ) -> AdoptionReport:
        """Scenario B: Adopt an existing repository into the agent platform.

        Performs strictly read-only inspection, verifies working-tree cleanliness,
        generates initial architecture documentation and Mermaid diagrams, and
        establishes .agent/ governance without touching application source files.
        """
        resolved = target_path.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError(f"Target path '{resolved}' must be a directory.")

        # 1. Cleanliness check for Git repository
        if (resolved / ".git").is_dir() and not allow_dirty:
            self._verify_git_clean(resolved)

        # 2. Deterministic discovery
        inventory = self._inventory.inventory(resolved)
        fullstack_inv = self._fullstack.discover(resolved)

        # 3. Initialize .agent/ layout
        self._governance.ensure_governance_layout(str(resolved), project_id=project_id)
        manifest = self._governance.get_manifest(str(resolved))
        pid = manifest.project_id if manifest else (project_id or resolved.name)

        # 4. Generate architecture documentation into docs/architecture
        architecture_dir = (docs_dir or (resolved / "docs" / "architecture")).resolve()
        architecture_dir.mkdir(parents=True, exist_ok=True)

        arch_doc = architecture_dir / "architecture.md"
        stack_doc = architecture_dir / "stack.md"
        mermaid_doc = architecture_dir / "dependencies.mermaid"

        # Generate Mermaid diagram
        mermaid_content = fullstack_inv.graph.to_mermaid(direction="TD")
        mermaid_doc.write_text(f"{mermaid_content}\n", encoding="utf-8")

        # Generate architecture summary
        frameworks_list = [f.framework_id for f in inventory.frameworks]
        fw_str = ", ".join(frameworks_list) if frameworks_list else "Generic"
        arch_content = (
            f"# Architecture Overview — {pid}\n\n"
            f"> **Epistemic Status:** Observed via Deterministic Discovery\n"
            f"> **Ownership:** Generated (Machine-created from code analysis)\n\n"
            f"## Technology Stack & Framework Evidence\n\n"
            f"- **Repository Root:** `{resolved}`\n"
            f"- **Eligible Files Count:** {len(inventory.files)}\n"
            f"- **Dependencies Count:** {len(inventory.dependencies)}\n"
            f"- **Detected Frameworks:** {fw_str}\n\n"
            f"## Package Boundaries\n\n"
        )
        if inventory.package_boundaries:
            for b in inventory.package_boundaries:
                arch_content += f"- `{b.path}` (manifest: `{b.manifest_path}`)\n"
        else:
            arch_content += "- Single-package repository structure\n"

        arch_content += (
            f"\n## Cross-Domain Dependency Graph\n\n```mermaid\n{mermaid_content}\n```\n"
        )
        arch_doc.write_text(arch_content, encoding="utf-8")

        # Generate stack summary
        stack_content = (
            f"# Technology Stack Inventory — {pid}\n\n"
            f"> **Generated:** Auto-discovered during repository adoption\n\n"
            f"## Inventory Files Summary\n\n"
            f"- Total files: {len(inventory.files)}\n"
            f"- Cross-domain nodes: {len(fullstack_inv.graph.nodes)}\n"
            f"- Cross-domain edges: {len(fullstack_inv.graph.edges)}\n\n"
            f"## Framework Signals\n\n"
        )
        for fw in inventory.frameworks:
            stack_content += (
                f"### Framework: `{fw.framework_id}` (Confidence: {fw.confidence:.2f})\n"
            )
            for ev in fw.evidence:
                stack_content += f"- `{ev.path}`: {ev.description} (weight: {ev.weight})\n"

        stack_doc.write_text(stack_content, encoding="utf-8")

        return AdoptionReport(
            project_id=pid,
            target_path=str(resolved),
            docs_directory=str(architecture_dir),
            eligible_files_count=len(inventory.files),
            detected_frameworks=tuple(frameworks_list),
            cross_domain_nodes_count=len(fullstack_inv.graph.nodes),
            architecture_doc_path=str(arch_doc),
            mermaid_diagram_path=str(mermaid_doc),
        )

    @staticmethod
    def _verify_git_clean(repo_root: Path) -> None:
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                raise RuntimeError(
                    f"Target repository at '{repo_root}' has uncommitted dirty changes. "
                    "Commit or stash changes before adoption, or pass --allow-dirty."
                )
        except FileNotFoundError:
            # git executable not available in environment
            pass
