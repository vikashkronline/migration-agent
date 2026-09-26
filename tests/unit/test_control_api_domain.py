"""Unit tests for Control API domain models and view models."""

from migration_agent.domain import (
    ApplyRunPayload,
    ApprovePlanPayload,
    ControlApiError,
    ControlApiErrorCode,
    ControlApiResponse,
    DiffFileView,
    DiffReviewView,
    GraphView,
    PlanView,
    RunDetailView,
    RunSummaryView,
    SessionTokenInfo,
    WebSocketEventMessage,
)


def test_session_token_info_creation() -> None:
    token_info = SessionTokenInfo(
        token="abcdefghijklmnopqrstuvwxyz123456",
        csrf_token="abcdefghijklmnopqrstuvwxyz123456",
        actor="dev-user",
    )
    assert token_info.token == "abcdefghijklmnopqrstuvwxyz123456"
    assert token_info.actor == "dev-user"
    assert token_info.created_at is not None


def test_control_api_response_envelope() -> None:
    ok_resp = ControlApiResponse(status="ok", data={"key": "val"})
    assert ok_resp.status == "ok"
    assert ok_resp.data == {"key": "val"}
    assert ok_resp.error is None

    err = ControlApiError(
        code=ControlApiErrorCode.UNAUTHORIZED,
        message="Token required",
    )
    err_resp = ControlApiResponse(status="error", error=err)
    assert err_resp.status == "error"
    assert err_resp.error is not None
    assert err_resp.error.code == ControlApiErrorCode.UNAUTHORIZED


def test_run_views() -> None:
    summary = RunSummaryView(
        run_id="run-1",
        plan_id="plan-1",
        status="COMPLETED",
        source_root="/tmp/src",
        created_at="2026-09-26T12:00:00Z",
        updated_at="2026-09-26T12:05:00Z",
    )
    assert summary.run_id == "run-1"
    assert summary.has_recovery_required is False

    detail = RunDetailView(
        run_id="run-2",
        plan_id="plan-2",
        status="FAILED",
        source_root="/tmp/src",
        created_at="2026-09-26T12:00:00Z",
        updated_at="2026-09-26T12:05:00Z",
        terminal_state="RECOVERY_REQUIRED",
        terminal_reason="Partial file write on disk full",
        affected_files=["app/component.ts"],
        recovery_actions=["Inspect filesystem"],
    )
    assert detail.terminal_state == "RECOVERY_REQUIRED"
    assert len(detail.affected_files) == 1


def test_diff_views() -> None:
    file_diff = DiffFileView(
        path="src/index.ts",
        change_type="MODIFY",
        patch="--- a\n+++ b\n+new line",
        additions=1,
        deletions=0,
    )
    review = DiffReviewView(
        run_id="run-1",
        files=[file_diff],
        total_files=1,
        total_additions=1,
        total_deletions=0,
        is_clean=False,
    )
    assert review.total_files == 1
    assert review.is_clean is False


def test_plan_and_graph_views() -> None:
    plan = PlanView(
        plan_id="plan-test",
        status="NEEDS_APPROVAL",
        plan_digest="abc123digest",
        steps=[{"step_id": "step-1", "title": "Setup", "risk": "LOW"}],
    )
    assert plan.plan_id == "plan-test"
    assert plan.is_approved is False

    graph = GraphView(
        nodes=[{"id": "ui:comp"}],
        edges=[{"source": "ui:comp", "target": "api:users"}],
        mermaid_source="graph TD\nui:comp --> api:users",
        domains=["frontend", "backend_api"],
    )
    assert len(graph.nodes) == 1
    assert "mermaid_source" in graph.model_dump()


def test_payloads_and_events() -> None:
    approve = ApprovePlanPayload(actor="reviewer-1", notes="LGTM")
    assert approve.actor == "reviewer-1"

    apply_payload = ApplyRunPayload(actor="deployer-1")
    assert apply_payload.actor == "deployer-1"

    ev = WebSocketEventMessage(
        event_type="PLAN_APPROVED",
        sequence_id=42,
        timestamp="2026-09-26T12:00:00Z",
        payload={"plan_id": "p-1"},
    )
    assert ev.event_type == "PLAN_APPROVED"
    assert ev.sequence_id == 42
