"""Command-line entry point for Migration Agent."""

import contextlib
import getpass
import json
import os
import secrets
import sys
import time
import uuid
import webbrowser
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
    FoundationTransformationAdapter,
    FullStackReportWriter,
    GitGovernanceAdapter,
    GitKnowledgeAdapter,
    InMemoryEventBroadcaster,
    InventoryReportWriter,
    LocalTrustStoreAdapter,
    LocalWorkspaceAdapter,
    LoopbackControlServer,
    SafeFilesystemInspector,
    SqliteCheckpointStore,
    SubprocessCommandRunner,
    create_default_domain_adapters,
)
from migration_agent.adapters.access_cli import register_access_cli
from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.cli_access import secure_cli
from migration_agent.adapters.configuration_cli import register_configuration_cli
from migration_agent.adapters.mcp.setup import register_setup_cli
from migration_agent.adapters.workbench import CanonicalWorkbench
from migration_agent.adapters.workflow_cli import register_workflow_cli
from migration_agent.application import (
    AnalysisService,
    BoundedRepairService,
    ContextualQAService,
    ControlApiService,
    EvaluationService,
    FullStackDiscoveryService,
    InventoryService,
    KnowledgeService,
    MigrationPipelineService,
    PlanningService,
    ProjectAdoptionService,
    ReportService,
    ResumableExecutionService,
    RuleBasedPlanValidator,
    SpecialistCoordinator,
    TransformationService,
    ValidationService,
    collect_diagnostics,
)
from migration_agent.application.workbench import WorkbenchService
from migration_agent.config import Settings
from migration_agent.domain import (
    AnalysisResult,
    AssuranceLevel,
    EvaluationBenchmark,
    MigrationPlan,
    PlanStatus,
    ProjectInventory,
    RunStatus,
    ValidationCommand,
    ValidationProfile,
    ValidationStatus,
    compute_plan_digest,
    verify_approval,
)
from migration_agent.domain.inspection_access import InspectionContext
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.workflow_access import WorkflowContext
from migration_agent.packaging import (
    cloak_prompt_string,
    decloak_prompt_string,
    generate_release_manifest,
    get_binary_packaging_spec,
    load_release_manifest,
    save_release_manifest,
    verify_release_manifest,
    write_pyinstaller_spec_file,
)
from migration_agent.ports import (
    AgentRuntimePort,
    CommandRunnerPort,
    FrameworkAdapterRegistry,
    InspectionPolicy,
    SpecialistRuntimePort,
)
from migration_agent.ports.apply_approval import StagedWorkflowPort

