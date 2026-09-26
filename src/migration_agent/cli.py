"""Command-line entry point for Migration Agent."""

import contextlib
import json
import os
import secrets
import sys
import time
import uuid
import webbrowser
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated

import typer
from typer.core import TyperGroup

from migration_agent.adapters import (
    AnalysisReportWriter,
    AngularAdapter,
    AngularJsDirectiveAdapter,
    CryptoSignatureVerifierAdapter,
    EmberClassicAdapter,
    FakeAgentRuntime,
    FakeCommandRunner,
    FullStackReportWriter,
    GeminiRuntimeAdapter,
    GitGovernanceAdapter,
    InMemoryEventBroadcaster,
    InventoryReportWriter,
    LocalTrustStoreAdapter,
    LocalWorkspaceAdapter,
    LoopbackControlServer,
    OpenAIAgentsRuntimeAdapter,
    SafeFilesystemInspector,
    SqliteCheckpointStore,
    SubprocessCommandRunner,
    create_default_domain_adapters,
)
from migration_agent.application import (
    AnalysisService,
    BoundedRepairService,
    ControlApiService,
    EvaluationService,
    FullStackDiscoveryService,
    InventoryService,
    PlanningService,
    ReportService,
    ResumableExecutionService,
    RuleBasedPlanValidator,
    SpecialistCoordinator,
    TransformationService,
    ValidationService,
)
from migration_agent.config import Settings
from migration_agent.domain import (
    AnalysisResult,
    ApplyStatus,
    AssuranceLevel,
    ChangeSet,
    EvaluationBenchmark,
    PlanStatus,
    ProjectInventory,
    RunStatus,
    ValidationCommand,
    ValidationProfile,
    ValidationStatus,
    compute_plan_digest,
    verify_approval,
)
from migration_agent.ports import (
    AgentRuntimePort,
    CommandRunnerPort,
    FrameworkAdapterRegistry,
    InspectionPolicy,
    SpecialistRuntimePort,
)

app = typer.Typer(
    help="Controlled, evidence-based code migration tooling.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

plan_app = typer.Typer(
    help="Create, inspect, approve, and reject typed migration plans.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(plan_app, name="plan")


class DefaultGroup(TyperGroup):
    """Custom TyperGroup enabling backward-compatible invocation of default 'start' command."""

    def parse_args(self, ctx: object, args: list[str]) -> list[str]:
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            args = ["start", *list(args)]
        return super().parse_args(ctx, args)  # type: ignore[arg-type]


run_app = typer.Typer(
    cls=DefaultGroup,
    help="Manage, inspect, execute, and resume migration runs.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(run_app, name="run")

_MINIMUM_PYTHON = (3, 12)
_RUNTIME_DISTRIBUTIONS = (
    "google-genai",
    "openai-agents",
    "pydantic",
    "pydantic-settings",
    "typer",
)


def _create_framework_registry() -> FrameworkAdapterRegistry:
    return FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
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
        frameworks=_create_framework_registry(),
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


@app.command("graph")
def graph_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Read-only source repository to inspect for full-stack domains.",
        ),
    ],
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: json, mermaid, or summary.",
        ),
    ] = "json",
    mermaid: Annotated[
        bool,
        typer.Option(
            "--mermaid",
            "-m",
            help="Output Mermaid flowchart directly to stdout.",
        ),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help="Optional directory to write full-stack inventory, Mermaid, and Markdown reports.",
        ),
    ] = None,
    impact_of: Annotated[
        str | None,
        typer.Option(
            "--impact-of",
            help="Node ID to compute upstream dependencies and downstream impact ripples for.",
        ),
    ] = None,
) -> None:
    """Discover full-stack domains and construct a cross-domain dependency graph."""
    service = FullStackDiscoveryService(
        filesystem=SafeFilesystemInspector(),
        adapters=create_default_domain_adapters(),
    )
    try:
        inventory = service.discover(path)
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

    written_files: dict[str, str] = {}
    if output_dir is not None:
        try:
            json_path, mermaid_path, markdown_path = FullStackReportWriter().write(
                inventory, output_dir
            )
            written_files = {
                "json_report": str(json_path),
                "mermaid_report": str(mermaid_path),
                "markdown_report": str(markdown_path),
            }
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

    impact_data: dict[str, object] | None = None
    if impact_of is not None:
        try:
            impact_report = inventory.graph.compute_impact(impact_of)
            impact_data = impact_report.model_dump(mode="json")
        except ValueError as err:
            typer.echo(
                json.dumps(
                    {"error": str(err), "status": "error"},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                err=True,
            )
            raise typer.Exit(code=1) from err

    if mermaid or format.lower() == "mermaid":
        typer.echo(inventory.graph.to_mermaid(direction="TD"))
        return

    if format.lower() == "summary":
        typer.echo(f"Repository: {inventory.repository.name}")
        typer.echo(f"Domains detected: {', '.join(d.value for d in inventory.domains_detected)}")
        typer.echo(
            f"Total nodes: {len(inventory.graph.nodes)}, Total edges: {len(inventory.graph.edges)}"
        )
        if impact_data:
            typer.echo(f"Impact of {impact_of}: {impact_data.get('impact_summary')}")
        return

    output_dict: dict[str, object] = {
        "repository": inventory.repository.name,
        "domains_detected": [d.value for d in inventory.domains_detected],
        "summary": inventory.summary,
        "nodes": [n.model_dump(mode="json") for n in inventory.graph.nodes],
        "edges": [e.model_dump(mode="json") for e in inventory.graph.edges],
        "status": "ok",
    }
    if impact_data:
        output_dict["impact_analysis"] = impact_data
    if written_files:
        output_dict["reports"] = written_files

    typer.echo(json.dumps(output_dict, separators=(",", ":"), sort_keys=True))


@app.command("fullstack")
def fullstack_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Read-only source repository to inspect for full-stack domains.",
        ),
    ],
    format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: json, mermaid, or summary.",
        ),
    ] = "json",
    mermaid: Annotated[
        bool,
        typer.Option(
            "--mermaid",
            "-m",
            help="Output Mermaid flowchart directly to stdout.",
        ),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            help="Optional directory to write full-stack inventory, Mermaid, and Markdown reports.",
        ),
    ] = None,
    impact_of: Annotated[
        str | None,
        typer.Option(
            "--impact-of",
            help="Node ID to compute upstream dependencies and downstream impact ripples for.",
        ),
    ] = None,
) -> None:
    """Discover full-stack domains and construct a cross-domain graph (alias for 'graph')."""
    graph_command(
        path=path,
        format=format,
        mermaid=mermaid,
        output_dir=output_dir,
        impact_of=impact_of,
    )


