"""Read-only tool handler implementations for MCP server."""

from __future__ import annotations

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import (
    AngularAdapter,
    AngularJsDirectiveAdapter,
    EmberClassicAdapter,
)
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.adapters.mcp.binding import ProjectBinding, validate_identifier
from migration_agent.adapters.mcp.models import (
    DoctorResult,
    InventoryResult,
    PlanShowResult,
    RunStatusResult,
    StepPreviewResult,
    protect_result,
)
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.doctor import collect_diagnostics
from migration_agent.application.inventory import InventoryService
from migration_agent.application.transformation import TransformationService
from migration_agent.config import Settings
from migration_agent.domain.planning import MigrationPlan, compute_plan_digest
from migration_agent.ports.frameworks import FrameworkAdapterRegistry


def _load_bound_plan(
    binding: ProjectBinding,
    plan_id: str,
    store: SqliteCheckpointStore,
    governance: GitGovernanceAdapter,
) -> MigrationPlan:
    plan = store.get_plan(plan_id) or governance.load_plan(str(binding.project_root), plan_id)
    if plan is None:
        raise ValueError("PLAN_NOT_FOUND: plan not found.")
    binding.validate_record_root(plan.source_root)
    if plan.plan_id != plan_id:
        raise ValueError("PLAN_MISMATCH: stored plan identifier does not match.")
    run = store.get_run_record(plan.run_id)
    if run is not None:
        binding.validate_record_root(run.source_root)
        if run.plan_id != plan.plan_id:
            raise ValueError("RUN_MISMATCH: related run does not match the plan.")
    return plan


def _validate_page(offset: int, limit: int) -> None:
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("INVALID_PAGE: offset must be nonnegative and limit between 1 and 100.")


def _create_default_framework_registry() -> FrameworkAdapterRegistry:
    return FrameworkAdapterRegistry(
        (
            EmberClassicAdapter(),
            AngularJsDirectiveAdapter(),
            AngularAdapter(),
        )
    )


def handle_doctor(settings: Settings | None = None) -> DoctorResult:
    """Collect local setup diagnostics."""
    diagnostics = collect_diagnostics(settings=settings)
    return protect_result(DoctorResult.model_validate(diagnostics))


def handle_inventory(
    binding: ProjectBinding,
    project_id: str = "",
    file_offset: int = 0,
    file_limit: int = 100,
) -> InventoryResult:
    """Perform deterministic repository inventory for the bound project."""
    if project_id:
        binding.validate_project_id(project_id)
    _validate_page(file_offset, file_limit)

    registry = _create_default_framework_registry()
    inspector = SafeFilesystemInspector()
    service = InventoryService(inspector, registry)
    inventory = service.inventory(binding.project_root)

    total = len(inventory.files)
    paged = inventory.model_copy(
        update={"files": inventory.files[file_offset : file_offset + file_limit]}
    )
    return protect_result(
        InventoryResult(
            project_id=binding.project_id,
            status="ok",
            inventory=paged,
            file_offset=file_offset,
            files_total=total,
            has_more_files=file_offset + file_limit < total,
        )
    )


def handle_run_status(
    binding: ProjectBinding,
    project_id: str,
    run_id: str,
    checkpoint_store: SqliteCheckpointStore,
) -> RunStatusResult:
    """Inspect status and checkpoints for a given migration run."""
    binding.validate_project_id(project_id)
    binding.validate_storage_roots(checkpoint_store.state_dir)
    cleaned_run_id = validate_identifier(run_id, "run_id")

    record = checkpoint_store.get_run_record(cleaned_run_id)
    if record is None:
        raise ValueError("RUN_NOT_FOUND: run not found.")
    binding.validate_record_root(record.source_root)
    if record.run_id != cleaned_run_id:
        raise ValueError("RUN_MISMATCH: stored run identifier does not match.")
    related_plan = checkpoint_store.get_plan(record.plan_id)
    if related_plan is not None:
        binding.validate_record_root(related_plan.source_root)
        if related_plan.run_id != record.run_id:
            raise ValueError("PLAN_MISMATCH: related plan does not match the run.")

    report = checkpoint_store.get_run_report(cleaned_run_id)
    checkpoints = checkpoint_store.list_checkpoints(cleaned_run_id)

    return protect_result(
        RunStatusResult(
            project_id=binding.project_id,
            run_id=record.run_id,
            plan_id=record.plan_id,
            status=record.status.value,
            current_step_id=record.current_step_id,
            applied_changeset_id=record.applied_changeset_id,
            checkpoints_count=len(checkpoints),
            report_status=report.status.value if report else None,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
            source_root=record.source_root,
            staging_root=record.staging_root,
        )
    )