app = typer.Typer(
    name="agent",
    help="Controlled code migration workbench (canonical: agent, alias: migration-agent).",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
register_access_cli(app)
register_configuration_cli(app)

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

challenge_app = typer.Typer(
    help="Record and inspect diagnostic challenges and migration hurdles.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(challenge_app, name="challenge")

solution_app = typer.Typer(
    help="Propose and inspect candidate solutions.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(solution_app, name="solution")

learning_app = typer.Typer(
    help="Approve and inspect curated project learnings (ADR-3, Invariant 16).",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(learning_app, name="learning")

decision_app = typer.Typer(
    help="Record and inspect Architectural Decision Records (ADRs).",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(decision_app, name="decision")

package_app = typer.Typer(
    help="Distribution packaging, release manifest generation, and binary verification.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(package_app, name="package")

mcp_app = typer.Typer(
    help="Model Context Protocol (MCP) server for ambient coding agents.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(mcp_app, name="mcp")


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
    ] = 5_000_000,
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
    source_root: Path | None = None,
) -> tuple[AgentRuntimePort, str, str]:
    configuration_facade = None
    requested_provider = (provider or settings.runtime_provider or "gemini").strip().lower()
    if requested_provider not in {"gemini", "openai", "fake"}:
        raise ValueError(
            "Unsupported runtime provider. Supported providers: 'gemini', 'openai', 'fake'."
        )
    offline = (
        fake_runtime
        or os.getenv("MIGRATION_AGENT_FAKE_RUNTIME") == "1"
        or requested_provider == "fake"
    )
    if source_root is not None and not offline:
        from migration_agent.adapters.configuration_runtime import ConfigurationFacade

        updates: dict[str, object] = {}
        if provider:
            updates["runtime_provider"] = provider
        if model:
            updates["runtime_model"] = model
        settings = settings.model_copy(update=updates)
        configuration_facade = ConfigurationFacade(
            ProjectAuthorization(source_root, settings), settings
        )
        settings = configuration_facade.runtime_settings(model_operation=True)
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
        from migration_agent.adapters.gemini import GeminiRuntimeAdapter

        runtime = GeminiRuntimeAdapter()
    elif chosen_provider == "openai":
        from migration_agent.adapters.agents import OpenAIAgentsRuntimeAdapter

        runtime = OpenAIAgentsRuntimeAdapter()
    else:
        runtime = FakeAgentRuntime()

    if configuration_facade is not None:
        from typer._click.globals import get_current_context

        from migration_agent.adapters.configuration_agent_runtime import (
            ConfigurationAgentRuntime,
            ConfigurationSpecialistRuntime,
        )

        context = get_current_context(silent=True)
        turn_override = None
        if context is not None:
            parameter_source = context.get_parameter_source("max_turns")
            if parameter_source is not None and parameter_source.name != "DEFAULT":
                turn_override = context.params.get("max_turns")
        wrapper = (
            ConfigurationSpecialistRuntime
            if isinstance(runtime, SpecialistRuntimePort)
            else ConfigurationAgentRuntime
        )
        runtime = wrapper(runtime, configuration_facade, turn_override)
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
    ] = 5_000_000,
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
            provider, model, fake_runtime, settings, path
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
            provider, model, fake_runtime, settings, path
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
            knowledge=GitKnowledgeAdapter(),
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
        foundation_adapter=FoundationTransformationAdapter(),
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


def _create_pipeline_service(
    checkpoint_store: SqliteCheckpointStore,
    runner: CommandRunnerPort,
    governance: GitGovernanceAdapter,
    settings: Settings,
    max_repairs: int = 3,
    workflow: StagedWorkflowPort | None = None,
    source_root: Path | None = None,
) -> MigrationPipelineService:
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
    runtime, provider, model = _resolve_runtime(
        None, None, isinstance(runner, FakeCommandRunner), settings, source_root
    )
    repair_service.specialist_runtime = (
        runtime if isinstance(runtime, SpecialistRuntimePort) else None
    )
    inv_service = InventoryService(
        filesystem=SafeFilesystemInspector(),
        frameworks=_create_framework_registry(),
    )
    analysis_service = AnalysisService(
        filesystem=SafeFilesystemInspector(),
        frameworks=_create_framework_registry(),
        runtime=runtime,
    )
    planning_service = PlanningService(
        runtime=runtime,
        checkpoint_store=checkpoint_store,
        audit_logger=checkpoint_store,
        governance=governance,
        validator=RuleBasedPlanValidator(max_step_files=settings.max_step_files),
        knowledge=GitKnowledgeAdapter(),
    )
    return MigrationPipelineService(
        checkpoint_store=checkpoint_store,
        transformation_service=trans_service,
        validation_service=val_service,
        repair_service=repair_service,
        report_service=report_service,
        planning_service=planning_service,
        governance=governance,
        inventory_service=inv_service,
        analysis_service=analysis_service,
        audit_logger=checkpoint_store,
        workflow=workflow,
        runtime_provider=provider,
        runtime_model=model,
        runtime_dry_run=isinstance(runtime, FakeAgentRuntime),
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
    from migration_agent.adapters.workflow_cli import emit_error, stage_cli

    try:
        stage_cli(path, plan_id, step_id, state_dir, staging_root)
    except (ValueError, OSError) as error:
        emit_error(error)
        raise typer.Exit(2) from error
    return


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
    staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
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
    from migration_agent.adapters.workflow_cli import apply_cli, emit_error

    try:
        apply_cli(path, plan_id, changeset_id, state_dir, staging_root)
    except (ValueError, OSError) as error:
        emit_error(error)
        raise typer.Exit(2) from error
    return


@app.command("migrate")
def migrate_command(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
            help="Target repository path to migrate.",
        ),
    ],
    step: Annotated[
        str | None,
        typer.Option(
            "--step",
            "-s",
            help="Optional specific step ID within the migration plan.",
        ),
    ] = None,
    plan_id: Annotated[
        str | None,
        typer.Option(
            "--plan",
            "-p",
            help="Optional existing migration plan ID to execute.",
        ),
    ] = None,
    auto_approve: Annotated[
        bool,
        typer.Option(
            "--auto-approve",
            help="Automatically approve the migration plan (Mode B) without prompting.",
        ),
    ] = False,
    skip_validation: Annotated[
        bool,
        typer.Option(
            "--skip-validation",
            help="Skip compiler and test validation gates.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Generate preview changes and diff summary without modifying files.",
        ),
    ] = False,
    allow_dirty: Annotated[
        bool,
        typer.Option(
            "--allow-dirty",
            help="Allow migration on working trees with uncommitted changes (Invariant 25).",
        ),
    ] = False,
    actor: Annotated[
        str,
        typer.Option(
            "--actor",
            "-a",
            help="Actor executing the migration.",
        ),
    ] = "operator",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            file_okay=False,
            help="Directory to save run reports and audit artifacts.",
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
    max_repairs: Annotated[
        int,
        typer.Option(
            "--max-repairs",
            help="Maximum repair attempts budget.",
        ),
    ] = 3,
) -> None:
    """Execute end-to-end unified migration pipeline with approval and self-repair."""
    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    effective_staging_root = settings.resolve_staging_root(staging_root)
    checkpoint_store = SqliteCheckpointStore(effective_state_dir)
    governance = GitGovernanceAdapter()

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

    from migration_agent.adapters.workflow_cli import runtime_for

    workflow_runtime = (
        None
        if fake_runner or dry_run
        else runtime_for(path, effective_state_dir, effective_staging_root)
    )
    pipeline_service = _create_pipeline_service(
        checkpoint_store=checkpoint_store,
        runner=runner,
        governance=governance,
        settings=settings,
        max_repairs=max_repairs,
        workflow=workflow_runtime,
        source_root=path,
    )

    def interactive_confirm(plan: MigrationPlan) -> bool:
        if not sys.stdin.isatty():
            return False
        typer.echo(f"\nMigration Plan '{plan.plan_id}' generated:")
        typer.echo(f"- Steps count: {len(plan.steps)}")
        for s in plan.steps:
            typer.echo(f"  * [{s.step_id}] {s.title} (Risk: {s.risk.value})")
        return typer.confirm("\nApprove plan and execute migration?", default=True)

    report_output_dir = output or (effective_state_dir / "reports")

    try:
        result = pipeline_service.migrate(
            project_path=path,
            step_id=step,
            plan_id=plan_id,
            auto_approve=auto_approve,
            skip_validation=skip_validation,
            dry_run=dry_run,
            allow_dirty=allow_dirty,
            staging_root=effective_staging_root,
            output_dir=report_output_dir,
            actor=actor,
            confirm_callback=interactive_confirm if not auto_approve else None,
        )
    except Exception as err:
        typer.echo(
            json.dumps({"error": str(err), "status": "error"}, separators=(",", ":")),
            err=True,
        )
        raise typer.Exit(code=2) from err
    finally:
        if workflow_runtime:
            workflow_runtime.close()

    payload: dict[str, object] = {
        "applied_paths": list(result.applied_paths),
        "changeset_digest": result.changeset_digest,
        "changeset_id": result.changeset_id,
        "diagnostics": list(result.diagnostics),
        "dry_run": result.dry_run,
        "json_report_path": result.json_report_path,
        "md_report_path": result.md_report_path,
        "plan_id": result.plan_id,
        "repair_attempts_count": result.repair_attempts_count,
        "run_id": result.run_id,
        "status": result.status,
        "step_id": result.step_id,
        "validation_checks_count": result.validation_checks_count,
        "validation_status": result.validation_status,
    }
    if result.backup_snapshot_path:
        payload["backup_snapshot_path"] = result.backup_snapshot_path

    if result.status in ("ok", "dry_run", "approval_required"):
        typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    elif result.status == "aborted":
        typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True), err=True)
        raise typer.Exit(code=1)
    else:
        typer.echo(json.dumps(payload, separators=(",", ":"), sort_keys=True), err=True)
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
    step_id: Annotated[str | None, typer.Option("--step")] = None,
    staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
) -> None:
    """Run allowlisted validation checks against a staging workspace."""
    if not fake_runner and (plan_id is None or step_id is None):
        from migration_agent.adapters.workflow_cli import emit_error

        emit_error(
            ValueError(
                "STAGED_WORKFLOW_REQUIRED: live validation requires --plan and "
                "--step with persisted staging."
            )
        )
        raise typer.Exit(2)
    if plan_id is not None and step_id is not None:
        from migration_agent.adapters.workflow_cli import emit_error, runtime_for

        try:
            if fake_runner:
                raise ValueError("TEST_RUNNER_REJECTED: fake checks cannot mint apply provenance.")
            runtime = runtime_for(path, state_dir, staging_root)
            try:
                record = runtime.store.get_workflow(runtime.binding.project_id, plan_id, step_id)
                if (
                    staging_dir
                    and staging_dir.resolve() != Path(record.staging_path or "").resolve()
                ):
                    raise ValueError("STAGING_PATH_INVALID: select the persisted step workspace.")
                operation = runtime.dispatch(
                    "validate",
                    plan_id,
                    step_id,
                    f"cli-{uuid.uuid4().hex}",
                    profile=profile.upper(),
                    background=False,
                )
                typer.echo(operation.model_dump_json())
                if operation.status.value != "SUCCEEDED":
                    raise typer.Exit(2)
            finally:
                runtime.close()
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        return
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
    if not fake_runner:
        from migration_agent.adapters.workflow_cli import emit_error

        emit_error(
            ValueError(
                "STAGED_WORKFLOW_REQUIRED: legacy run reports support "
                "--fake-runner only; use agent stage, validate and validation "
                "repair for live execution."
            )
        )
        raise typer.Exit(2)
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
    if not fake_runner:
        from migration_agent.adapters.workflow_cli import emit_error

        emit_error(
            ValueError(
                "STAGED_WORKFLOW_REQUIRED: legacy run resume supports "
                "--fake-runner reports only; resume live validation with "
                "agent validation repair."
            )
        )
        raise typer.Exit(2)
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
    semantic: Annotated[
        bool,
        typer.Option(
            "--semantic",
            help="Include compilation, spec pass rate, and control flow fidelity evaluation.",
        ),
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
    trans_service = (
        TransformationService(
            workspace_adapter=LocalWorkspaceAdapter(),
            registry=_create_framework_registry(),
            filesystem=SafeFilesystemInspector(),
        )
        if semantic
        else None
    )
    eval_service = EvaluationService(
        inventory_service=inventory_service,
        specialist_coordinator=coordinator,
        transformation_service=trans_service,
    )
    if with_specialists:
        result, specialist_metric = eval_service.run_specialist_benchmark(
            benchmark, fixture_path=fixture_path, semantic=semantic
        )
    else:
        result = eval_service.run_benchmark(benchmark, fixture_path=fixture_path, semantic=semantic)
        specialist_metric = None

    metrics_dict: dict[str, object] = {
        "duration_ms": result.metrics.duration_ms,
        "f1_score": result.metrics.f1_score,
        "passed": result.metrics.passed,
        "precision": result.metrics.precision,
        "recall": result.metrics.recall,
        "repair_count": result.metrics.repair_count,
    }
    if result.metrics.compilation_pass_rate is not None:
        metrics_dict["compilation_pass_rate"] = result.metrics.compilation_pass_rate
    if result.metrics.spec_pass_rate is not None:
        metrics_dict["spec_pass_rate"] = result.metrics.spec_pass_rate
    if result.metrics.control_flow_fidelity is not None:
        metrics_dict["control_flow_fidelity"] = result.metrics.control_flow_fidelity

    payload: dict[str, object] = {
        "benchmark_id": result.benchmark_id,
        "detected_components": list(result.detected_components),
        "metrics": metrics_dict,
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
            help="Read-only source repository bound to external governance.",
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
    state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
    staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    trust_root: Annotated[Path | None, typer.Option("--trust-root")] = None,
    local_config_root: Annotated[Path | None, typer.Option("--local-config-root")] = None,
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

    settings = Settings()
    updates: dict[str, object] = {}
    if state_dir is not None:
        updates["state_dir"] = state_dir
    if staging_root is not None:
        updates["staging_root"] = staging_root
    if trust_root is not None:
        updates["trust_root"] = trust_root
    if local_config_root is not None:
        updates["local_config_root"] = local_config_root
    settings = settings.model_copy(update=updates)
    effective_staging_root = settings.resolve_staging_root(staging_root)
    effective_state_dir = settings.resolve_state_dir(state_dir)
    context = InspectionContext(
        actor=getpass.getuser(),
        assurance=AssuranceLevel.MODE_B
        if settings.mcp_trusted_local_reads
        else AssuranceLevel.MODE_C,
        capabilities=settings.mcp_read_capabilities,
    )
    try:
        source = CanonicalWorkbench(
            target_root,
            settings,
            WorkflowContext(
                actor=context.actor,
                assurance=context.assurance,
                capabilities=settings.mcp_workflow_capabilities,
            ),
        )
    except (ValueError, OSError) as error:
        typer.echo(
            json.dumps({"status": "error", "error": RedactionPolicy().redact_text(str(error))}),
            err=True,
        )
        raise typer.Exit(2) from error
    workbench = WorkbenchService(source, context)
    broadcaster = InMemoryEventBroadcaster()
    control_service = ControlApiService(event_broadcaster=broadcaster)

    server = LoopbackControlServer(
        control_service=control_service,
        target_root=target_root,
        broadcaster=broadcaster,
        workbench=workbench,
        authorization=source.authorization,
        staging_root=effective_staging_root,
        state_dir=effective_state_dir,
        settings=settings,
        actor=context.actor,
    )

    try:
        server.start(host=host, port=port, session_token=session_token)
    except OSError as err:
        source.close()
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
        "access_url": server.get_url(),
        "binding": f"http://{host}:{port}",
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
        source.close()
        typer.echo(json.dumps({"status": "stopped"}, separators=(",", ":")))


# ============================================================================
# Phase 12 Commands: Project Lifecycle, Knowledge Engine & Contextual Q&A
# ============================================================================


@app.command("init")
def init_project(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target project directory to initialize.",
        ),
    ] = Path("."),
    project_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Custom project identifier.",
        ),
    ] = None,
    source: Annotated[
        Path | None,
        typer.Option("--source", help="Read-only source for a separate migration project."),
    ] = None,
    staging_root: Annotated[
        Path | None, typer.Option("--staging-root", help="External isolated staging root.")
    ] = None,
    state_dir: Annotated[
        Path | None, typer.Option("--state-dir", help="External operational state directory.")
    ] = None,
) -> None:
    """Scenario A: Initialize a new project with Git-native .agent/ governance layout."""
    governance = GitGovernanceAdapter()
    inspector = SafeFilesystemInspector()
    registry = _create_framework_registry()
    inv_svc = InventoryService(inspector, registry)
    fullstack_svc = FullStackDiscoveryService(inspector, create_default_domain_adapters())
    adoption_svc = ProjectAdoptionService(governance, inv_svc, fullstack_svc)

    session = None
    try:
        if source is not None:
            settings = Settings()
            manifest, session = adoption_svc.init_migration(
                path,
                source,
                settings.resolve_staging_root(staging_root),
                settings.resolve_state_dir(state_dir),
                project_id,
            )
        else:
            if staging_root is not None or state_dir is not None:
                raise ValueError("MISSING_SOURCE: --staging-root/--state-dir require --source.")
            manifest = adoption_svc.init(path, project_id=project_id)
    except (ValueError, OSError) as err:
        typer.echo(json.dumps({"status": "blocked", "error": str(err)}), err=True)
        raise typer.Exit(code=1) from err
    typer.echo(
        json.dumps(
            {
                "status": "initialized",
                "project_id": manifest.project_id,
                "platform_version": manifest.platform_version,
                "path": str(path.resolve()),
                **(
                    {
                        "migration_session": session.model_dump(mode="json"),
                        "next_steps": [
                            "Record decisions in the external project directory before planning.",
                            "Inventory/analyze the source; plan with --output set to this project.",
                            "Pass the recorded state/staging roots to workflow commands.",
                            "Source apply is outside this read-only session's scope.",
                        ],
                    }
                    if session is not None
                    else {}
                ),
            },
            indent=2,
        )
    )


