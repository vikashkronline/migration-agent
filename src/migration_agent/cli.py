"""Command-line entry point for Migration Agent."""

import json
import os
import sys
import uuid
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated

import typer

from migration_agent.adapters import (
    AnalysisReportWriter,
    AngularAdapter,
    AngularStandaloneComponentRenderer,
    EmberClassicAdapter,
    EmberClassicComponentExtractor,
    FakeAgentRuntime,
    FakeCommandRunner,
    GeminiRuntimeAdapter,
    GitGovernanceAdapter,
    InventoryReportWriter,
    LocalWorkspaceAdapter,
    OpenAIAgentsRuntimeAdapter,
    SafeFilesystemInspector,
    SqliteCheckpointStore,
    SubprocessCommandRunner,
)
from migration_agent.application import (
    AnalysisService,
    BoundedRepairService,
    InventoryService,
    PlanningService,
    ReportService,
    RuleBasedPlanValidator,
    TransformationService,
    ValidationService,
)
from migration_agent.config import Settings
from migration_agent.domain import (
    AnalysisResult,
    ApplyStatus,
    AssuranceLevel,
    ChangeSet,
    PlanStatus,
    ProjectInventory,
    RepairAttempt,
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
                frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
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
                frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
                runtime=runtime,
            )
            _, analysis_result = an_service.analyze(
                path,
                provider=chosen_provider,
                model=chosen_model,
                dry_run=dry_run,
            )

        planning_service = PlanningService(
            runtime=runtime,
            checkpoint_store=checkpoint_store,
            audit_logger=checkpoint_store,
            governance=governance,
            validator=validator,
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
        )

        plan_digest = compute_plan_digest(plan)
        export_path = str(
            Path(target_governance_root) / ".agent" / "plans" / f"{plan.plan_id}.json"
        )

        typer.echo(
            json.dumps(
                {
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

    try:
        approved_plan = service.approve_plan(
            plan_id,
            actor=actor,
            assurance_level=level,
            project_root=str(project_root) if project_root else None,
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
        extractor=EmberClassicComponentExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
        checkpoint_store=checkpoint_store,
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


@app.command("run")
def run_command(
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

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    trans_service = _create_transformation_service(checkpoint_store)

    try:
        staging_dir, initial_changeset = trans_service.stage(
            staging_root=effective_staging_root,
            run_id=run_id,
            source_root=path,
            plan=plan,
        )
    except Exception as err:
        typer.echo(
            json.dumps(
                {"error": f"Staging failed: {err}", "status": "error"},
                separators=(",", ":"),
            ),
            err=True,
        )
        raise typer.Exit(code=2) from err

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

    val_service = ValidationService(command_runner=runner, audit_logger=checkpoint_store)
    val_results = val_service.validate(staging_dir, commands, run_id=run_id)

    repair_attempts: list[RepairAttempt] = []
    latest_changeset = initial_changeset
    step_id = plan.steps[0].step_id if plan.steps else "step-001"

    if any(r.status != ValidationStatus.PASSED for r in val_results) and auto_repair:
        repair_service = BoundedRepairService(
            command_runner=runner,
            workspace_adapter=LocalWorkspaceAdapter(),
            validation_service=val_service,
            audit_logger=checkpoint_store,
            checkpoint_store=checkpoint_store,
            max_budget=max_repairs,
        )
        _, latest_changeset, repair_attempts, val_results = repair_service.run_repair_loop(
            staging_dir=staging_dir,
            initial_changeset=initial_changeset,
            plan=plan,
            step_id=step_id,
            commands=commands,
            initial_results=val_results,
            max_attempts=max_repairs,
        )

    report_service = ReportService(checkpoint_store=checkpoint_store, audit_logger=checkpoint_store)
    report = report_service.compile_report(
        run_id=run_id,
        plan_id=plan.plan_id,
        source_root=str(path),
        staging_root=str(staging_dir),
        validation_results=val_results,
        repair_attempts=repair_attempts,
        applied_changeset=latest_changeset
        if all(r.status == ValidationStatus.PASSED for r in val_results)
        else None,
    )

    report_output_dir = output_dir or (effective_state_dir / "reports")
    json_report_path, md_report_path = report_service.save_report(
        report, output_dir=report_output_dir
    )

    summary_payload = {
        "json_report_path": str(json_report_path),
        "md_report_path": str(md_report_path),
        "plan_id": plan.plan_id,
        "repair_attempts_count": len(report.repair_attempts),
        "run_id": run_id,
        "staging_path": str(staging_dir),
        "status": report.status.value,
        "validation_checks_count": len(report.validation_results),
    }

    if report.status == RunStatus.SUCCESS:
        typer.echo(json.dumps(summary_payload, separators=(",", ":"), sort_keys=True))
    else:
        typer.echo(json.dumps(summary_payload, separators=(",", ":"), sort_keys=True), err=True)
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
