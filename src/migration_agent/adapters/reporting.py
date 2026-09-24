"""Stable JSON and Markdown inventory report output."""

import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from migration_agent.domain import AnalysisResult, ProjectInventory


class InventoryReportWriter:
    """Write deterministic reports outside the inspected source repository."""

    def write(self, inventory: ProjectInventory, output_directory: Path) -> tuple[Path, Path]:
        source_root = inventory.repository.root.resolve(strict=True)
        output_root = output_directory.expanduser().resolve(strict=False)
        if self._overlap(source_root, output_root):
            raise ValueError("output directory must not overlap the source repository")
        if output_root.exists() and not output_root.is_dir():
            raise ValueError("output path must be a directory")
        output_root.mkdir(parents=True, exist_ok=True)

        json_path = output_root / "inventory.json"
        markdown_path = output_root / "inventory.md"
        json_content = json.dumps(
            inventory.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        self._atomic_write(json_path, f"{json_content}\n")
        self._atomic_write(markdown_path, self._render_markdown(inventory))
        return json_path, markdown_path

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
    def _render_markdown(inventory: ProjectInventory) -> str:
        category_counts = Counter(file.category.value for file in inventory.files)
        lines = [
            "# Project Inventory",
            "",
            f"- Repository: `{inventory.repository.name}`",
            f"- Root: `{inventory.repository.root}`",
            f"- Eligible files: {len(inventory.files)}",
            f"- Dependencies: {len(inventory.dependencies)}",
            "",
            "## Framework fingerprints",
            "",
        ]
        if inventory.frameworks:
            for framework in inventory.frameworks:
                lines.append(
                    f"- `{framework.framework_id}`: confidence {framework.confidence:.2f} "
                    f"from {len(framework.evidence)} evidence item(s)"
                )
                for evidence in framework.evidence:
                    lines.append(f"  - `{evidence.path}` — {evidence.description}")
        else:
            lines.append("No supported framework was detected with sufficient confidence.")

        lines.extend(["", "## Files by category", ""])
        for category, count in sorted(category_counts.items()):
            lines.append(f"- `{category}`: {count}")
        if not category_counts:
            lines.append("No eligible web-project files were found.")

        lines.extend(["", "## Package boundaries", ""])
        for boundary in inventory.package_boundaries:
            workspace_label = "declared workspace" if boundary.declared_workspace else "package"
            lines.append(f"- `{boundary.path}` via `{boundary.manifest_path}` ({workspace_label})")
        if not inventory.package_boundaries:
            lines.append("No package manifests were found.")

        exclusions = inventory.exclusions
        lines.extend(
            [
                "",
                "## Exclusions",
                "",
                f"- Ignored entries: {exclusions.ignored_entries}",
                f"- Secret-like files: {exclusions.secret_like_files}",
                f"- Symlink or junction entries: {exclusions.symlink_entries}",
                f"- Binary files: {exclusions.binary_files}",
                f"- Oversized files: {exclusions.oversized_files}",
                f"- Unreadable entries: {exclusions.unreadable_entries}",
                f"- Outside-root entries: {exclusions.outside_root_entries}",
                "",
                "## Issues",
                "",
            ]
        )
        if inventory.issues:
            for issue in inventory.issues:
                lines.append(f"- `{issue.code}` at `{issue.path}`: {issue.message}")
        else:
            lines.append("No inventory issues were recorded.")
        return "\n".join(lines) + "\n"


class AnalysisReportWriter:
    """Write schema-versioned JSON and Markdown analysis reports atomically."""

    def write(self, result: AnalysisResult, output_directory: Path) -> tuple[Path, Path]:
        source_root = result.repository.root.resolve(strict=True)
        output_root = output_directory.expanduser().resolve(strict=False)
        if self._overlap(source_root, output_root):
            raise ValueError("output directory must not overlap the source repository")
        if output_root.exists() and not output_root.is_dir():
            raise ValueError("output path must be a directory")
        output_root.mkdir(parents=True, exist_ok=True)

        json_path = output_root / "analysis.json"
        markdown_path = output_root / "analysis.md"

        json_content = json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        self._atomic_write(json_path, f"{json_content}\n")
        self._atomic_write(markdown_path, self._render_markdown(result))
        return json_path, markdown_path

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
    def _render_markdown(result: AnalysisResult) -> str:
        mode_label = "Dry-run (Read-only)" if result.is_dry_run else "Standard Execution"
        lines = [
            "# Migration Analysis Report",
            "",
            f"- Repository: `{result.repository.name}`",
            f"- Provider: `{result.provider}`",
            f"- Model: `{result.model}`",
            f"- Mode: {mode_label}",
            f"- Total findings: {len(result.findings)}",
            "",
            "## Summary",
            "",
            result.summary,
            "",
            "## Findings",
            "",
        ]

        if not result.findings:
            lines.append("No specific migration findings were recorded.")
        else:
            for finding in result.findings:
                lines.extend(
                    [
                        f"### [{finding.severity.value.upper()}] {finding.title} (`{finding.id}`)",
                        "",
                        f"- Category: `{finding.category.value}`",
                        f"- Confidence: `{finding.confidence:.2f}`",
                        "",
                        finding.description,
                        "",
                    ]
                )
                if finding.evidence_references:
                    lines.append("#### Evidence")
                    lines.append("")
                    for ref in finding.evidence_references:
                        loc = f":{ref.line_number}" if ref.line_number else ""
                        status_tag = (
                            f"[{ref.status.value.upper()}] " if ref.status.value != "valid" else ""
                        )
                        lines.append(f"- {status_tag}`{ref.path}{loc}` — {ref.description}")
                        if ref.validation_note:
                            lines.append(f"  - **Validation Note:** {ref.validation_note}")
                        if ref.sample:
                            lines.append(f"  - **Sample:** `{ref.sample}`")
                    lines.append("")

                if finding.unsupported_constructs:
                    lines.append("#### Unsupported constructs")
                    lines.append("")
                    for construct in finding.unsupported_constructs:
                        lines.append(f"- {construct}")
                    lines.append("")

                if finding.assumptions:
                    lines.append("#### Assumptions")
                    lines.append("")
                    for assumption in finding.assumptions:
                        lines.append(f"- {assumption}")
                    lines.append("")

                if finding.questions:
                    lines.append("#### Open questions")
                    lines.append("")
                    for question in finding.questions:
                        lines.append(f"- {question}")
                    lines.append("")

        lines.extend(["## Global Considerations", ""])

        lines.append("### Unsupported constructs")
        lines.append("")
        if result.unsupported_constructs:
            for item in result.unsupported_constructs:
                lines.append(f"- {item}")
        else:
            lines.append("None identified.")
        lines.append("")

        lines.append("### Assumptions")
        lines.append("")
        if result.assumptions:
            for item in result.assumptions:
                lines.append(f"- {item}")
        else:
            lines.append("None declared.")
        lines.append("")

        lines.append("### Open questions")
        lines.append("")
        if result.questions:
            for item in result.questions:
                lines.append(f"- {item}")
        else:
            lines.append("None recorded.")
        lines.append("")

        return "\n".join(lines)