@app.command("adopt")
def adopt_project(
    path: Annotated[
        Path,
        typer.Argument(
            help="Target repository directory to adopt.",
        ),
    ] = Path("."),
    allow_dirty: Annotated[
        bool,
        typer.Option(
            "--allow-dirty",
            help="Allow adoption on a Git repository with uncommitted changes.",
        ),
    ] = False,
    docs_dir: Annotated[
        Path | None,
        typer.Option(
            "--docs-dir",
            help="Directory to write architecture documentation (default: docs/architecture).",
        ),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option(
            "--id",
            help="Custom project identifier.",
        ),
    ] = None,
) -> None:
    """Scenario B: Adopt an existing repository into the platform with read-only inspection."""
    governance = GitGovernanceAdapter()
    inspector = SafeFilesystemInspector()
    registry = _create_framework_registry()
    inv_svc = InventoryService(inspector, registry)
    fullstack_svc = FullStackDiscoveryService(inspector, create_default_domain_adapters())
    adoption_svc = ProjectAdoptionService(governance, inv_svc, fullstack_svc)

    try:
        report = adoption_svc.adopt(
            path,
            allow_dirty=allow_dirty,
            docs_dir=docs_dir,
            project_id=project_id,
        )
    except RuntimeError as err:
        typer.echo(json.dumps({"error": str(err), "status": "dirty_worktree"}, indent=2), err=True)
        raise typer.Exit(code=1) from err

    typer.echo(
        json.dumps(
            {
                "status": "adopted",
                "project_id": report.project_id,
                "target_path": report.target_path,
                "eligible_files": report.eligible_files_count,
                "frameworks": list(report.detected_frameworks),
                "cross_domain_nodes": report.cross_domain_nodes_count,
                "docs_directory": report.docs_directory,
            },
            indent=2,
        )
    )


