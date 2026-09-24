"""Command-line entry point for Migration Agent."""

import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated

import typer

from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter
from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.adapters.gemini import GeminiRuntimeAdapter
from migration_agent.adapters.reporting import AnalysisReportWriter, InventoryReportWriter
from migration_agent.application import AnalysisService, InventoryService
from migration_agent.config import Settings
from migration_agent.ports import AgentRuntimePort, FrameworkAdapterRegistry, InspectionPolicy

app = typer.Typer(
    help="Controlled, evidence-based code migration tooling.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

_MINIMUM_PYTHON = (3, 12)
_RUNTIME_DISTRIBUTIONS = (
    "google-genai",
    "openai-agents",
    "pydantic",
    "pydantic-settings",
    "typer",
)


@app.callback()
def main() -> None:
    """Expose Migration Agent commands."""


def _installed_runtime_versions() -> dict[str, str | None]:
    installed: dict[str, str | None] = {}
    for distribution in _RUNTIME_DISTRIBUTIONS:
        try:
            installed[distribution] = version(distribution)
        except PackageNotFoundError:
            installed[distribution] = None
    return installed


def collect_diagnostics(
    *,
    python_version: tuple[int, int, int] | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    """Return diagnostics without reading secrets or contacting external services."""
    actual_python = python_version or (
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    )
    configured_settings = settings or Settings()
    runtime_versions = _installed_runtime_versions()

    python_ok = actual_python[:2] >= _MINIMUM_PYTHON
    dependencies_ok = all(value is not None for value in runtime_versions.values())
    overall_ok = python_ok and dependencies_ok

    return {
        "checks": [
            {
                "details": {
                    "actual": ".".join(str(part) for part in actual_python),
                    "minimum": ".".join(str(part) for part in _MINIMUM_PYTHON),
                },
                "name": "python",
                "status": "pass" if python_ok else "fail",
            },
            {
                "details": runtime_versions,
                "name": "runtime_dependencies",
                "status": "pass" if dependencies_ok else "fail",
            },
            {
                "details": {
                    "configured": bool(
                        configured_settings.agent_model and configured_settings.agent_model.strip()
                    ),
                    "required_for_doctor": False,
                },
                "name": "model_configuration",
                "status": "pass",
            },
        ],
        "schema_version": 1,
        "status": "ok" if overall_ok else "error",
    }


@app.command()
def doctor() -> None:
    """Print machine-readable local setup diagnostics."""
    diagnostics = collect_diagnostics()
    typer.echo(json.dumps(diagnostics, separators=(",", ":"), sort_keys=True))
    if diagnostics["status"] != "ok":
        raise typer.Exit(code=1)


@app.command("inventory")
def inventory_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Read-only source repository to inspect.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Separate directory for inventory.json and inventory.md.",
        ),
    ],
    max_file_bytes: Annotated[
        int,
        typer.Option(
            "--max-file-bytes",
            min=1,
            help="Maximum eligible text-file size to read.",
        ),
    ] = 1_000_000,
) -> None:
    """Create deterministic JSON and Markdown repository inventories."""
    service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
    )
    try:
        project_inventory = service.inventory(
            path,
            policy=InspectionPolicy(max_text_file_bytes=max_file_bytes),
        )
        json_path, markdown_path = InventoryReportWriter().write(project_inventory, output)
    except (OSError, ValueError) as error:
        typer.echo(
            json.dumps(
                {"error": str(error), "status": "error"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2) from error

    typer.echo(
        json.dumps(
            {
                "frameworks": [
                    framework.framework_id for framework in project_inventory.frameworks
                ],
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "status": "ok",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


@app.command("analyze")
def analyze_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Read-only source repository to analyze.",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Separate directory for analysis.json and analysis.md.",
        ),
    ],
    provider: Annotated[
        str | None,
        typer.Option(
            "--provider",
            "-p",
            help="LLM runtime provider: 'gemini' (default) or 'openai'.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="LLM model identifier to use (defaults to provider default).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Run read-only analysis without making any changes.",
        ),
    ] = True,
    max_turns: Annotated[
        int,
        typer.Option(
            "--max-turns",
            min=1,
            help="Maximum agent turn iterations.",
        ),
    ] = 15,
    max_file_bytes: Annotated[
        int,
        typer.Option(
            "--max-file-bytes",
            min=1,
            help="Maximum eligible text-file size to read.",
        ),
    ] = 1_000_000,
    fake_runtime: Annotated[
        bool,
        typer.Option(
            "--fake-runtime",
            help="Force use of deterministic offline fake runtime.",
        ),
    ] = False,
) -> None:
    """Analyze repository using a read-only agent to generate typed findings."""
    settings = Settings()
    chosen_provider = (provider or settings.runtime_provider or "gemini").strip().lower()

    if chosen_provider not in ("gemini", "openai", "fake"):
        typer.echo(
            json.dumps(
                {
                    "error": (
                        f"Unsupported runtime provider '{chosen_provider}'. "
                        "Supported providers: 'gemini', 'openai', 'fake'."
                    ),
                    "status": "error",
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    if chosen_provider == "gemini":
        default_model = "gemini-2.5-pro"
    elif chosen_provider == "openai":
        default_model = "gpt-4o"
    else:
        default_model = "fake-model"

    chosen_model = model or settings.effective_model or default_model

    runtime: AgentRuntimePort
    use_fake = (
        fake_runtime
        or os.getenv("MIGRATION_AGENT_FAKE_RUNTIME") == "1"
        or chosen_provider == "fake"
    )
    if use_fake:
        runtime = FakeAgentRuntime()
    elif chosen_provider == "gemini":
        runtime = GeminiRuntimeAdapter()
    elif chosen_provider == "openai":
        runtime = OpenAIAgentsRuntimeAdapter()
    else:
        runtime = FakeAgentRuntime()

    service = AnalysisService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
        runtime=runtime,
    )

    try:
        _, analysis_result = service.analyze(
            path,
            provider=chosen_provider,
            model=chosen_model,
            policy=InspectionPolicy(max_text_file_bytes=max_file_bytes),
            max_turns=max_turns,
            dry_run=dry_run,
        )
        json_path, markdown_path = AnalysisReportWriter().write(analysis_result, output)
    except (OSError, ValueError) as error:
        typer.echo(
            json.dumps(
                {"error": str(error), "status": "error"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2) from error

    typer.echo(
        json.dumps(
            {
                "findings_count": len(analysis_result.findings),
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
                "model": analysis_result.model,
                "provider": analysis_result.provider,
                "status": "ok",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    app()
