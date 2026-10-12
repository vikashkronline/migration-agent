"""Grounded host generation, scope protection and cumulative target publication."""

from test_destination_workflow import separate
from test_shared_apply import HumanFixture, ValidationFixture
from test_shared_apply import workflow as workflow

from migration_agent.adapters.foundation_transformation import (
    BoundFoundationTransformationAdapter,
    FoundationTransformationAdapter,
)
from migration_agent.domain.host_workflow import (
    ImplementationFile,
    ImplementationProposal,
    OperationStatus,
)
from migration_agent.domain.validation import ValidationCommand, ValidationProfile


def foundation(workflow, tmp_path):
    separate(workflow, tmp_path)
    runtime, plan_id, _ = workflow
    original = runtime.store.get_plan(plan_id)
    step = original.steps[0].model_copy(update={"step_id": "foundation", "scope": "foundation"})
    plan = original.model_copy(
        update={"plan_id": "foundation-plan", "run_id": "foundation-run", "steps": [step]}
    )
    runtime.store.save_plan(plan)
    runtime.apply_service.foundation_contract = lambda: "fixture-accepted-architecture"
    runtime.apply_service.foundation_paths = frozenset(
        BoundFoundationTransformationAdapter.configuration_paths
    )
    runtime.apply_service.transformation.foundation_adapter = FoundationTransformationAdapter()
    gate = ValidationFixture()
    runtime.apply_service.execution_gate = gate
    runtime.apply_service.browser_gate = None
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "foundation-fixture")
    try:
        record = runtime.apply_service.stage(plan.plan_id, step.step_id, lease)
        runtime.apply_service.validate(
            plan.plan_id,
            step.step_id,
            (
                ValidationCommand(
                    executable="tsc", args=("--noEmit",), profile=ValidationProfile.TYPECHECK
                ),
            ),
            gate,
            lease,
        )
    finally:
        runtime.store.release_lease(lease)
    runtime.apply_service.approve(plan.plan_id, step.step_id, HumanFixture())
    runtime.apply_service.apply(plan.plan_id, step.step_id, record.changeset_id)


def implementation(workflow):
    runtime, plan_id, _ = workflow
    original = runtime.store.get_plan(plan_id)
    step = original.steps[0].model_copy(
        update={
            "step_id": "feature",
            "scope": "implementation",
            "target_files": ["src/app/features/feature.txt"],
            "acceptance_criteria": ["Preserve the fixture behavior"],
        }
    )
    plan = original.model_copy(
        update={"plan_id": "implementation-plan", "run_id": "implementation-run", "steps": [step]}
    )
    runtime.store.save_plan(plan)
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "context-fixture")
    try:
        context = runtime.apply_service.implementation_context(plan.plan_id, step.step_id, lease)
    finally:
        runtime.store.release_lease(lease)
    return ImplementationProposal(
        plan_id=plan.plan_id,
        step_id=step.step_id,
        base_revision=context.base_revision,
        worktree_fingerprint=context.worktree_fingerprint,
        destination=context.destination,
        architecture_digest=context.architecture_digest,
        citations=context.citations,
        files=(
            ImplementationFile(path=step.target_files[0], text="fixture-generated implementation"),
        ),
    )


def test_grounded_implementation_is_idempotent_and_requires_separate_validation(workflow, tmp_path):
    foundation(workflow, tmp_path)
    runtime, _, _ = workflow
    source_before = runtime.proposals.evidence.repository_state()
    proposal = implementation(workflow)
    first = runtime.apply_service.submit_implementation("generated-feature", proposal)
    assert first.status == OperationStatus.SUCCEEDED, first.message
    assert (
        runtime.apply_service.submit_implementation("generated-feature", proposal).operation_id
        == first.operation_id
    )
    record = runtime.store.get_workflow(
        runtime.binding.project_id, proposal.plan_id, proposal.step_id
    )
    assert record.validation_digest is None and record.approval_nonce is None
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "stage-generated")
    try:
        staged = runtime.apply_service.stage(proposal.plan_id, proposal.step_id, lease)
        runtime.apply_service.validate(
            proposal.plan_id,
            proposal.step_id,
            (
                ValidationCommand(
                    executable="tsc", args=("--noEmit",), profile=ValidationProfile.TYPECHECK
                ),
            ),
            runtime.apply_service.execution_gate,
            lease,
        )
    finally:
        runtime.store.release_lease(lease)
    runtime.apply_service.approve(proposal.plan_id, proposal.step_id, HumanFixture())
    runtime.apply_service.apply(proposal.plan_id, proposal.step_id, staged.changeset_id)
    target = runtime.files.write_root
    assert (
        target / "src/app/features/feature.txt"
    ).read_text() == "fixture-generated implementation"
    assert (target / "angular.json").is_file()
    assert runtime.proposals.evidence.repository_state() == source_before


def test_generation_rejects_foreign_files_and_source_citations(workflow, tmp_path):
    foundation(workflow, tmp_path)
    runtime, _, _ = workflow
    proposal = implementation(workflow)
    bad = proposal.model_copy(
        update={"files": (ImplementationFile(path="src/app/undeclared.txt", text="unapproved"),)}
    )
    result = runtime.apply_service.submit_implementation("wrong-scope", bad)
    assert (
        result.status == OperationStatus.FAILED and "IMPLEMENTATION_SCOPE_INVALID" in result.message
    )
    bad = proposal.model_copy(
        update={"citations": (proposal.citations[0].model_copy(update={"sha256": "0" * 64}),)}
    )
    result = runtime.apply_service.submit_implementation("wrong-evidence", bad)
    assert result.status == OperationStatus.FAILED and "EVIDENCE_CHANGED" in result.message
    assert (
        runtime.store.get_workflow(
            runtime.binding.project_id, proposal.plan_id, proposal.step_id
        ).changeset_id
        is None
    )