@challenge_app.command("record")
def record_challenge_command(
    title: Annotated[str, typer.Option("--title", "-t", help="Challenge title.")],
    description: Annotated[str, typer.Option("--desc", "-d", help="Detailed description.")],
    path: Annotated[Path, typer.Argument(help="Target project directory.")] = Path("."),
    category: Annotated[str, typer.Option("--category", "-c", help="Category.")] = "GENERAL",
    diagnostics: Annotated[
        list[str] | None, typer.Option("--diag", help="Diagnostic citation.")
    ] = None,
    challenge_id: Annotated[str | None, typer.Option("--id", help="Explicit challenge ID.")] = None,
) -> None:
    """Record a diagnostic hurdle or migration challenge in .agent/challenges/."""
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)
    record = service.record_challenge(
        str(path.resolve()),
        title=title,
        description=description,
        category=category,
        diagnostic_citations=tuple(diagnostics or ()),
        challenge_id=challenge_id,
    )
    typer.echo(
        json.dumps(
            {
                "status": "recorded",
                "challenge_id": record.challenge_id,
                "title": record.title,
                "category": record.category,
            },
            indent=2,
        )
    )


@challenge_app.command("list")
def list_challenges_command(
    path: Annotated[Path, typer.Argument(help="Target project directory.")] = Path("."),
) -> None:
    """List recorded migration challenges from .agent/challenges/."""
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)
    challenges = service.list_challenges(str(path.resolve()))
    typer.echo(
        json.dumps(
            [c.model_dump(mode="json") for c in challenges],
            indent=2,
        )
    )


