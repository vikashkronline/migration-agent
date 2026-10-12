"""MCP server adapter with process-wide stream isolation and root binding."""

from __future__ import annotations

import getpass
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp_types import INVALID_PARAMS, CallToolResult, TextContent
from pydantic import BaseModel, ValidationError

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.adapters.configuration_checks import ConfigurationChecks
from migration_agent.adapters.configuration_runtime import ConfigurationFacade
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.mcp.host_tools import register_host_tools
from migration_agent.adapters.mcp.models import (
    DoctorResult,
    InventoryResult,
    PlanShowResult,
    RunStatusResult,
    StepPreviewResult,
)
from migration_agent.adapters.mcp.tools import (
    handle_doctor,
    handle_inventory,
    handle_plan_show,
    handle_run_status,
    handle_step_preview,
)
from migration_agent.config import Settings
from migration_agent.domain.configuration import (
    CheckKind,
    ConfigurationCheckRequest,
    ConfigurationCheckResult,
    ConfigurationReceipt,
    ConfigurationView,
    ProjectConfigurationRequest,
)
from migration_agent.domain.inspection_access import (
    InspectionCapability,
    InspectionContext,
    authorize_inspection,
)
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.workflow_access import (
    WorkflowCapability,
    WorkflowContext,
    authorize_workflow,
)

logger = logging.getLogger("migration_agent.mcp")


async def protect_protocol(
    ctx: ServerRequestContext[Any, Any], call_next: CallNext
) -> HandlerResult:
    """Protect SDK validation errors as well as application tool results."""
    policy = RedactionPolicy()
    request_text = json.dumps(ctx.params or {})
    if len(request_text.encode("utf-8")) > 65_536 or policy.contains_secret(request_text):
        if ctx.method == "tools/call":
            return CallToolResult(
                is_error=True,
                content=[TextContent(type="text", text="INVALID_REQUEST: input rejected.")],
            )
        raise MCPError(code=INVALID_PARAMS, message="INVALID_REQUEST: input rejected.")
    try:
        result = await call_next(ctx)
    except ValidationError as err:
        raise MCPError(code=INVALID_PARAMS, message="INVALID_REQUEST: invalid parameters.") from err
    except MCPError as err:
        raise MCPError(code=err.code, message=policy.redact_text(err.message)[:512]) from None
    if result is None:
        return None
    text = result.model_dump_json() if isinstance(result, BaseModel) else json.dumps(result)
    text = policy.redact_text(text)
    if len(text.encode("utf-8")) > 147_456:
        raise MCPError(code=INVALID_PARAMS, message="RESPONSE_TOO_LARGE: request a smaller scope.")
    if isinstance(result, BaseModel):
        return type(result).model_validate_json(text)
    cleaned: dict[str, Any] = json.loads(text)
    return cleaned


class RedactingStreamHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Stream handler that redacts secrets before writing to stderr."""

    def __init__(self, stream: Any = None) -> None:
        super().__init__(stream or sys.stderr)
        self._policy = RedactionPolicy()

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return self._policy.redact_text(msg)


def configure_mcp_logging(level: int = logging.INFO) -> None:
    """Ensure process-wide logging writes strictly to sys.stderr with secret redaction."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = RedactingStreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(level)


