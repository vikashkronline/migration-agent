"""Typed schemas for MCP read-only inspection tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.inventory import ProjectInventory
from migration_agent.domain.planning import MigrationPlan
from migration_agent.domain.redaction import RedactionPolicy

MAX_RESULT_BYTES = 65_536


class MCPModel(BaseModel):
    """Immutable base model for MCP tools."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    redacted: bool = False


class DoctorCheck(MCPModel):
    """Result of an individual doctor check."""

    name: str
    status: str
    details: dict[str, Any]


class DoctorResult(MCPModel):
    """Diagnostics result for the local runtime environment."""

    schema_version: int = 1
    status: str
    checks: list[DoctorCheck]


class InventoryResult(MCPModel):
    """Project inventory result."""

    project_id: str
    status: str = "ok"
    inventory: ProjectInventory
    file_offset: int = 0
    files_total: int = 0
    has_more_files: bool = False


class RunStatusResult(MCPModel):
    """Operational status and progress of a migration run."""

    project_id: str
    run_id: str
    plan_id: str
    status: str
    current_step_id: str | None = None
    applied_changeset_id: str | None = None
    checkpoints_count: int = Field(ge=0)
    report_status: str | None = None
    created_at: str
    updated_at: str
    source_root: str
    staging_root: str | None = None


class PlanShowResult(MCPModel):
    """Complete migration plan details."""

    project_id: str
    plan_id: str
    status: str = "ok"
    plan: MigrationPlan
    plan_digest: str
    step_offset: int = 0
    steps_total: int = 0
    has_more_steps: bool = False
    display_only: bool = True


class StepPreviewResult(MCPModel):
    """Staged changeset preview and unified diff."""

    project_id: str
    plan_id: str
    step_id: str | None = None
    changeset_id: str
    changeset_digest: str
    worktree_fingerprint: str
    file_count: int = Field(ge=0)
    diff: str
    status: str = "ok"


def protect_result[ResultT: MCPModel](result: ResultT) -> ResultT:
    """Redact display strings and enforce the serialized DTO byte budget."""
    policy = RedactionPolicy()
    original = result.model_dump(mode="json")

    def redact(value: Any) -> Any:
        if isinstance(value, str):
            return policy.redact_text(value)
        if isinstance(value, dict):
            return {policy.redact_text(key): redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    cleaned = redact(original)
    cleaned["redacted"] = cleaned != original
    protected = type(result).model_validate(cleaned)
    if len(protected.model_dump_json().encode("utf-8")) > MAX_RESULT_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE: request a smaller page or step scope.")
    return protected