@solution_app.command("record")
def record_solution_command(
    challenge_id: Annotated[str, typer.Option("--challenge", "-c", help="Target challenge ID.")],
    approach: Annotated[str, typer.Option("--approach", "-a", help="Proposed solution approach.")],
    path: Annotated[Path, typer.Argument(help="Target project directory.")] = Path("."),
    changeset: Annotated[
        str | None, typer.Option("--changeset", help="Optional ChangeSet ID reference.")
    ] = None,
    run_id: Annotated[
        str | None, typer.Option("--run-id", help="Optional verifying Run ID.")
    ] = None,
    solution_id: Annotated[str | None, typer.Option("--id", help="Explicit solution ID.")] = None,
) -> None:
    """Propose and record a candidate solution for a known challenge."""
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)
    try:
        solution = service.propose_solution(
            str(path.resolve()),
            challenge_id=challenge_id,
            proposed_approach=approach,
            changeset_ref=changeset,
            verified_by_run_id=run_id,
            solution_id=solution_id,
        )
    except ValueError as err:
        typer.echo(json.dumps({"error": str(err), "status": "error"}, indent=2), err=True)
        raise typer.Exit(code=1) from err

    typer.echo(
        json.dumps(
            {
                "status": "proposed",
                "solution_id": solution.solution_id,
                "challenge_id": solution.challenge_id,
                "approach": solution.proposed_approach,
            },
            indent=2,
        )
    )


