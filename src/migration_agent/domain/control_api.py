"""Domain entities and view models for the Local Control API and Control Center GUI."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ControlApiErrorCode(StrEnum):
    """Structured error codes emitted across the Control API boundary."""

    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN_ORIGIN = "FORBIDDEN_ORIGIN"
    CSRF_REJECTED = "CSRF_REJECTED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    BASE_CHANGED = "BASE_CHANGED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    INVALID_REQUEST = "INVALID_REQUEST"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SessionTokenInfo(BaseModel):
    """Cryptographically generated session token bound to a GUI execution session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str = Field(min_length=16)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    actor: str = Field(default="local-user", min_length=1)
    csrf_token: str = Field(min_length=16)


class ControlApiError(BaseModel):
    """Structured error details for rejected or failed Control API requests."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ControlApiErrorCode
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class ControlApiResponse(BaseModel):
    """Standardized response envelope for all Control API operations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = "ok"  # "ok" or "error"
    data: Any = None
    error: ControlApiError | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request_id: str | None = None


class RunSummaryView(BaseModel):
    """Projection of an operational migration run for GUI listing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    source_root: str = Field(min_length=1)
    staging_root: str | None = None
    created_at: str
    updated_at: str
    has_recovery_required: bool = False
    terminal_state: str | None = None


class RunDetailView(BaseModel):
    """Comprehensive run inspection view with terminal diagnostics and checkpoints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    source_root: str = Field(min_length=1)
    staging_root: str | None = None
    current_step_id: str | None = None
    created_at: str
    updated_at: str
    terminal_state: str | None = None
    terminal_reason: str | None = None
    affected_files: list[str] = Field(default_factory=list)
    recovery_actions: list[str] = Field(default_factory=list)
    checkpoints: list[dict[str, Any]] = Field(default_factory=list)


class DiffFileView(BaseModel):
    """Per-file side-by-side visual diff model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    change_type: str = Field(default="MODIFY")  # "CREATE", "MODIFY", "DELETE"
    old_content: str | None = None
    new_content: str | None = None
    patch: str = ""
    is_safe: bool = True
    additions: int = 0
    deletions: int = 0


class DiffReviewView(BaseModel):
    """Complete side-by-side diff review model for a staged changeset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(min_length=1)
    changeset_id: str | None = None
    changeset_digest: str | None = None
    files: list[DiffFileView] = Field(default_factory=list)
    total_files: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    is_clean: bool = True


class PlanView(BaseModel):
    """Projection of a typed migration plan DAG for GUI review and approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    plan_digest: str = Field(min_length=1)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    is_approved: bool = False
    approval_signature: dict[str, Any] | None = None


class GraphView(BaseModel):
    """Full-stack cross-domain dependency graph view with Mermaid source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    mermaid_source: str = ""
    domains: list[str] = Field(default_factory=list)


class LearningsView(BaseModel):
    """Curated project learnings and recorded challenges from .agent/."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    learnings: list[dict[str, Any]] = Field(default_factory=list)
    challenges: list[dict[str, Any]] = Field(default_factory=list)


class DoctorView(BaseModel):
    """Machine-readable system diagnostics and dependency health status."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = "ok"
    checks: list[dict[str, Any]] = Field(default_factory=list)


class ApprovePlanPayload(BaseModel):
    """Mutating payload to sign and approve a migration plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: str = Field(default="local-developer", min_length=1)
    request_id: str | None = None
    notes: str = ""


class ApplyRunPayload(BaseModel):
    """Mutating payload to execute controlled apply for a staged run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor: str = Field(default="local-developer", min_length=1)
    request_id: str | None = None


class WebSocketEventMessage(BaseModel):
    """Structured event envelope sent across WebSocket and SSE connections."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str = Field(min_length=1)
    sequence_id: int = Field(ge=0)
    timestamp: str
    payload: dict[str, Any] = Field(default_factory=dict)