def _resolve_runtime(
    provider: str | None,
    model: str | None,
    fake_runtime: bool,
    settings: Settings,
) -> tuple[AgentRuntimePort, str, str]:
    chosen_provider = (provider or settings.runtime_provider or "gemini").strip().lower()

    if chosen_provider not in ("gemini", "openai", "fake"):
        raise ValueError(
            f"Unsupported runtime provider '{chosen_provider}'. "
            "Supported providers: 'gemini', 'openai', 'fake'."
        )

    if chosen_provider == "gemini":
        default_model = "gemini-2.5-pro"
    elif chosen_provider == "openai":
        default_model = "gpt-4o"
    else:
        default_model = "fake-model"

    chosen_model = model or settings.effective_model or default_model

    use_fake = (
        fake_runtime
        or os.getenv("MIGRATION_AGENT_FAKE_RUNTIME") == "1"
        or chosen_provider == "fake"
    )
    runtime: AgentRuntimePort
    if use_fake:
        runtime = FakeAgentRuntime()
    elif chosen_provider == "gemini":
        runtime = GeminiRuntimeAdapter()
    elif chosen_provider == "openai":
        runtime = OpenAIAgentsRuntimeAdapter()
    else:
        runtime = FakeAgentRuntime()

    return runtime, chosen_provider, chosen_model


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
    try:
        runtime, chosen_provider, chosen_model = _resolve_runtime(
            provider, model, fake_runtime, settings
        )
    except ValueError as err:
        typer.echo(
            json.dumps({"error": str(err), "status": "error"}, separators=(",", ":")),
            err=True,
        )
        raise typer.Exit(code=2) from err

    service = AnalysisService(
        filesystem=SafeFilesystemInspector(),
        frameworks=_create_framework_registry(),
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


@plan_app.command("create")
def plan_create_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Read-only source repository to plan migration for.",
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Directory for .agent/ governance assets. Defaults to target repository root.",
        ),
    ] = None,
    inventory: Annotated[
        Path | None,
        typer.Option(
            "--inventory",
            "-i",
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to pre-computed inventory.json (generated automatically if omitted).",
        ),
    ] = None,
    analysis: Annotated[
        Path | None,
        typer.Option(
            "--analysis",
            "-a",
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="Path to pre-computed analysis.json (generated automatically if omitted).",
        ),
    ] = None,
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
            help="LLM model identifier to use.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Run planning without making changes to target source.",
        ),
    ] = True,
    max_turns: Annotated[
        int,
        typer.Option(
            "--max-turns",
            min=1,
            help="Maximum agent turn iterations.",
        ),
    ] = 10,
    fake_runtime: Annotated[
        bool,
        typer.Option(
            "--fake-runtime",
            help="Force use of deterministic offline fake runtime.",
        ),
    ] = False,
    critic: Annotated[
        bool,
        typer.Option(
            "--critic/--no-critic",
            help="Enable adversarial Plan Critic subagent audit before finalizing plan.",
        ),
    ] = False,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Generate, validate, and persist an ordered migration plan."""
    settings = Settings()
    try:
        runtime, chosen_provider, chosen_model = _resolve_runtime(
            provider, model, fake_runtime, settings
        )
    except ValueError as err:
        typer.echo(
            json.dumps({"error": str(err), "status": "error"}, separators=(",", ":")),
            err=True,
        )
        raise typer.Exit(code=2) from err

    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()
    validator = RuleBasedPlanValidator(max_step_files=settings.max_step_files)

    try:
        # Resolve or run inventory
        if inventory is not None:
            project_inventory = ProjectInventory.model_validate_json(
                inventory.read_text(encoding="utf-8")
            )
        else:
            inv_service = InventoryService(
                filesystem=SafeFilesystemInspector(),
                frameworks=_create_framework_registry(),
            )
            project_inventory = inv_service.inventory(path)

        # Resolve or run analysis
        if analysis is not None:
            analysis_result = AnalysisResult.model_validate_json(
                analysis.read_text(encoding="utf-8")
            )
        else:
            an_service = AnalysisService(
                filesystem=SafeFilesystemInspector(),
                frameworks=_create_framework_registry(),
                runtime=runtime,
            )
            _, analysis_result = an_service.analyze(
                path,
                provider=chosen_provider,
                model=chosen_model,
                dry_run=dry_run,
            )

        specialist_rt = runtime if isinstance(runtime, SpecialistRuntimePort) else None
        planning_service = PlanningService(
            runtime=runtime,
            checkpoint_store=checkpoint_store,
            audit_logger=checkpoint_store,
            governance=governance,
            validator=validator,
            specialist_runtime=specialist_rt,
        )

        target_governance_root = str(output or path)
        plan, validation = planning_service.create_plan(
            inventory=project_inventory,
            analysis=analysis_result,
            project_root=target_governance_root,
            provider=chosen_provider,
            model=chosen_model,
            max_turns=max_turns,
            dry_run=dry_run,
            enable_critic=critic,
        )

        plan_digest = compute_plan_digest(plan)
        export_path = str(
            Path(target_governance_root) / ".agent" / "plans" / f"{plan.plan_id}.json"
        )

        typer.echo(
            json.dumps(
                {
                    "critic_enabled": critic,
                    "errors": validation.errors,
                    "export_file": export_path,
                    "is_valid": validation.is_valid,
                    "plan_digest": plan_digest,
                    "plan_id": plan.plan_id,
                    "policy_digest": plan.policy_digest,
                    "status": plan.status.value,
                    "step_count": len(plan.steps),
                    "warnings": validation.warnings,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        if not validation.is_valid:
            raise typer.Exit(code=1)
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


@plan_app.command("show")
def plan_show_command(
    plan_id: Annotated[
        str,
        typer.Argument(help="Unique identifier of the migration plan."),
    ],
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            "-r",
            help="Target repository root containing .agent/ governance assets.",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints.",
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Output format: 'json' or 'summary'.",
        ),
    ] = "json",
) -> None:
    """Display the details and current state of a migration plan."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()

    plan = checkpoint_store.get_plan(plan_id)
    if plan is None and project_root is not None:
        plan = governance.load_plan(str(project_root), plan_id)

    if plan is None:
        typer.echo(
            json.dumps(
                {"error": f"Plan '{plan_id}' not found.", "status": "error"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    if output_format.lower() == "summary":
        typer.echo(f"Plan ID:        {plan.plan_id}")
        typer.echo(f"Status:         {plan.status.value}")
        typer.echo(f"Source Root:    {plan.source_root}")
        typer.echo(f"Steps Count:    {len(plan.steps)}")
        typer.echo(f"Plan Digest:    {compute_plan_digest(plan)}")
        typer.echo(f"Policy Digest:  {plan.policy_digest}")
        if plan.approval:
            actor = plan.approval.actor
            mode = plan.approval.assurance_level.value
            typer.echo(f"Approved By:    {actor} ({mode})")
        if plan.rejection_reason:
            typer.echo(f"Rejection:      {plan.rejection_reason}")
    else:
        typer.echo(plan.model_dump_json(indent=2))


@plan_app.command("approve")
def plan_approve_command(
    plan_id: Annotated[
        str,
        typer.Argument(help="Unique identifier of the migration plan."),
    ],
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            "-a",
            help="Actor identity (key fingerprint, username, or role).",
        ),
    ],
    assurance_level: Annotated[
        str,
        typer.Option(
            "--assurance-level",
            help="Assurance level: 'MODE_A', 'MODE_B' (default), or 'MODE_C'.",
        ),
    ] = "MODE_B",
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            "-r",
            help="Target repository root containing .agent/ governance assets.",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
    signature: Annotated[
        str | None,
        typer.Option(
            "--signature",
            "-s",
            help="Cryptographic signature string for Mode A approval.",
        ),
    ] = None,
    key_id: Annotated[
        str | None,
        typer.Option(
            "--key-id",
            "-k",
            help="Trusted Authority Key ID or fingerprint.",
        ),
    ] = None,
    trust_dir: Annotated[
        Path | None,
        typer.Option(
            "--trust-dir",
            help="Custom directory for trusted authority keys (~/.agent-platform/trust/).",
        ),
    ] = None,
) -> None:
    """Approve a migration plan with cryptographic digest binding."""
    settings = Settings()
    try:
        level = AssuranceLevel(assurance_level.upper())
    except ValueError:
        typer.echo(
            json.dumps(
                {
                    "error": (
                        f"Invalid assurance level '{assurance_level}'. "
                        "Valid levels: 'MODE_A', 'MODE_B', 'MODE_C'."
                    ),
                    "status": "error",
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2) from None

    if level == AssuranceLevel.MODE_C:
        typer.echo(
            json.dumps(
                {
                    "error": "Mode C (unauthenticated) cannot approve migration plans.",
                    "status": "error",
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()
    runtime = FakeAgentRuntime()
    service = PlanningService(
        runtime=runtime,
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
        governance=governance,
    )

    authority_key = None
    signature_verifier = None

    if level == AssuranceLevel.MODE_A:
        if not signature:
            typer.echo(
                json.dumps(
                    {
                        "error": "Mode A approval requires --signature (-s).",
                        "status": "error",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                err=True,
            )
            raise typer.Exit(code=2)

        trust_store = LocalTrustStoreAdapter(trust_root=trust_dir)
        # Identify project_id from directory or default
        project_id = Path(project_root).resolve().name if project_root else "default"
        record = trust_store.load_trust_record(project_id)
        if record is None:
            typer.echo(
                json.dumps(
                    {
                        "error": (
                            f"No trust record found for project '{project_id}' in trust store."
                        ),
                        "status": "error",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                err=True,
            )

            raise typer.Exit(code=2)

        search_key = key_id or actor
        authority_key = record.find_key(search_key)
        if authority_key is None:
            typer.echo(
                json.dumps(
                    {
                        "error": f"Authority key '{search_key}' not found in project trust record.",
                        "status": "error",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                err=True,
            )
            raise typer.Exit(code=2)

        signature_verifier = CryptoSignatureVerifierAdapter()

    try:
        approved_plan = service.approve_plan(
            plan_id,
            actor=actor,
            assurance_level=level,
            project_root=str(project_root) if project_root else None,
            custom_signature=signature,
            authority_key=authority_key,
            signature_verifier=signature_verifier,
        )

        sig = approved_plan.approval
        typer.echo(
            json.dumps(
                {
                    "actor": sig.actor if sig else None,
                    "assurance_level": sig.assurance_level.value if sig else None,
                    "plan_digest": sig.plan_digest if sig else None,
                    "plan_id": approved_plan.plan_id,
                    "policy_digest": sig.policy_digest if sig else None,
                    "signature": sig.signature if sig else None,
                    "status": approved_plan.status.value,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    except ValueError as err:
        typer.echo(
            json.dumps({"error": str(err), "status": "error"}, separators=(",", ":")),
            err=True,
        )
        raise typer.Exit(code=2) from err


@plan_app.command("reject")
def plan_reject_command(
    plan_id: Annotated[
        str,
        typer.Argument(help="Unique identifier of the migration plan."),
    ],
    reason: Annotated[
        str,
        typer.Option(
            "--reason",
            help="Reason for rejecting the migration plan.",
        ),
    ],
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            help="Actor rejecting the plan.",
        ),
    ] = "user",
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            "-r",
            help="Target repository root containing .agent/ governance assets.",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Reject a migration plan and record the rejection reason."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()
    runtime = FakeAgentRuntime()
    service = PlanningService(
        runtime=runtime,
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
        governance=governance,
    )

    try:
        rejected_plan = service.reject_plan(
            plan_id,
            reason=reason,
            actor=actor,
            project_root=str(project_root) if project_root else None,
        )
        typer.echo(
            json.dumps(
                {
                    "plan_id": rejected_plan.plan_id,
                    "rejection_reason": rejected_plan.rejection_reason,
                    "status": rejected_plan.status.value,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    except ValueError as err:
        typer.echo(
            json.dumps({"error": str(err), "status": "error"}, separators=(",", ":")),
            err=True,
        )
        raise typer.Exit(code=2) from err


def _create_transformation_service(
    checkpoint_store: SqliteCheckpointStore,
) -> TransformationService:
    return TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        registry=_create_framework_registry(),
        filesystem=SafeFilesystemInspector(),
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
    )


def _create_execution_service(
    checkpoint_store: SqliteCheckpointStore,
    runner: CommandRunnerPort,
    max_repairs: int = 3,
) -> ResumableExecutionService:
    trans_service = _create_transformation_service(checkpoint_store)
    val_service = ValidationService(command_runner=runner, audit_logger=checkpoint_store)
    repair_service = BoundedRepairService(
        command_runner=runner,
        workspace_adapter=LocalWorkspaceAdapter(),
        validation_service=val_service,
        audit_logger=checkpoint_store,
        checkpoint_store=checkpoint_store,
        max_budget=max_repairs,
    )
    report_service = ReportService(checkpoint_store=checkpoint_store, audit_logger=checkpoint_store)
    return ResumableExecutionService(
        checkpoint_store=checkpoint_store,
        transformation_service=trans_service,
        validation_service=val_service,
        repair_service=repair_service,
        report_service=report_service,
        audit_logger=checkpoint_store,
    )


@app.command("preview")
def preview_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Source repository path to inspect.",
        ),
    ],
    plan_id: Annotated[
        str,
        typer.Option(
            "--plan",
            "-p",
            help="Migration plan ID to preview changes for.",
        ),
    ],
    step_id: Annotated[
        str | None,
        typer.Option(
            "--step",
            "-s",
            help="Optional specific step ID within the plan.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Optional directory to write changeset.json and preview.diff.",
        ),
    ] = None,
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            "-r",
            help="Target repository root containing .agent/ governance assets.",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Generate proposed ChangeSet and unified diff without modifying source or staging."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()

    plan = checkpoint_store.get_plan(plan_id)
    if plan is None and project_root is not None:
        plan = governance.load_plan(str(project_root), plan_id)
    if plan is None:
        plan = governance.load_plan(str(path), plan_id)

    if plan is None:
        typer.echo(
            json.dumps(
                {"error": f"Plan '{plan_id}' not found.", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    service = _create_transformation_service(checkpoint_store)

    try:
        changeset, diff_text = service.preview(path, plan, step_id=step_id)
    except Exception as err:
        typer.echo(
            json.dumps({"error": str(err), "status": "error"}, separators=(",", ":")),
            err=True,
        )
        raise typer.Exit(code=2) from err

    result_data: dict[str, object] = {
        "changeset_digest": changeset.changeset_digest,
        "changeset_id": changeset.changeset_id,
        "file_count": len(changeset.changes),
        "plan_id": plan.plan_id,
        "status": "ok",
        "worktree_fingerprint": changeset.worktree_fingerprint,
    }

    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        changeset_file = output / "changeset.json"
        diff_file = output / "preview.diff"
        changeset_file.write_text(changeset.model_dump_json(indent=2), encoding="utf-8")
        diff_file.write_text(diff_text, encoding="utf-8")
        result_data["changeset_path"] = str(changeset_file)
        result_data["diff_path"] = str(diff_file)

    typer.echo(json.dumps(result_data, separators=(",", ":"), sort_keys=True))


@app.command("stage")
def stage_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Source repository path to stage from.",
        ),
    ],
    plan_id: Annotated[
        str,
        typer.Option(
            "--plan",
            "-p",
            help="Approved migration plan ID to stage.",
        ),
    ],
    step_id: Annotated[
        str | None,
        typer.Option(
            "--step",
            "-s",
            help="Optional specific step ID within the plan.",
        ),
    ] = None,
    staging_root: Annotated[
        Path | None,
        typer.Option(
            "--staging-root",
            file_okay=False,
            help="Custom root directory to create isolated staging workspace.",
        ),
    ] = None,
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            "-r",
            help="Target repository root containing .agent/ governance assets.",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Materialize proposed ChangeSet in an isolated staging workspace after verifying approval."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    effective_staging_root = settings.resolve_staging_root(staging_root)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()

    plan = checkpoint_store.get_plan(plan_id)
    if plan is None and project_root is not None:
        plan = governance.load_plan(str(project_root), plan_id)
    if plan is None:
        plan = governance.load_plan(str(path), plan_id)

    if plan is None:
        typer.echo(
            json.dumps(
                {"error": f"Plan '{plan_id}' not found.", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    if plan.status != PlanStatus.APPROVED or not verify_approval(plan):
        typer.echo(
            json.dumps(
                {
                    "error": (
                        f"Cannot stage unapproved or modified plan '{plan_id}' "
                        f"(status: {plan.status.value})."
                    ),
                    "status": "error",
                },
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    service = _create_transformation_service(checkpoint_store)

    run_id = f"stage-{uuid.uuid4().hex[:8]}"
    try:
        staging_dir, changeset = service.stage(
            staging_root=effective_staging_root,
            run_id=run_id,
            source_root=path,
            plan=plan,
            step_id=step_id,
        )
    except Exception as err:
        typer.echo(
            json.dumps({"error": str(err), "status": "error"}, separators=(",", ":")),
            err=True,
        )
        raise typer.Exit(code=2) from err

    typer.echo(
        json.dumps(
            {
                "changeset_digest": changeset.changeset_digest,
                "changeset_id": changeset.changeset_id,
                "file_count": len(changeset.changes),
                "plan_id": plan.plan_id,
                "staging_path": str(staging_dir),
                "status": "ok",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


@app.command("apply")
def apply_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Target repository path to apply changes to.",
        ),
    ],
    plan_id: Annotated[
        str,
        typer.Option(
            "--plan",
            "-p",
            help="Approved migration plan ID.",
        ),
    ],
    changeset_id: Annotated[
        str | None,
        typer.Option(
            "--changeset",
            "-c",
            help="Optional specific changeset ID to apply.",
        ),
    ] = None,
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            "-a",
            help="Actor executing the controlled apply.",
        ),
    ] = "operator",
    backup_root: Annotated[
        Path | None,
        typer.Option(
            "--backup-root",
            file_okay=False,
            help="Optional custom root directory for pre-apply file backups.",
        ),
    ] = None,
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            "-r",
            help="Target repository root containing .agent/ governance assets.",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Execute ADR-8 4-step controlled apply protocol with verified rollback."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()

    plan = checkpoint_store.get_plan(plan_id)
    if plan is None and project_root is not None:
        plan = governance.load_plan(str(project_root), plan_id)
    if plan is None:
        plan = governance.load_plan(str(path), plan_id)

    if plan is None:
        typer.echo(
            json.dumps(
                {"error": f"Plan '{plan_id}' not found.", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    if plan.status != PlanStatus.APPROVED or not verify_approval(plan):
        typer.echo(
            json.dumps(
                {
                    "error": (
                        f"Cannot apply unapproved or modified plan '{plan_id}' "
                        f"(status: {plan.status.value})."
                    ),
                    "status": "error",
                },
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    service = _create_transformation_service(checkpoint_store)

    changeset: ChangeSet | None = None
    if changeset_id is not None:
        changeset = checkpoint_store.get_changeset(changeset_id)
        if changeset is None:
            cs_path = Path(changeset_id)
            if cs_path.is_file():
                try:
                    changeset = ChangeSet.model_validate_json(cs_path.read_text(encoding="utf-8"))
                except Exception as read_err:
                    typer.echo(
                        json.dumps(
                            {
                                "error": f"Failed reading ChangeSet file: {read_err}",
                                "status": "error",
                            },
                            separators=(",", ":"),
                        ),
                        err=True,
                    )
                    raise typer.Exit(code=2) from read_err

        if changeset is None:
            typer.echo(
                json.dumps(
                    {"error": f"ChangeSet '{changeset_id}' not found.", "status": "error"},
                    separators=(",", ":"),
                ),
                err=True,
            )
            raise typer.Exit(code=2)
    else:
        changeset, _ = service.preview(path, plan)

    result = service.apply(
        source_root=path,
        changeset=changeset,
        plan=plan,
        actor=actor,
        backup_root=backup_root,
    )

    output_payload: dict[str, object] = {
        "applied_paths": list(result.applied_paths),
        "backup_snapshot_path": result.backup_snapshot_path,
        "changeset_id": result.changeset_id,
        "diagnostics": list(result.diagnostics),
        "status": result.status.value,
    }
    if result.recovery_details:
        output_payload["recovery_details"] = result.recovery_details

    if result.status == ApplyStatus.APPLIED:
        typer.echo(json.dumps(output_payload, separators=(",", ":"), sort_keys=True))
    else:
        typer.echo(
            json.dumps(output_payload, separators=(",", ":"), sort_keys=True),
            err=True,
        )
        raise typer.Exit(code=2)


@app.command("validate")
def validate_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Target repository or staging workspace path.",
        ),
    ],
    plan_id: Annotated[
        str | None,
        typer.Option(
            "--plan",
            "-p",
            help="Associated migration plan ID.",
        ),
    ] = None,
    staging_dir: Annotated[
        Path | None,
        typer.Option(
            "--staging-dir",
            file_okay=False,
            dir_okay=True,
            help="Explicit staging workspace path to validate.",
        ),
    ] = None,
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            help="Validation profile (LINT, TYPECHECK, TEST, BUILD, ALL).",
        ),
    ] = "ALL",
    fake_runner: Annotated[
        bool,
        typer.Option(
            "--fake-runner",
            help="Use deterministic FakeCommandRunner for offline verification.",
        ),
    ] = False,
    fail_validation: Annotated[
        bool,
        typer.Option(
            "--fail-validation",
            help="Simulate validation failure when using fake runner.",
        ),
    ] = False,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Run allowlisted validation checks against a staging workspace."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)

    target_dir = staging_dir or path
    if not target_dir.exists():
        typer.echo(
            json.dumps({"error": f"Directory '{target_dir}' does not exist.", "status": "error"}),
            err=True,
        )
        raise typer.Exit(code=2)

    profiles: list[ValidationProfile] = []
    norm_profile = profile.upper()
    if norm_profile == "ALL":
        profiles = [
            ValidationProfile.LINT,
            ValidationProfile.TYPECHECK,
            ValidationProfile.TEST,
            ValidationProfile.BUILD,
        ]
    else:
        try:
            profiles = [ValidationProfile(norm_profile)]
        except ValueError:
            msg = f"Invalid profile '{profile}'. Allowed: LINT, TYPECHECK, TEST, BUILD, ALL."
            typer.echo(
                json.dumps({"error": msg, "status": "error"}, separators=(",", ":")),
                err=True,
            )
            raise typer.Exit(code=2) from None

    angular_adapter = AngularAdapter()
    commands: list[ValidationCommand] = []
    for p in profiles:
        commands.extend(angular_adapter.get_validation_commands(p))

    runner: CommandRunnerPort
    if fake_runner:
        runner = FakeCommandRunner(
            default_status=ValidationStatus.FAILED if fail_validation else ValidationStatus.PASSED,
            default_exit_code=1 if fail_validation else 0,
            default_output=(
                "Simulated failure diagnostic: syntax error in component"
                if fail_validation
                else "All checks passed."
            ),
            diagnostics=("syntax error in component",) if fail_validation else (),
        )
    else:
        runner = SubprocessCommandRunner()

    service = ValidationService(command_runner=runner, audit_logger=checkpoint_store)
    run_id = f"val-{uuid.uuid4().hex[:8]}"
    results = service.validate(target_dir, commands, run_id=run_id)

    all_passed = all(r.status == ValidationStatus.PASSED for r in results)
    payload = {
        "plan_id": plan_id,
        "run_id": run_id,
        "status": "ok" if all_passed else "failed",
        "target_dir": str(target_dir),
        "validation_results": [
            {
                "command": r.command,
                "diagnostics": list(r.diagnostics),
                "duration_ms": r.duration_ms,
                "exit_code": r.exit_code,
                "output_digest": r.output_digest,
                "profile": r.profile.value,
                "status": r.status.value,
            }
            for r in results
        ],
    }

    if all_passed:
        typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    else:
        typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True), err=True)
        raise typer.Exit(code=2)


@run_app.command("start", hidden=True)
def run_start_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Target repository path to run migration against.",
        ),
    ],
    plan_id: Annotated[
        str,
        typer.Option(
            "--plan",
            "-p",
            help="Approved migration plan ID to execute and validate.",
        ),
    ],
    auto_repair: Annotated[
        bool,
        typer.Option(
            "--auto-repair",
            help="Enable bounded self-repair loop on validation failure.",
        ),
    ] = False,
    max_repairs: Annotated[
        int,
        typer.Option(
            "--max-repairs",
            help="Maximum repair attempts budget.",
        ),
    ] = 3,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Directory to save run reports.",
        ),
    ] = None,
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            "-a",
            help="Actor executing the migration run.",
        ),
    ] = "operator",
    fake_runner: Annotated[
        bool,
        typer.Option(
            "--fake-runner",
            help="Use deterministic FakeCommandRunner for offline verification.",
        ),
    ] = False,
    fail_validation: Annotated[
        bool,
        typer.Option(
            "--fail-validation",
            help="Simulate validation failure in fake runner.",
        ),
    ] = False,
    project_root: Annotated[
        Path | None,
        typer.Option(
            "--project-root",
            "-r",
            help="Target repository root containing .agent/ governance assets.",
        ),
    ] = None,
    staging_root: Annotated[
        Path | None,
        typer.Option(
            "--staging-root",
            help="Custom root directory for staging workspaces.",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Execute end-to-end migration run: stage, validate, bounded repair, and report."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    effective_staging_root = settings.resolve_staging_root(staging_root)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()

    plan = checkpoint_store.get_plan(plan_id)
    if plan is None and project_root is not None:
        plan = governance.load_plan(str(project_root), plan_id)
    if plan is None:
        plan = governance.load_plan(str(path), plan_id)

    if plan is None:
        typer.echo(
            json.dumps(
                {"error": f"Plan '{plan_id}' not found.", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    if plan.status != PlanStatus.APPROVED or not verify_approval(plan):
        err_msg = (
            f"Cannot run unapproved or modified plan '{plan_id}' (status: {plan.status.value})."
        )
        typer.echo(
            json.dumps(
                {"error": err_msg, "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    angular_adapter = AngularAdapter()
    commands: list[ValidationCommand] = []
    for p in (
        ValidationProfile.LINT,
        ValidationProfile.TYPECHECK,
        ValidationProfile.TEST,
        ValidationProfile.BUILD,
    ):
        commands.extend(angular_adapter.get_validation_commands(p))

    runner: CommandRunnerPort
    if fake_runner:
        runner = FakeCommandRunner(
            default_status=ValidationStatus.FAILED if fail_validation else ValidationStatus.PASSED,
            default_exit_code=1 if fail_validation else 0,
            default_output=(
                "Simulated failure diagnostic: syntax error in component"
                if fail_validation
                else "All checks passed."
            ),
            diagnostics=("syntax error in component",) if fail_validation else (),
        )
    else:
        runner = SubprocessCommandRunner()

    execution_service = _create_execution_service(
        checkpoint_store=checkpoint_store,
        runner=runner,
        max_repairs=max_repairs,
    )

    report_output_dir = output_dir or (effective_state_dir / "reports")

    try:
        run_record, report = execution_service.start_run(
            source_root=path,
            plan=plan,
            staging_root=effective_staging_root,
            commands=commands,
            auto_repair=auto_repair,
            max_repairs=max_repairs,
            output_dir=report_output_dir,
            actor=actor,
        )
    except Exception as err:
        typer.echo(
            json.dumps(
                {"error": f"Run execution failed: {err}", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2) from err

    json_report_path = report_output_dir / f"run_report_{report.run_id}.json"
    md_report_path = report_output_dir / f"run_report_{report.run_id}.md"

    summary_payload = {
        "json_report_path": str(json_report_path),
        "md_report_path": str(md_report_path),
        "plan_id": plan.plan_id,
        "repair_attempts_count": len(report.repair_attempts),
        "run_id": run_record.run_id,
        "staging_path": run_record.staging_root or "",
        "status": report.status.value,
        "validation_checks_count": len(report.validation_results),
    }

    if report.status == RunStatus.SUCCESS:
        typer.echo(json.dumps(summary_payload, separators=(",", ":"), sort_keys=True))
    else:
        typer.echo(json.dumps(summary_payload, separators=(",", ":"), sort_keys=True), err=True)
        raise typer.Exit(code=2)


@run_app.command("list")
def run_list_command(
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """List recorded migration runs."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)

    records = checkpoint_store.list_run_records()
    payload = [
        {
            "applied_changeset_id": r.applied_changeset_id,
            "created_at": r.created_at.isoformat(),
            "current_step_id": r.current_step_id,
            "plan_id": r.plan_id,
            "run_id": r.run_id,
            "source_root": r.source_root,
            "staging_root": r.staging_root,
            "status": r.status.value,
            "updated_at": r.updated_at.isoformat(),
        }
        for r in records
    ]
    typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True))


@run_app.command("show")
def run_show_command(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID of the migration run to inspect."),
    ],
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Display details and state transitions for a specific migration run."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)

    record = checkpoint_store.get_run_record(run_id)
    if record is None:
        typer.echo(
            json.dumps(
                {"error": f"Run '{run_id}' not found.", "status": "error"}, separators=(",", ":")
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    report = checkpoint_store.get_run_report(run_id)
    checkpoints = checkpoint_store.list_checkpoints(run_id)

    payload = {
        "applied_changeset_id": record.applied_changeset_id,
        "checkpoints_count": len(checkpoints),
        "created_at": record.created_at.isoformat(),
        "current_step_id": record.current_step_id,
        "plan_id": record.plan_id,
        "report_status": report.status.value if report else None,
        "run_id": record.run_id,
        "source_root": record.source_root,
        "staging_root": record.staging_root,
        "status": record.status.value,
        "updated_at": record.updated_at.isoformat(),
    }
    typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True))


@run_app.command("resume")
def run_resume_command(
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID of the interrupted run to resume."),
    ],
    auto_repair: Annotated[
        bool,
        typer.Option(
            "--auto-repair",
            help="Enable bounded self-repair loop on validation failure.",
        ),
    ] = True,
    max_repairs: Annotated[
        int,
        typer.Option(
            "--max-repairs",
            help="Maximum repair attempts budget.",
        ),
    ] = 3,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Directory to save run reports.",
        ),
    ] = None,
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            "-a",
            help="Actor executing the migration run.",
        ),
    ] = "operator",
    fake_runner: Annotated[
        bool,
        typer.Option(
            "--fake-runner",
            help="Use deterministic FakeCommandRunner for offline verification.",
        ),
    ] = False,
    fail_validation: Annotated[
        bool,
        typer.Option(
            "--fail-validation",
            help="Simulate validation failure in fake runner.",
        ),
    ] = False,
    staging_root: Annotated[
        Path | None,
        typer.Option(
            "--staging-root",
            help="Custom root directory for staging workspaces.",
        ),
    ] = None,
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Resume an interrupted migration run from its latest operational checkpoint."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    effective_staging_root = settings.resolve_staging_root(staging_root)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)

    record = checkpoint_store.get_run_record(run_id)
    if record is None:
        typer.echo(
            json.dumps(
                {"error": f"Run '{run_id}' not found.", "status": "error"}, separators=(",", ":")
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    plan = checkpoint_store.get_plan(record.plan_id)
    if plan is None:
        typer.echo(
            json.dumps(
                {
                    "error": f"Plan '{record.plan_id}' associated with run '{run_id}' not found.",
                    "status": "error",
                },
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    angular_adapter = AngularAdapter()
    commands: list[ValidationCommand] = []
    for p in (
        ValidationProfile.LINT,
        ValidationProfile.TYPECHECK,
        ValidationProfile.TEST,
        ValidationProfile.BUILD,
    ):
        commands.extend(angular_adapter.get_validation_commands(p))

    runner: CommandRunnerPort
    if fake_runner:
        runner = FakeCommandRunner(
            default_status=ValidationStatus.FAILED if fail_validation else ValidationStatus.PASSED,
            default_exit_code=1 if fail_validation else 0,
            default_output=(
                "Simulated failure diagnostic: syntax error in component"
                if fail_validation
                else "All checks passed."
            ),
            diagnostics=("syntax error in component",) if fail_validation else (),
        )
    else:
        runner = SubprocessCommandRunner()

    execution_service = _create_execution_service(
        checkpoint_store=checkpoint_store,
        runner=runner,
        max_repairs=max_repairs,
    )

    report_output_dir = output_dir or (effective_state_dir / "reports")

    try:
        updated_record, report = execution_service.resume_run(
            run_id=run_id,
            staging_root=effective_staging_root,
            commands=commands,
            auto_repair=auto_repair,
            max_repairs=max_repairs,
            output_dir=report_output_dir,
            actor=actor,
        )
    except Exception as err:
        typer.echo(
            json.dumps(
                {"error": f"Resume failed: {err}", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2) from err

    json_report_path = report_output_dir / f"run_report_{report.run_id}.json"
    md_report_path = report_output_dir / f"run_report_{report.run_id}.md"

    summary_payload = {
        "json_report_path": str(json_report_path),
        "md_report_path": str(md_report_path),
        "plan_id": plan.plan_id,
        "repair_attempts_count": len(report.repair_attempts),
        "run_id": updated_record.run_id,
        "staging_path": updated_record.staging_root or "",
        "status": report.status.value,
        "validation_checks_count": len(report.validation_results),
    }

    if report.status == RunStatus.SUCCESS:
        typer.echo(json.dumps(summary_payload, separators=(",", ":"), sort_keys=True))
    else:
        typer.echo(json.dumps(summary_payload, separators=(",", ":"), sort_keys=True), err=True)
        raise typer.Exit(code=2)


@app.command("eval")
def eval_command(
    path: Annotated[
        Path | None,
        typer.Argument(
            help="Target fixture path to evaluate. Defaults to tests/fixtures/ember-classic-mini.",
        ),
    ] = None,
    min_precision: Annotated[
        float,
        typer.Option("--min-precision", help="Minimum required precision score."),
    ] = 0.8,
    min_recall: Annotated[
        float,
        typer.Option("--min-recall", help="Minimum required recall score."),
    ] = 0.8,
    with_specialists: Annotated[
        bool,
        typer.Option("--with-specialists", help="Run benchmark with specialist subagents enabled."),
    ] = False,
) -> None:
    """Execute offline evaluation benchmark against synthetic fixtures."""
    fixture_path = path or (Path("tests") / "fixtures" / "ember-classic-mini")
    if not fixture_path.exists():
        typer.echo(
            json.dumps(
                {"error": f"Fixture path '{fixture_path}' does not exist.", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    if "dashboard" in str(fixture_path).lower():
        benchmark = EvaluationBenchmark.default_angularjs_dashboard(str(fixture_path)).model_copy(
            update={"min_precision": min_precision, "min_recall": min_recall}
        )
    elif "angularjs" in str(fixture_path).lower():
        benchmark = EvaluationBenchmark.default_angularjs_mini(str(fixture_path)).model_copy(
            update={"min_precision": min_precision, "min_recall": min_recall}
        )
    else:
        benchmark = EvaluationBenchmark.default_ember_mini(str(fixture_path)).model_copy(
            update={"min_precision": min_precision, "min_recall": min_recall}
        )

    inventory_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=_create_framework_registry(),
    )
    coordinator = SpecialistCoordinator(FakeAgentRuntime()) if with_specialists else None
    eval_service = EvaluationService(
        inventory_service=inventory_service,
        specialist_coordinator=coordinator,
    )
    if with_specialists:
        result, specialist_metric = eval_service.run_specialist_benchmark(
            benchmark, fixture_path=fixture_path
        )
    else:
        result = eval_service.run_benchmark(benchmark, fixture_path=fixture_path)
        specialist_metric = None

    payload: dict[str, object] = {
        "benchmark_id": result.benchmark_id,
        "detected_components": list(result.detected_components),
        "metrics": {
            "duration_ms": result.metrics.duration_ms,
            "f1_score": result.metrics.f1_score,
            "passed": result.metrics.passed,
            "precision": result.metrics.precision,
            "recall": result.metrics.recall,
            "repair_count": result.metrics.repair_count,
        },
        "missed_components": list(result.missed_components),
        "run_id": result.run_id,
        "status": "ok" if result.metrics.passed else "failed",
        "summary": result.summary,
        "unexpected_components": list(result.unexpected_components),
    }

    if specialist_metric is not None:
        payload["specialist_metrics"] = {
            "baseline_f1": specialist_metric.baseline_f1,
            "cost_usd": specialist_metric.cost_usd,
            "improvement_detected": specialist_metric.improvement_detected,
            "plan_critique_score": specialist_metric.plan_critique_score,
            "specialist_f1": specialist_metric.specialist_f1,
            "turns_used": specialist_metric.turns_used,
        }

    if result.metrics.passed:
        typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    else:
        typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True), err=True)
        raise typer.Exit(code=2)


@app.command("ui")
def ui_command(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target repository path to inspect and manage.",
        ),
    ] = Path("."),
    port: Annotated[
        int,
        typer.Option(
            "--port",
            "-p",
            help="Port to bind on loopback interface (default: 8080).",
        ),
    ] = 8080,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Loopback host address (must be 127.0.0.1 or localhost).",
        ),
    ] = "127.0.0.1",
    open_browser: Annotated[
        bool,
        typer.Option(
            "--open/--no-open",
            help="Automatically open browser to Control Center URL on launch.",
        ),
    ] = True,
    token: Annotated[
        str | None,
        typer.Option(
            "--token",
            help="Predefined session token (cryptographically generated if omitted).",
        ),
    ] = None,
) -> None:
    """Launch the Local Control Center web GUI on loopback (127.0.0.1)."""
    if host not in ("127.0.0.1", "localhost"):
        typer.echo(
            json.dumps(
                {
                    "error": (
                        "Control API must bind strictly to loopback (127.0.0.1). "
                        f"Rejected '{host}'."
                    ),
                    "status": "error",
                },
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    target_root = path.resolve()
    if not target_root.exists() or not target_root.is_dir():
        typer.echo(
            json.dumps(
                {
                    "error": f"Target path '{target_root}' does not exist or is not a directory.",
                    "status": "error",
                },
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2)

    session_token = token if token and len(token) >= 16 else secrets.token_urlsafe(32)

    checkpoint_db = target_root / ".agent" / "checkpoints.db"
    checkpoint_store = SqliteCheckpointStore(checkpoint_db) if checkpoint_db.exists() else None
    governance = GitGovernanceAdapter()
    broadcaster = InMemoryEventBroadcaster()
    discovery_service = FullStackDiscoveryService(
        filesystem=SafeFilesystemInspector(),
        adapters=create_default_domain_adapters(),
    )

    control_service = ControlApiService(
        checkpoint_port=checkpoint_store,
        governance_port=governance,
        event_broadcaster=broadcaster,
        discovery_service=discovery_service,
    )

    server = LoopbackControlServer(
        control_service=control_service,
        target_root=target_root,
        broadcaster=broadcaster,
    )

    try:
        server.start(host=host, port=port, session_token=session_token)
    except OSError as err:
        typer.echo(
            json.dumps(
                {"error": f"Failed to bind port {port}: {err}", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=1) from err

    access_url = f"{server.get_url()}/?token={session_token}"

    info_payload = {
        "access_url": access_url,
        "binding": f"http://{host}:{port}",
        "session_token": session_token,
        "status": "running",
        "target_root": str(target_root),
    }
    typer.echo(json.dumps(info_payload, separators=(",", ":"), sort_keys=True))

    if open_browser:
        with contextlib.suppress(Exception):
            webbrowser.open(access_url)

    try:
        while True:
            time.sleep(0.5)
    except (KeyboardInterrupt, SystemExit):
        server.stop()
        typer.echo(json.dumps({"status": "stopped"}, separators=(",", ":")))


if __name__ == "__main__":
    app()