@solution_app.command("list")
def list_solutions_command(
    path: Annotated[Path, typer.Argument(help="Target project directory.")] = Path("."),
) -> None:
    """List proposed candidate solutions from .agent/solutions/."""
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)
    solutions = service.list_solutions(str(path.resolve()))
    typer.echo(
        json.dumps(
            [s.model_dump(mode="json") for s in solutions],
            indent=2,
        )
    )


@learning_app.command("approve")
def approve_learning_command(
    solution_id: Annotated[str, typer.Option("--solution", "-s", help="Candidate solution ID.")],
    approver: Annotated[
        str, typer.Option("--approver", help="Human approver identifier (Invariant 16).")
    ],
    title: Annotated[str, typer.Option("--title", "-t", help="Title of curated learning.")],
    findings: Annotated[str, typer.Option("--findings", help="Core diagnostic findings.")],
    pattern: Annotated[str, typer.Option("--pattern", help="Recommended pattern.")],
    path: Annotated[Path, typer.Argument(help="Target project directory.")] = Path("."),
    anti_patterns: Annotated[
        list[str] | None, typer.Option("--anti-pattern", help="Anti-patterns to avoid.")
    ] = None,
    tags: Annotated[
        list[str] | None, typer.Option("--tag", help="Tags for categorization.")
    ] = None,
    learning_id: Annotated[str | None, typer.Option("--id", help="Explicit learning ID.")] = None,
) -> None:
    """Promote a candidate solution to a curated learning with human approval (Invariant 16)."""
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)
    try:
        learning = service.approve_learning(
            str(path.resolve()),
            solution_id=solution_id,
            approved_by=approver,
            title=title,
            findings=findings,
            recommended_pattern=pattern,
            anti_patterns=tuple(anti_patterns or ()),
            tags=tuple(tags or ()),
            learning_id=learning_id,
        )
    except ValueError as err:
        typer.echo(json.dumps({"error": str(err), "status": "error"}, indent=2), err=True)
        raise typer.Exit(code=1) from err

    typer.echo(
        json.dumps(
            {
                "status": "approved",
                "learning_id": learning.learning_id,
                "title": learning.title,
                "approved_by": learning.approved_by,
            },
            indent=2,
        )
    )


@learning_app.command("list")
def list_learnings_command(
    path: Annotated[Path, typer.Argument(help="Target project directory.")] = Path("."),
) -> None:
    """List human-approved curated project learnings from .agent/learnings/."""
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)
    learnings = service.list_learnings(str(path.resolve()))
    typer.echo(
        json.dumps(
            [lrn.model_dump(mode="json") for lrn in learnings],
            indent=2,
        )
    )