def handle_plan_show(
    binding: ProjectBinding,
    project_id: str,
    plan_id: str,
    checkpoint_store: SqliteCheckpointStore,
    governance: GitGovernanceAdapter | None = None,
    step_offset: int = 0,
    step_limit: int = 100,
) -> PlanShowResult:
    """Retrieve full plan details for a specific migration plan."""
    binding.validate_project_id(project_id)
    binding.validate_storage_roots(checkpoint_store.state_dir)
    _validate_page(step_offset, step_limit)
    cleaned_plan_id = validate_identifier(plan_id, "plan_id")

    gov = governance or GitGovernanceAdapter()
    plan = _load_bound_plan(binding, cleaned_plan_id, checkpoint_store, gov)
    total = len(plan.steps)
    paged = plan.model_copy(update={"steps": plan.steps[step_offset : step_offset + step_limit]})

    return protect_result(
        PlanShowResult(
            project_id=binding.project_id,
            plan_id=plan.plan_id,
            status="ok",
            plan=paged,
            plan_digest=compute_plan_digest(plan),
            step_offset=step_offset,
            steps_total=total,
            has_more_steps=step_offset + step_limit < total,
        )
    )


def handle_step_preview(
    binding: ProjectBinding,
    project_id: str,
    plan_id: str,
    step_id: str | None = None,
    checkpoint_store: SqliteCheckpointStore | None = None,
    governance: GitGovernanceAdapter | None = None,
) -> StepPreviewResult:
    """Generate staged changeset preview and unified diff without modifying source."""
    binding.validate_project_id(project_id)
    cleaned_plan_id = validate_identifier(plan_id, "plan_id")

    gov = governance or GitGovernanceAdapter()
    if checkpoint_store is None:
        raise ValueError("STATE_STORE_REQUIRED: preview requires a validated operational store.")
    store = checkpoint_store
    binding.validate_storage_roots(store.state_dir)
    plan = _load_bound_plan(binding, cleaned_plan_id, store, gov)

    cleaned_step_id = validate_identifier(step_id, "step_id") if step_id is not None else None
    if cleaned_step_id is None:
        if len(plan.steps) != 1:
            raise ValueError("STEP_REQUIRED: select one plan step for a bounded preview.")
        cleaned_step_id = validate_identifier(plan.steps[0].step_id, "step_id")

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        registry=_create_default_framework_registry(),
        filesystem=SafeFilesystemInspector(),
        checkpoint_store=None,
        audit_logger=store,
        max_preview_files=100,
        max_preview_bytes=32_768,
    )

    changeset, diff_text = service.preview(
        binding.project_root,
        plan,
        step_id=cleaned_step_id,
    )

    result = protect_result(
        StepPreviewResult(
            project_id=binding.project_id,
            plan_id=plan.plan_id,
            step_id=cleaned_step_id,
            changeset_id=changeset.changeset_id,
            changeset_digest=changeset.changeset_digest,
            worktree_fingerprint=changeset.worktree_fingerprint,
            file_count=len(changeset.changes),
            diff=diff_text,
            status="ok",
        )
    )
    store.save_changeset(changeset)
    return result
