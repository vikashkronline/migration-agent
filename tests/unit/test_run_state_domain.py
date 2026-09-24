"""Unit tests for Phase 6 execution state domain models and redaction policies."""

import pytest
from pydantic import ValidationError

from migration_agent.domain import (
    ExecutionStep,
    RedactionPolicy,
    RunRecord,
    RunSummary,
)


def test_execution_step_enum_members() -> None:
    expected = {
        "INITIALIZED",
        "STAGED",
        "VALIDATING",
        "REPAIRING",
        "COMPLETED",
        "FAILED",
        "ABORTED",
    }
    actual = {step.value for step in ExecutionStep}
    assert actual == expected


def test_run_record_creation_and_immutability() -> None:
    record = RunRecord(
        run_id="run-001",
        plan_id="plan-001",
        source_root="/repo",
        status=ExecutionStep.INITIALIZED,
    )
    assert record.run_id == "run-001"
    assert record.plan_id == "plan-001"
    assert record.source_root == "/repo"
    assert record.staging_root is None
    assert record.status == ExecutionStep.INITIALIZED
    assert record.current_step_id is None
    assert record.applied_changeset_id is None
    assert record.created_at is not None
    assert record.updated_at is not None

    with pytest.raises(ValidationError):
        # Frozen model prohibits direct mutation
        record.status = ExecutionStep.COMPLETED  # type: ignore[misc]


def test_run_summary_projection() -> None:
    record = RunRecord(
        run_id="run-002",
        plan_id="plan-002",
        source_root="/repo",
        status=ExecutionStep.STAGED,
        staging_root="/staging/run-002",
    )
    summary = RunSummary(
        run_id=record.run_id,
        plan_id=record.plan_id,
        status=record.status,
        source_root=record.source_root,
        staging_root=record.staging_root,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
    assert summary.run_id == "run-002"
    assert summary.status == ExecutionStep.STAGED


def test_redaction_policy_sensitive_keys() -> None:
    policy = RedactionPolicy()
    assert policy.is_sensitive_key("API_KEY")
    assert policy.is_sensitive_key("secret_token")
    assert policy.is_sensitive_key("openai_api_key")
    assert policy.is_sensitive_key("gemini_credentials")
    assert policy.is_sensitive_key("AUTH_HEADER")
    assert policy.is_sensitive_key("USER_PASSWORD")
    assert not policy.is_sensitive_key("component_name")
    assert not policy.is_sensitive_key("file_path")


def test_redaction_policy_inline_text() -> None:
    policy = RedactionPolicy()
    text = "Use key sk-1234567890abcdef1234 and Bearer tok_1234567890abcdef here."
    redacted = policy.redact_text(text)
    assert "sk-" not in redacted
    assert "Bearer" not in redacted
    assert "[REDACTED]" in redacted


def test_redaction_policy_nested_payload_and_oversized_digestion() -> None:
    policy = RedactionPolicy(max_payload_bytes=64)

    payload = {
        "normal": "hello world",
        "api_key": "super_secret_123",
        "nested": {
            "token": "secret_abc",
            "safe_list": ["item1", "sk-1234567890abcdef1234"],
        },
        "large_text": "A" * 200,
        "large_bytes": b"B" * 200,
    }

    cleaned = policy.redact_payload(payload)

    assert cleaned["normal"] == "hello world"
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["token"] == "[REDACTED]"
    assert cleaned["nested"]["safe_list"][0] == "item1"
    assert cleaned["nested"]["safe_list"][1] == "[REDACTED]"

    # Large text truncated and digested
    assert isinstance(cleaned["large_text"], dict)
    assert cleaned["large_text"]["digest"].startswith("sha256:")
    assert "... [TRUNCATED]" in cleaned["large_text"]["preview"]
    assert cleaned["large_text"]["size_bytes"] == 200

    # Large bytes truncated and digested
    assert isinstance(cleaned["large_bytes"], dict)
    assert cleaned["large_bytes"]["digest"].startswith("sha256:")
    assert cleaned["large_bytes"]["preview"] == "[BINARY_DATA_TRUNCATED]"
    assert cleaned["large_bytes"]["size_bytes"] == 200
