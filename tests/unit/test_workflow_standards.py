"""The standards ledger uses shared staged evidence without granting approval."""

import json
from pathlib import Path

import pytest
from test_shared_apply import validated
from test_shared_apply import workflow as workflow
from typer.testing import CliRunner

from migration_agent.adapters.rules import AngularRuleEvaluator, load_rule_registry
from migration_agent.cli import app
from migration_agent.domain.host_workflow import Lifecycle


def staged(workflow):
    runtime, plan, step = workflow
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "standards-fixture", ttl=900)
    try:
        return runtime.apply_service.stage(plan, step, lease)
    finally:
        runtime.store.release_lease(lease)


def test_standards_review_is_read_only_and_does_not_authorize_apply(workflow):
    runtime, plan, step = workflow
    record = staged(workflow)
    before = runtime.proposals.evidence.repository_state()
    report = runtime.apply_service.review_standards(
        plan, step, load_rule_registry(), AngularRuleEvaluator()
    )
    assert report.status == "BLOCKED" and len(report.files) == 4
    assert report.changeset_digest == record.changeset_digest
    assert runtime.store.get_workflow(record.project_id, plan, step) == record
    assert runtime.proposals.evidence.repository_state() == before
    assert record.state == Lifecycle.STAGE_VERIFIED
    with pytest.raises(ValueError, match=r"VALIDATION_REQUIRED|APPROVAL_REQUIRED"):
        runtime.apply_service.apply(plan, step, record.changeset_id)


def test_verified_partial_validation_appears_as_missing_profiles(workflow):
    runtime, plan, step = workflow
    record = validated(workflow)
    report = runtime.apply_service.review_standards(
        plan, step, load_rule_registry(), AngularRuleEvaluator()
    )
    assert report.validation_digest == record.validation_digest
    assert report.status == "BLOCKED"
    assert any(
        "Missing required validation profiles" in evaluation.summary
        for file in report.files
        for evaluation in file.evaluations
    )
    assert runtime.store.get_workflow(record.project_id, plan, step) == record


@pytest.mark.parametrize("scope", ["source", "staging", "plan", "artifact"])
def test_standards_review_rejects_drift(workflow, scope):
    runtime, plan, step = workflow
    record = staged(workflow)
    changeset = runtime.store.get_changeset(record.changeset_id)
    if scope == "source":
        (runtime.proposals.root / "app/components/user-card.js").write_text("drift\n")
    elif scope == "staging":
        (Path(record.staging_path) / changeset.changes[0].path).write_text("drift\n")
    elif scope == "plan":
        stored = runtime.store.get_plan(plan)
        changed = stored.steps[0].model_copy(update={"description": "changed plan"})
        runtime.store.save_plan(stored.model_copy(update={"steps": [changed, *stored.steps[1:]]}))
    else:
        changed = changeset.changes[0].model_copy(update={"content_bytes": b"drift\n"})
        runtime.store.save_changeset(
            changeset.model_copy(update={"changes": (changed, *changeset.changes[1:])})
        )
    with pytest.raises(ValueError):
        runtime.apply_service.review_standards(
            plan, step, load_rule_registry(), AngularRuleEvaluator()
        )
    assert runtime.store.get_workflow(record.project_id, plan, step) == record


def test_cli_standards_emits_typed_pending_report(workflow, monkeypatch):
    runtime, plan, step = workflow
    staged(workflow)
    monkeypatch.setattr("migration_agent.adapters.workflow_cli.runtime_for", lambda *args: runtime)
    result = CliRunner().invoke(
        app,
        [
            "validation",
            "standards",
            step,
            "--project-root",
            str(runtime.proposals.root),
            "--plan",
            plan,
        ],
    )
    assert result.exit_code == 1, result.output
    report = json.loads(result.output)
    assert report["status"] == "BLOCKED" and report["report_only"]
    assert report["total_files"] == 4


def test_cli_selected_registry_can_pass_without_source_approval(workflow, monkeypatch, tmp_path):
    runtime, plan, step = workflow
    record = staged(workflow)
    registry = load_rule_registry()
    registry = registry.model_copy(update={"rules": (registry.rules[0],)})
    path = tmp_path / "lf-profile.json"
    path.write_text(registry.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr("migration_agent.adapters.workflow_cli.runtime_for", lambda *args: runtime)
    result = CliRunner().invoke(
        app,
        [
            "validation",
            "standards",
            step,
            "--project-root",
            str(runtime.proposals.root),
            "--plan",
            plan,
            "--registry",
            str(path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "PASS"
    assert runtime.store.get_workflow(record.project_id, plan, step) == record


def test_cli_registry_failure_does_not_open_runtime(tmp_path, monkeypatch):
    path = tmp_path / "invalid.json"
    path.write_text("{invalid}", encoding="utf-8")

    def unexpected(*args):
        pytest.fail("Malformed registry must be rejected before opening workflow state.")

    monkeypatch.setattr("migration_agent.adapters.workflow_cli.runtime_for", unexpected)
    result = CliRunner().invoke(
        app,
        [
            "validation",
            "standards",
            "step-1",
            "--project-root",
            str(tmp_path),
            "--plan",
            "plan-1",
            "--registry",
            str(path),
        ],
    )
    assert result.exit_code == 2
    assert "RULE_REGISTRY_INVALID" in result.output


def test_plan_change_during_review_invalidates_report(workflow):
    runtime, plan, step = workflow
    record = staged(workflow)

    class ChangingEvaluator(AngularRuleEvaluator):
        def evaluate(self, file, rule, execution):
            current = runtime.store.get_plan(plan)
            changed = current.steps[0].model_copy(update={"description": "concurrent plan change"})
            runtime.store.save_plan(
                current.model_copy(update={"steps": [changed, *current.steps[1:]]})
            )
            return super().evaluate(file, rule, execution)

    with pytest.raises(ValueError, match="STANDARDS_CONTEXT_CHANGED"):
        runtime.apply_service.review_standards(
            plan, step, load_rule_registry(), ChangingEvaluator()
        )
    assert runtime.store.get_workflow(record.project_id, plan, step) == record