@decision_app.command("record")
def record_decision_command(
    decision_id: Annotated[str, typer.Option("--id", help="ADR identifier (e.g. ADR-001).")],
    title: Annotated[str, typer.Option("--title", "-t", help="ADR title.")],
    context: Annotated[str, typer.Option("--context", help="Context and problem statement.")],
    decision: Annotated[str, typer.Option("--decision", help="Decision statement.")],
    consequences: Annotated[str, typer.Option("--consequences", help="Expected consequences.")],
    by: Annotated[str, typer.Option("--by", help="Author/decided_by identifier.")],
    path: Annotated[Path, typer.Argument(help="Target project directory.")] = Path("."),
) -> None:
    """Record an Architectural Decision Record (ADR) in .agent/decisions/."""
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)
    try:
        adr = service.record_decision(
            str(path.resolve()),
            decision_id=decision_id,
            title=title,
            context=context,
            decision=decision,
            consequences=consequences,
            decided_by=by,
        )
    except ValueError as err:
        typer.echo(json.dumps({"error": str(err), "status": "error"}, indent=2), err=True)
        raise typer.Exit(code=1) from err

    typer.echo(
        json.dumps(
            {
                "status": "recorded",
                "decision_id": adr.decision_id,
                "title": adr.title,
                "decided_by": adr.decided_by,
            },
            indent=2,
        )
    )


@decision_app.command("list")
def list_decisions_command(
    path: Annotated[Path, typer.Argument(help="Target project directory.")] = Path("."),
) -> None:
    """List Architectural Decision Records from .agent/decisions/."""
    adapter = GitKnowledgeAdapter()
    service = KnowledgeService(adapter)
    decisions = service.list_decisions(str(path.resolve()))
    typer.echo(
        json.dumps(
            [d.model_dump(mode="json") for d in decisions],
            indent=2,
        )
    )


@app.command("ask")
def ask_question(
    query: Annotated[str, typer.Argument(help="Technical question to ask.")],
    path: Annotated[
        Path,
        typer.Option("--path", "-p", help="Target project root directory."),
    ] = Path("."),
    entity: Annotated[
        str | None,
        typer.Option("--entity", "-e", help="Selected component or entity."),
    ] = None,
    artifact: Annotated[
        str | None,
        typer.Option("--artifact", help="Selected artifact path."),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", help="Active run ID context."),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Model runtime provider (gemini, openai, fake)."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model name."),
    ] = None,
    fake_runtime: Annotated[
        bool,
        typer.Option("--fake-runtime", help="Use deterministic fake runtime."),
    ] = False,
) -> None:
    """Ask a contextual question bounded by project inventory, ADRs, and curated learnings."""
    settings = Settings()
    runtime, chosen_provider, chosen_model = _resolve_runtime(
        provider, model, fake_runtime, settings, path
    )
    knowledge_adapter = GitKnowledgeAdapter()
    governance = GitGovernanceAdapter()
    inspector = SafeFilesystemInspector()
    registry = _create_framework_registry()
    inventory_svc = InventoryService(inspector, registry)

    qa_service = ContextualQAService(
        runtime=runtime,
        knowledge_port=knowledge_adapter,
        governance_port=governance,
        inventory_service=inventory_svc,
    )

    try:
        answer = qa_service.ask(
            str(path.resolve()),
            query,
            selected_entity=entity,
            selected_artifact=artifact,
            current_run_id=run_id,
            provider=chosen_provider,
            model=chosen_model,
        )
    except Exception as err:
        typer.echo(json.dumps({"error": str(err), "status": "error"}, indent=2), err=True)
        raise typer.Exit(code=1) from err

    typer.echo(json.dumps(answer.model_dump(mode="json"), indent=2))


@package_app.command("spec")
def package_spec_command(
    package_root: Annotated[
        Path,
        typer.Option("--package-root", help="Path to project root directory."),
    ] = Path("."),
    binary_name: Annotated[
        str,
        typer.Option("--binary-name", help="Primary binary executable name."),
    ] = "agent",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Target file path to write PyInstaller .spec file."),
    ] = None,
    write: Annotated[
        bool,
        typer.Option("--write", help="Whether to write .spec file to disk."),
    ] = False,
) -> None:
    """Generate or write PyInstaller specification for standalone binary bundling."""
    if write or output is not None:
        target = write_pyinstaller_spec_file(
            package_root, output_file=output, binary_name=binary_name
        )
        typer.echo(json.dumps({"status": "written", "spec_path": str(target.resolve())}, indent=2))
    else:
        spec_dict = get_binary_packaging_spec(package_root, binary_name=binary_name)
        typer.echo(json.dumps(spec_dict, indent=2))


