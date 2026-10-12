"""Offline rule-registry, exact evidence and coverage regressions."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from migration_agent.adapters.rules import AngularRuleEvaluator, load_rule_registry
from migration_agent.application.standards_review import StandardsReviewService
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import (
    ChangeSet,
    FileChange,
    FileOperation,
    compute_changeset_digest,
    compute_file_sha256,
)
from migration_agent.domain.execution import ExecutionPolicy, ExecutionProvenance, ValidationMode
from migration_agent.domain.host_workflow import ValidationExecution, WorkflowRecord
from migration_agent.domain.rules import (
    FileRuleReview,
    RuleEnforcement,
    RuleEvaluation,
    RuleOutcome,
    RuleRegistry,
)
from migration_agent.domain.validation import ValidationProfile, ValidationResult, ValidationStatus


def artifact(data: bytes = b"export const title = 'Hello';\n", path: str = "src/card.ts"):
    changeset = ChangeSet(
        changeset_id="cs-rules",
        plan_id="plan-rules",
        step_id="step-1",
        base_revision="fixture-base",
        worktree_fingerprint="fixture-worktree",
        changes=(
            FileChange(
                path=path,
                operation=FileOperation.CREATE,
                content_bytes=data,
                content_digest=compute_file_sha256(data),
            ),
        ),
    )
    changeset = changeset.model_copy(
        update={"changeset_digest": compute_changeset_digest(changeset)}
    )
    record = WorkflowRecord(
        project_id="fixture-project",
        source_root="fixture-source",
        run_id="run-rules",
        plan_id=changeset.plan_id,
        step_id=changeset.step_id,
        changeset_id=changeset.changeset_id,
        changeset_digest=changeset.changeset_digest,
        base_revision=changeset.base_revision,
        worktree_fingerprint=changeset.worktree_fingerprint,
        root_commit="fixture-root",
        policy_digest="fixture-policy",
        staging_fingerprint="fixture-staging",
    )
    return record, changeset


def execution_for(record, profiles=tuple(ValidationProfile), failed=False):
    policy = ExecutionPolicy(
        mode=ValidationMode.CONTAINER,
        project_policy_digest=record.policy_digest,
        network="none",
        filesystem="container",
        supervision="fixture",
    )
    execution = ValidationExecution(
        schema_version=2,
        project_id=record.project_id,
        plan_id=record.plan_id,
        step_id=record.step_id,
        changeset_id=record.changeset_id,
        changeset_digest=record.changeset_digest,
        staging_fingerprint=record.staging_fingerprint,
        provenance=ExecutionProvenance(
            backend=ValidationMode.CONTAINER,
            policy=policy,
            policy_digest=policy.digest,
            input_digest=record.staging_fingerprint,
            cleanup_verified=True,
        ),
        results=tuple(
            ValidationResult(
                command="fixture-" + profile.value,
                profile=profile,
                status=ValidationStatus.FAILED if failed else ValidationStatus.PASSED,
                exit_code=1 if failed else 0,
            )
            for profile in profiles
        ),
    )
    return (
        record.model_copy(
            update={
                "validation_results": execution.results,
                "validation_digest": compute_canonical_digest(execution.model_dump(mode="json")),
            }
        ),
        execution,
    )


def review(record, changeset, registry=None, execution=None):
    return StandardsReviewService().review(
        record, changeset, registry or load_rule_registry(), AngularRuleEvaluator(), execution
    )


def test_default_reports_every_rule_without_claiming_manual_completion():
    record, changeset = artifact()
    report = review(record, changeset)
    assert report.status == "BLOCKED" and report.report_only
    assert report.total_files == 1 and report.applicable_check_count == 3
    assert report.completed_check_count == 1
    assert {row.rule_id: row.outcome for row in report.files[0].evaluations} == {
        "RULE-FORMAT-001": RuleOutcome.PASS,
        "RULE-MIGRATION-CONTRACT-001": RuleOutcome.PENDING_MANUAL,
        "RULE-QUALITY-001": RuleOutcome.BLOCKED,
    }
    assert "export const" not in report.model_dump_json()
    assert report.registry_digest == load_rule_registry().digest


def test_recorded_commands_pass_but_manual_obligation_remains_pending():
    record, changeset = artifact()
    record, execution = execution_for(record)
    report = review(record, changeset, execution=execution)
    assert report.completed_check_count == 2 and report.status == "BLOCKED"
    assert report.validation_digest == record.validation_digest
    assert report.files[0].evaluations[-1].outcome == RuleOutcome.PASS


@pytest.mark.parametrize(
    "profiles,failed,expected",
    [
        ((ValidationProfile.TYPECHECK,), False, RuleOutcome.BLOCKED),
        (tuple(ValidationProfile), True, RuleOutcome.FAIL),
    ],
)
def test_missing_and_failed_command_evidence(profiles, failed, expected):
    record, changeset = artifact()
    record, execution = execution_for(record, profiles, failed)
    assert (
        review(record, changeset, execution=execution).files[0].evaluations[-1].outcome == expected
    )


def test_selected_profile_has_real_formatting_pass_and_failure():
    registry = load_rule_registry()
    registry = registry.model_copy(update={"rules": (registry.rules[0],)})
    record, changeset = artifact()
    assert review(record, changeset, registry).status == "PASS"
    record, changeset = artifact(b"line one\nline two\r\n")
    report = review(record, changeset, registry)
    assert report.status == "FAIL"
    assert report.files[0].evaluations[0].line_number == 2
    record, changeset = artifact(path="notes.txt")
    assert review(record, changeset, registry).status == "BLOCKED"


@pytest.mark.parametrize(
    "data,path",
    [
        (b"text", "../outside.ts"),
        (b"text", "src/.env"),
        (b"\xff", "src/invalid.ts"),
        (b"x\0y", "src/binary.ts"),
        (b"x" * 32769, "src/huge.ts"),
        (("sk-" + "A" * 48).encode(), "src/credential.ts"),
    ],
    ids=["traversal", "protected", "encoding", "binary", "oversized", "credential"],
)
def test_unsafe_candidates_fail_without_content_in_errors(data, path):
    record, changeset = artifact(data, path)
    with pytest.raises(ValueError) as error:
        review(record, changeset)
    assert "sk-" not in str(error.value)


def test_artifact_tampering_and_validation_from_another_candidate_fail():
    record, changeset = artifact()
    bad = changeset.changes[0].model_copy(update={"content_bytes": b"other bytes"})
    with pytest.raises(ValueError, match="altered file bytes"):
        review(record, changeset.model_copy(update={"changes": (bad,)}))
    record, execution = execution_for(record)
    with pytest.raises(ValueError, match="does not bind"):
        review(record, changeset, execution=execution.model_copy(update={"step_id": "other"}))
    with pytest.raises(ValueError, match="missing"):
        review(record, changeset)


def test_case_collisions_renames_and_deletions():
    record, changeset = artifact()
    for change in (
        changeset.changes[0].model_copy(update={"old_path": "src/old.ts"}),
        changeset.changes[0].model_copy(update={"path": "src/Card.ts"}),
    ):
        bad = changeset.model_copy(update={"changes": (*changeset.changes, change)})
        bad = bad.model_copy(update={"changeset_digest": compute_changeset_digest(bad)})
        with pytest.raises(ValueError, match="renames or duplicate"):
            review(record.model_copy(update={"changeset_digest": bad.changeset_digest}), bad)
    deleted = changeset.changes[0].model_copy(
        update={"operation": FileOperation.DELETE, "content_bytes": None}
    )
    changeset = changeset.model_copy(update={"changes": (deleted,)})
    changeset = changeset.model_copy(
        update={"changeset_digest": compute_changeset_digest(changeset)}
    )
    report = review(
        record.model_copy(update={"changeset_digest": changeset.changeset_digest}), changeset
    )
    assert report.status == "BLOCKED"
    assert report.files[0].operation == FileOperation.DELETE
    assert report.files[0].evaluations[0].outcome == RuleOutcome.BLOCKED


def test_registry_accepts_external_aliases_and_all_known_enforcement_modes():
    original = load_rule_registry().model_dump(mode="json", by_alias=True)
    rows = []
    for index, mode in enumerate(RuleEnforcement):
        row = dict(original["rules"][0])
        row.update(id=f"RULE-IMPORT-{index}", enforcement=mode.value, evaluatorId=None)
        rows.append(row)
    original["rules"] = rows
    registry = RuleRegistry.model_validate_json(json.dumps(original))
    assert {rule.enforcement for rule in registry.rules} == set(RuleEnforcement)
    record, changeset = artifact()
    report = review(record, changeset, registry)
    assert all(
        row.outcome in {RuleOutcome.BLOCKED, RuleOutcome.PENDING_MANUAL}
        for row in report.files[0].evaluations
    )


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "bool", "extra", "empty", "profiles"])
def test_malformed_registries_are_rejected(mutation):
    data = load_rule_registry().model_dump(mode="json", by_alias=True)
    if mutation == "unknown":
        data["rules"][0]["enforcement"] = "EXECUTE_SHELL"
    elif mutation == "duplicate":
        data["rules"].append(data["rules"][0])
    elif mutation == "bool":
        data["rules"][0]["safeAutofix"] = "true"
    elif mutation == "extra":
        data["rules"][0]["shellCommand"] = "untrusted"
    elif mutation == "empty":
        data["rules"] = []
    else:
        data["rules"][0]["requiredProfiles"] = ["TEST"]
    with pytest.raises(ValidationError):
        RuleRegistry.model_validate_json(json.dumps(data))


def test_registry_digest_and_report_order_are_deterministic():
    registry = load_rule_registry()
    reversed_registry = registry.model_copy(update={"rules": tuple(reversed(registry.rules))})
    assert registry.digest == reversed_registry.digest
    assert registry.digest != registry.model_copy(update={"version": "changed"}).digest
    record, changeset = artifact()
    assert (
        review(record, changeset, registry).model_dump_json()
        == review(record, changeset, reversed_registry).model_dump_json()
    )


def test_registry_loader_rejects_sensitive_and_invalid_files(tmp_path: Path):
    for name, data in [("secrets.json", "{}"), ("bad.json", "invalid JSON")]:
        path = tmp_path / name
        path.write_text(data, encoding="utf-8")
        with pytest.raises(ValueError, match="RULE_REGISTRY_INVALID"):
            load_rule_registry(path)


def test_bundled_profile_excludes_reference_identity():
    registry = load_rule_registry()
    assert registry.source is None
    assert registry.profile_id == "ember-angular-baseline"
    data = registry.model_dump(mode="json")
    data.pop("profile_id")
    external = RuleRegistry.model_validate_json(json.dumps(data))
    assert external.profile_id == "external-registry"


def test_unknown_applicability_cannot_silently_skip_required_rules(tmp_path):
    data = load_rule_registry().model_dump(mode="json")
    data["rules"][0]["applies_to"] = ["UNSUPPORTED"]
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="RULE_REGISTRY_INVALID"):
        load_rule_registry(path)


def test_completed_checks_and_coverage_cannot_omit_evidence():
    with pytest.raises(ValidationError, match="RULE_EVIDENCE_REQUIRED"):
        RuleEvaluation(
            rule_id="RULE-CHECK-001",
            outcome=RuleOutcome.PASS,
            severity="ERROR",
            evaluator="fixture",
            summary="claimed pass",
        )
    with pytest.raises(ValidationError, match="RULE_COVERAGE_INVALID"):
        FileRuleReview(
            path="src/card.ts",
            operation=FileOperation.CREATE,
            content_digest="fixture",
            applicable_rule_ids=("RULE-CHECK-001",),
            evaluations=(),
        )


def test_imported_ast_obligations_are_visible_and_blocked(tmp_path):
    data = load_rule_registry().model_dump(mode="json")
    data["rules"][0]["applies_to"] = ["AST"]
    path = tmp_path / "ast-scope.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    registry = load_rule_registry(path)
    record, changeset = artifact()
    report = review(record, changeset, registry)
    assert report.files[0].evaluations[0].outcome == RuleOutcome.BLOCKED
    assert "Source AST evidence" in report.files[0].evaluations[0].summary