def create_mcp_server(
    binding: ProjectBinding,
    state_dir: Path | None = None,
    settings: Settings | None = None,
    inspection_context: InspectionContext | None = None,
) -> MCPServer:
    """Create and configure the MCPServer instance with bound read-only tools."""
    app_settings = settings or Settings()
    effective_state_dir = binding.validate_storage_roots(
        app_settings.resolve_state_dir(state_dir), app_settings.resolve_staging_root()
    )
    context = inspection_context or InspectionContext(
        actor=getpass.getuser(),
        assurance=AssuranceLevel.MODE_B
        if app_settings.mcp_trusted_local_reads
        else AssuranceLevel.MODE_C,
        capabilities=app_settings.mcp_read_capabilities,
    )
    from migration_agent.adapters.mcp.mutation_tools import register_mutation_tools
    from migration_agent.adapters.workflow_runtime import WorkflowRuntime

    authorization = ProjectAuthorization(binding.project_root, app_settings, "agent")
    runtime = WorkflowRuntime(binding, app_settings, effective_state_dir, authorization)
    checkpoint_store = runtime.store

    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[dict[str, Any]]:
        try:
            yield {}
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(runtime.close)

    server = MCPServer(
        name="migration-agent",
        version="0.1.0",
        middleware=[protect_protocol],
        lifespan=lifespan,
        instructions=(
            f"Migration Agent MCP Server bound to project '{binding.project_id}' "
            f"at root '{binding.project_root}'. Use typed host proposals and durable operations. "
            "Human approval requires the trusted CLI review command; models cannot approve. "
            "Source apply requires exact human approval, PASSED validation, and a clean Git base."
        ),
    )

    @server.tool(
        name="migration_doctor",
        description=(
            "Return machine-readable diagnostics for the local runtime environment and "
            "dependencies without reading secrets or contacting external services."
        ),
    )
    def doctor() -> DoctorResult:
        try:
            authorize_inspection(context, InspectionCapability.DIAGNOSTICS)
            authorization.require("system.diagnostics")
            return handle_doctor(settings=app_settings)
        except ValueError as err:
            raise _safe_tool_error(err) from None

    @server.tool(
        name="migration_inventory",
        description=(
            "Inspect the bound repository and return a deterministic, framework-neutral "
            "inventory of eligible files, dependencies, package boundaries, "
            "and detected frameworks."
        ),
    )
    def inventory(
        project_id: str = "", file_offset: int = 0, file_limit: int = 100
    ) -> InventoryResult:
        try:
            authorize_inspection(context, InspectionCapability.PROJECT_READ)
            authorization.require("project.read")
            return handle_inventory(
                binding=binding,
                project_id=project_id,
                file_offset=file_offset,
                file_limit=file_limit,
            )
        except ValueError as err:
            raise _safe_tool_error(err) from None

    @server.tool(
        name="migration_run_status",
        description=(
            "Query the status, step progress, checkpoints count, and execution report "
            "for a specific migration run."
        ),
    )
    def run_status(project_id: str, run_id: str) -> RunStatusResult:
        try:
            authorize_inspection(context, InspectionCapability.RUN_READ)
            authorization.require("run.read")
            return handle_run_status(
                binding=binding,
                project_id=project_id,
                run_id=run_id,
                checkpoint_store=checkpoint_store,
            )
        except ValueError as err:
            raise _safe_tool_error(err) from None

    @server.tool(
        name="migration_plan_show",
        description=(
            "Retrieve the complete migration plan definition, step dependency graph, "
            "and approval state for a specific plan."
        ),
    )
    def plan_show(
        project_id: str, plan_id: str, step_offset: int = 0, step_limit: int = 100
    ) -> PlanShowResult:
        try:
            authorize_inspection(context, InspectionCapability.PLAN_READ)
            authorization.require("plan.read")
            return handle_plan_show(
                binding=binding,
                project_id=project_id,
                plan_id=plan_id,
                checkpoint_store=checkpoint_store,
                step_offset=step_offset,
                step_limit=step_limit,
            )
        except ValueError as err:
            raise _safe_tool_error(err) from None

    @server.tool(
        name="migration_step_preview",
        description=(
            "Generate proposed ChangeSet metadata and unified diff for a plan or specific step "
            "without modifying source code or staging workspaces."
        ),
    )
    def step_preview(
        project_id: str,
        plan_id: str,
        step_id: str | None = None,
    ) -> StepPreviewResult:
        try:
            authorize_inspection(context, InspectionCapability.CHANGESET_READ)
            authorization.require("changeset.read")
            return handle_step_preview(
                binding=binding,
                project_id=project_id,
                plan_id=plan_id,
                step_id=step_id,
                checkpoint_store=checkpoint_store,
            )
        except ValueError as err:
            raise _safe_tool_error(err) from None

    host_service = runtime.proposals
    workflow_context = WorkflowContext(
        actor=context.actor,
        assurance=context.assurance,
        capabilities=app_settings.mcp_workflow_capabilities,
    )

    def configuration_facade(project_id: str) -> ConfigurationFacade:
        binding.validate_project_id(project_id)
        authorize_inspection(context, InspectionCapability.PROJECT_READ)
        return ConfigurationFacade(authorization, authorization.settings)

    @server.tool(name="migration_configuration_show")
    def configuration_show(project_id: str) -> ConfigurationView:
        """Inspect verified effective settings and provenance; never expose credentials."""
        try:
            return configuration_facade(project_id).service.view()
        except ValueError as error:
            raise _safe_tool_error(error) from None

    @server.tool(name="migration_configuration_propose")
    def configuration_propose(
        project_id: str, proposal: ProjectConfigurationRequest
    ) -> ConfigurationReceipt:
        """Record a bounded shared candidate. A human owner must sign and activate it."""
        try:
            authorize_workflow(workflow_context, WorkflowCapability.PLAN_SUBMIT)
            return configuration_facade(project_id).service.propose(proposal)
        except ValueError as error:
            raise _safe_tool_error(error) from None

    @server.tool(name="migration_configuration_check")
    def configuration_check(
        project_id: str, request: ConfigurationCheckRequest
    ) -> ConfigurationCheckResult:
        """Run offline checks only; no provider calls, consent, signing or shell commands."""
        try:
            if request.kind != CheckKind.OFFLINE:
                raise ValueError(
                    "CONFIGURATION_OFFLINE_ONLY: run explicit probes from a human session."
                )
            return ConfigurationChecks(configuration_facade(project_id)).start(request)
        except ValueError as error:
            raise _safe_tool_error(error) from None

    @server.tool(name="migration_configuration_check_status")
    def configuration_check_status(project_id: str, operation_id: str) -> ConfigurationCheckResult:
        """Read the current principal's durable configuration check receipt."""
        try:
            return ConfigurationChecks(configuration_facade(project_id)).result(operation_id)
        except ValueError as error:
            raise _safe_tool_error(error) from None

    register_host_tools(
        server,
        binding,
        host_service,
        WorkflowContext(
            actor=context.actor,
            assurance=context.assurance,
            capabilities=app_settings.mcp_workflow_capabilities,
        ),
    )
    register_mutation_tools(
        server,
        runtime,
        WorkflowContext(
            actor=context.actor,
            assurance=context.assurance,
            capabilities=app_settings.mcp_workflow_capabilities,
        ),
    )
    return server


def _safe_tool_error(err: ValueError) -> ToolError:
    return ToolError(RedactionPolicy().redact_text(str(err))[:512])


def run_mcp_server(
    project_root: str | Path,
    state_dir: Path | None = None,
    settings: Settings | None = None,
) -> None:
    """Run the MCP server over stdio with process-wide stream isolation and root binding."""
    configure_mcp_logging()
    try:
        binding = ProjectBinding(project_root)
        server = create_mcp_server(binding=binding, state_dir=state_dir, settings=settings)
        logger.info("Starting Migration Agent MCP server for project '%s'", binding.project_id)

        async def serve() -> None:
            try:
                await server.run_stdio_async()
            except anyio.get_cancelled_exc_class():
                logger.info("MCP transport cancelled.")

        anyio.run(serve)
    except KeyboardInterrupt:
        logger.info("MCP server stopped cleanly.")
    except Exception as err:
        logger.exception("MCP server failed: %s", err)
        sys.exit(1)