@package_app.command("manifest")
def package_manifest_command(
    dist_dir: Annotated[
        Path,
        typer.Option("--dist-dir", help="Path to dist directory containing build assets."),
    ] = Path("dist"),
    version: Annotated[
        str,
        typer.Option("--version", "-v", help="Release version string."),
    ] = "0.1.0",
    channel: Annotated[
        str,
        typer.Option("--channel", help="Release channel (e.g. stable, beta)."),
    ] = "stable",
    canonical_cli: Annotated[
        str,
        typer.Option("--canonical-cli", help="Canonical CLI executable name."),
    ] = "agent",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Path to write release-manifest.json."),
    ] = None,
    key_id: Annotated[
        str | None,
        typer.Option("--key-id", help="Authority key ID for cryptographic signing."),
    ] = None,
    private_key: Annotated[
        str | None,
        typer.Option("--private-key", help="Private key secret for cryptographic signing."),
    ] = None,
) -> None:
    """Generate cryptographically bound release-manifest.json for distribution assets."""
    manifest = generate_release_manifest(
        version=version,
        dist_dir=dist_dir,
        release_channel=channel,
        canonical_cli=canonical_cli,
        signing_key=private_key,
        key_id=key_id,
    )
    if output is not None:
        target = save_release_manifest(manifest, output)
        typer.echo(
            json.dumps(
                {
                    "status": "written",
                    "manifest_path": str(target.resolve()),
                    "digest": manifest.manifest_digest,
                },
                indent=2,
            )
        )
    else:
        typer.echo(manifest.model_dump_json(indent=2))


@package_app.command("verify")
def package_verify_command(
    dist_dir: Annotated[
        Path,
        typer.Option("--dist-dir", help="Path to dist directory."),
    ] = Path("dist"),
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest", "-m", help="Path to release-manifest.json."),
    ] = Path("dist/release-manifest.json"),
) -> None:
    """Verify all published distribution assets against release-manifest.json."""
    if not manifest_path.is_file():
        reason_text = f"Manifest not found: {manifest_path}"
        typer.echo(
            json.dumps({"valid": False, "reason": reason_text}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        manifest = load_release_manifest(manifest_path)
    except Exception as err:
        typer.echo(
            json.dumps({"valid": False, "reason": f"Failed to parse manifest: {err}"}, indent=2),
            err=True,
        )
        raise typer.Exit(code=1) from err

    valid = verify_release_manifest(manifest, dist_dir)
    res = {
        "valid": valid,
        "version": manifest.version,
        "assets_checked": len(manifest.assets),
        "manifest_digest": manifest.manifest_digest,
        "signed": manifest.signature is not None,
    }
    typer.echo(json.dumps(res, indent=2))
    if not valid:
        raise typer.Exit(code=1)


@package_app.command("cloak")
def package_cloak_command(
    prompt: Annotated[
        str,
        typer.Argument(help="Sensitive prompt or heuristic string to mask."),
    ],
) -> None:
    """Mask a sensitive prompt or heuristic string for binary packaging."""
    cloaked = cloak_prompt_string(prompt)
    typer.echo(cloaked)


@package_app.command("decloak")
def package_decloak_command(
    cloaked: Annotated[
        str,
        typer.Argument(help="Cloaked base64 string to unmask."),
    ],
) -> None:
    """Unmask a cloaked prompt or heuristic string at runtime."""
    decloaked = decloak_prompt_string(cloaked)
    typer.echo(decloaked)


@mcp_app.command("serve")
def mcp_serve_command(
    project_root: Annotated[
        Path,
        typer.Option(
            "--project-root",
            "-r",
            help="Target repository root to bind and expose over MCP.",
        ),
    ] = Path("."),
    state_dir: Annotated[
        Path | None,
        typer.Option(
            "--state-dir",
            help="Custom directory for SQLite checkpoints and audit log.",
        ),
    ] = None,
) -> None:
    """Run the MCP server over stdio for ambient coding agents."""
    from migration_agent.adapters.mcp import run_mcp_server

    resolved_root = project_root.resolve()
    if not resolved_root.exists():
        sys.stderr.write(f"Error: Project root does not exist: {resolved_root}\n")
        raise typer.Exit(code=1)
    if not resolved_root.is_dir():
        sys.stderr.write(f"Error: Project root is not a directory: {resolved_root}\n")
        raise typer.Exit(code=1)

    settings = Settings()
    effective_state_dir = settings.resolve_state_dir(state_dir)
    run_mcp_server(
        project_root=resolved_root,
        state_dir=effective_state_dir,
        settings=settings,
    )


register_workflow_cli(app)
register_setup_cli(mcp_app)
secure_cli(app)

if __name__ == "__main__":
    app()
