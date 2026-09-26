"""Stable JSON, Mermaid, and Markdown reporting for full-stack multi-layer architectures."""

import json
import os
import tempfile
from pathlib import Path

from migration_agent.domain import FullStackInventory, MigrationDomain


class FullStackReportWriter:
    """Write deterministic multi-layer reports and Mermaid diagrams outside the repository."""

    def write(
        self, inventory: FullStackInventory, output_directory: Path
    ) -> tuple[Path, Path, Path]:
        source_root = inventory.repository.root.resolve(strict=True)
        output_root = output_directory.expanduser().resolve(strict=False)

        if self._overlap(source_root, output_root):
            raise ValueError("output directory must not overlap the source repository")
        if output_root.exists() and not output_root.is_dir():
            raise ValueError("output path must be a directory")

        output_root.mkdir(parents=True, exist_ok=True)

        json_path = output_root / "fullstack_inventory.json"
        mermaid_path = output_root / "dependency_graph.mermaid"
        markdown_path = output_root / "fullstack_inventory.md"

        # 1. JSON report
        json_content = json.dumps(
            inventory.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        self._atomic_write(json_path, f"{json_content}\n")

        # 2. Mermaid diagram
        mermaid_content = inventory.graph.to_mermaid(direction="TD")
        self._atomic_write(mermaid_path, f"{mermaid_content}\n")

        # 3. Markdown report
        markdown_content = self._render_markdown(inventory, mermaid_content)
        self._atomic_write(markdown_path, f"{markdown_content}\n")

        return json_path, mermaid_path, markdown_path

    @staticmethod
    def _overlap(first: Path, second: Path) -> bool:
        return first == second or first in second.parents or second in first.parents

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                delete=False,
                newline="\n",
            ) as temporary_file:
                temporary_file.write(content)
                temporary_path = Path(temporary_file.name)
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _render_markdown(inventory: FullStackInventory, mermaid_diagram: str) -> str:
        lines: list[str] = [
            f"# Full-Stack Migration Inventory: {inventory.repository.name}",
            "",
            "## Architectural Domains Detected",
            "",
        ]

        if inventory.domains_detected:
            for domain in inventory.domains_detected:
                lines.append(f"- **{domain.value}**")
        else:
            lines.append("_No migration domains detected._")

        lines.extend(["", "## Layer Summary", ""])
        lines.append("| Domain | Node Count |")
        lines.append("| --- | ---: |")
        for domain in MigrationDomain:
            count = len(inventory.graph.get_nodes_by_domain(domain))
            lines.append(f"| {domain.value} | {count} |")
        lines.append(f"| **Total Edges** | **{len(inventory.graph.edges)}** |")

        lines.extend(["", "## Discovered Components & Endpoints", ""])
        lines.append("| Node ID | Domain | Entity Type | Path | Line |")
        lines.append("| --- | --- | --- | --- | ---: |")
        for node in sorted(inventory.graph.nodes, key=lambda n: (n.domain.value, n.node_id)):
            line_str = str(node.line_number) if node.line_number else "-"
            row = (
                f"| `{node.node_id}` | {node.domain.value} | {node.entity_type} "
                f"| `{node.path}` | {line_str} |"
            )
            lines.append(row)

        lines.extend(["", "## Cross-Domain Dependencies", ""])
        if inventory.graph.edges:
            lines.append("| Source Node | Relation | Target Node | Description |")
            lines.append("| --- | --- | --- | --- |")
            for edge in sorted(
                inventory.graph.edges,
                key=lambda e: (e.source_node_id, e.target_node_id, e.relation.value),
            ):
                edge_row = (
                    f"| `{edge.source_node_id}` | `{edge.relation.value}` "
                    f"| `{edge.target_node_id}` | {edge.description} |"
                )
                lines.append(edge_row)
        else:
            lines.append("_No cross-domain edges identified._")

        lines.extend(
            ["", "## Dependency Graph (Mermaid)", "", "```mermaid", mermaid_diagram, "```", ""]
        )

        return "\n".join(lines)
