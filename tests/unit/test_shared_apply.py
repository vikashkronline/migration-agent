"""Phase 16C security scenarios using disposable Git repositories and human test doubles."""

import base64
import getpass
import io
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from access_fixture import WorkflowAuthorizationFixture
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from test_host_workflow import plan_proposal
from typer.testing import CliRunner

from migration_agent.adapters.approval_proof import LocalApprovalProof, public_key_fingerprint
from migration_agent.adapters.fenced_validation import FencedValidationRunner
from migration_agent.adapters.human_review import ConsoleHumanReview
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.workflow_runtime import WorkflowRuntime
from migration_agent.cli import app
from migration_agent.config import Settings
from migration_agent.domain.apply_approval import ApplyApprovalRecord, HumanDecision
from migration_agent.domain.changeset import ApplyStatus
from migration_agent.domain.execution import ExecutionPolicy, ExecutionProvenance, ValidationMode
from migration_agent.domain.host_workflow import Lifecycle, OperationStatus
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.trust import AuthorityKey, RepositoryBinding, TrustRecord
from migration_agent.domain.validation import (
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
)


class HumanFixture:
    def confirm(self, payload):
        assert payload.diff and payload.validation_digest
        return HumanDecision(
            confirmed=True, actor=getpass.getuser(), assurance=AssuranceLevel.MODE_B
        )


class ValidationFixture:
    # Explicit test gate exercises approval/apply mechanics. Production composition
    # never selects this gate or promotes an ordinary fake runner to evidence.
    def prepare(self, record, commands, lease):
        policy = ExecutionPolicy(
            mode=ValidationMode.CONTAINER,
            project_policy_digest=record.policy_digest,
            network="none",
            filesystem="container",
            supervision="test-harness",
        )
        return ExecutionProvenance(
            backend=ValidationMode.CONTAINER,
            policy=policy,
            policy_digest=policy.digest,
            input_digest=record.staging_fingerprint,
        )

    def completed(self, provenance, record, fence=None):
        if fence:
            fence()
        return provenance.model_copy(update={"cleanup_verified": True})

    def verify_execution(self, execution, record, fence=None):
        if fence:
            fence()
        assert execution.provenance.policy.supervision == "test-harness"

    def run(self, command, working_dir, fence):
        fence()
        assert working_dir.is_dir()
        return ValidationResult(
            command=command.rendered_command,
            profile=command.profile,
            status=ValidationStatus.PASSED,
            exit_code=0,
        )


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    authorization = WorkflowAuthorizationFixture()
    monkeypatch.setattr(
        "migration_agent.adapters.cli_access.ProjectAuthorization",
        lambda *args, **kwargs: authorization,
    )

    def authorized_runtime(binding, settings, state=None):
        return WorkflowRuntime(binding, settings, state, authorization=authorization)

    monkeypatch.setattr("migration_agent.adapters.workflow_cli.WorkflowRuntime", authorized_runtime)
    root = tmp_path / "repo"
    shutil.copytree(Path("tests/fixtures/ember-classic-mini"), root)
    for args in [
        ("init",),
        ("add", "."),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Fixture",
        ),
    ]:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    runtime = WorkflowRuntime(
        ProjectBinding(root),
        Settings(
            state_dir=tmp_path / "state",
            staging_root=tmp_path / "staging",
            trust_root=tmp_path / "trust",
        ),
        authorization=WorkflowAuthorizationFixture(),
    )
    proposal = plan_proposal(runtime.proposals)
    operation = runtime.proposals.submit_plan("plan", proposal)
    assert operation.status == OperationStatus.SUCCEEDED, operation.message
    yield runtime, operation.plan_id, proposal.steps[0].step_id
    runtime.close()


def validated(workflow):
    runtime, plan, step = workflow
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "fixture", ttl=900)
    try:
        record = runtime.apply_service.stage(plan, step, lease)
        assert record.state == Lifecycle.STAGE_VERIFIED
        gate = ValidationFixture()
        runtime.apply_service.execution_gate = gate
        runtime.apply_service.browser_gate = None  # Command/apply fixture, not browser acceptance.
        record = runtime.apply_service.validate(
            plan,
            step,
            (
                ValidationCommand(
                    executable="tsc", args=("--noEmit",), profile=ValidationProfile.TYPECHECK
                ),
            ),
            gate,
            lease,
        )
        assert record.state == Lifecycle.VALIDATION_PASSED
        return record
    finally:
        runtime.store.release_lease(lease)


def test_human_approval_preserves_clean_base_and_applies_once(workflow):
    record = validated(workflow)
    runtime, plan, step = workflow
    before = runtime.proposals.evidence.repository_state()
    with pytest.raises(ValueError, match="APPROVAL_REQUIRED"):
        runtime.apply_service.apply(plan, step, record.changeset_id)
    approval = runtime.apply_service.approve(plan, step, HumanFixture())
    assert runtime.proposals.evidence.repository_state() == before
    assert runtime.store.get_apply_approval(approval.nonce) == approval
    assert list((runtime.state / "runs" / record.run_id / "approvals").glob("*.json"))
    result = runtime.apply_service.apply(plan, step, record.changeset_id)
    assert result.status == ApplyStatus.APPLIED
    assert len(result.applied_paths) == 4
    assert Path(result.backup_snapshot_path).is_dir()
    with pytest.raises(ValueError, match="APPROVAL_REQUIRED"):
        runtime.store.get_apply_approval(approval.nonce)


def test_altered_changeset_and_staging_invalidate_approval(workflow):
    record = validated(workflow)
    runtime, plan, step = workflow
    runtime.apply_service.approve(plan, step, HumanFixture())
    cs = runtime.store.get_changeset(record.changeset_id)
    bad = cs.changes[0].model_copy(update={"content_bytes": b"altered\n"})
    runtime.store.save_changeset(cs.model_copy(update={"changes": (bad, *cs.changes[1:])}))
    with pytest.raises(ValueError, match="CHANGESET_INVALID"):
        runtime.apply_service.apply(plan, step, record.changeset_id)
    runtime.store.save_changeset(cs)
    (Path(record.staging_path) / cs.changes[0].path).write_text("altered\n")
    with pytest.raises(ValueError, match="STAGING_CHANGED"):
        runtime.apply_service.apply(plan, step, record.changeset_id)
    assert runtime.proposals.evidence.repository_state().clean


def test_stale_writer_cannot_mutate_after_new_generation(workflow):
    runtime, _, _ = workflow
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "A")
    with runtime.store._get_connection() as conn:
        conn.execute("UPDATE writer_leases SET expires_at=0")
    next_lease = runtime.store.acquire_lease(runtime.binding.project_id, "B")
    try:
        with pytest.raises(ValueError, match="LEASE_LOST"):
            runtime.files._write(
                runtime.binding.project_root,
                "stale.txt",
                b"bad",
                0o644,
                lambda: runtime.store.verify_lease(lease),
            )
        assert not (runtime.binding.project_root / "stale.txt").exists()
        assert next_lease.generation > lease.generation
    finally:
        runtime.store.release_lease(next_lease)


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_real_write_failure_rolls_back_or_requires_recovery(workflow, monkeypatch, rollback_fails):
    record = validated(workflow)
    runtime, plan, step = workflow
    runtime.apply_service.approve(plan, step, HumanFixture())
    write = runtime.files._write
    count = 0

    def fail(root, path, content, mode, fence):
        nonlocal count
        count += 1
        if count == 2:
            if rollback_fails:
                (runtime.binding.project_root / "intervening.txt").write_text("outside change")
            raise OSError("fixture write failure")
        return write(root, path, content, mode, fence)

    monkeypatch.setattr(runtime.files, "_write", fail)
    result = runtime.apply_service.apply(plan, step, record.changeset_id)
    assert result.status == (
        ApplyStatus.RECOVERY_REQUIRED if rollback_fails else ApplyStatus.ROLLED_BACK
    )
    assert (
        runtime.store.get_workflow(runtime.binding.project_id, plan, step).state
        == Lifecycle.RECOVERY_REQUIRED
    )
    if not rollback_fails:
        assert runtime.proposals.evidence.repository_state().clean
    recovery = CliRunner().invoke(
        app,
        [
            "recover",
            step,
            "--project-root",
            str(runtime.binding.project_root),
            "--plan",
            plan,
            "--state-dir",
            str(runtime.state),
            "--staging-root",
            str(runtime.staging),
        ],
    )
    assert recovery.exit_code == (2 if rollback_fails else 0), recovery.output
    expected = Lifecycle.RECOVERY_REQUIRED if rollback_fails else Lifecycle.BASE_CHANGED
    assert runtime.store.get_workflow(runtime.binding.project_id, plan, step).state == expected


def test_dirty_base_and_expired_approval_fail_before_write(workflow):
    record = validated(workflow)
    runtime, plan, step = workflow
    approval = runtime.apply_service.approve(plan, step, HumanFixture())
    expired = approval.model_copy(
        update={
            "created_at": datetime.now(UTC) - timedelta(hours=2),
            "expires_at": datetime.now(UTC) - timedelta(hours=1),
        }
    )
    with runtime.store._get_connection() as conn:
        conn.execute(
            "UPDATE apply_approvals SET content_json=? WHERE nonce=?",
            (expired.model_dump_json(), approval.nonce),
        )
    with pytest.raises(ValueError, match="APPROVAL_INVALID"):
        runtime.apply_service.apply(plan, step, record.changeset_id)
    (runtime.binding.project_root / "human.txt").write_text("WIP")
    with pytest.raises(ValueError, match="BASE_CHANGED"):
        runtime.apply_service.apply(plan, step, record.changeset_id)
    assert (
        runtime.store.get_workflow(runtime.binding.project_id, plan, step).state
        == Lifecycle.BASE_CHANGED
    )


def test_console_rejects_noninteractive_automatic_confirmation(workflow, monkeypatch):
    record = validated(workflow)
    runtime, plan, step = workflow
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(ValueError, match="HUMAN_CONSOLE_REQUIRED"):
        runtime.apply_service.approve(plan, step, ConsoleHumanReview())
    record = runtime.store.get_workflow(runtime.binding.project_id, plan, step)
    assert record.state == Lifecycle.APPROVAL_PENDING and record.approval_nonce is None


def test_mode_a_ignores_in_repo_keys_and_verifies_real_ed25519(workflow):
    runtime, _, _ = workflow
    state = runtime.proposals.evidence.repository_state()
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
    fingerprint = public_key_fingerprint(public)
    authority = TrustRecord(
        project_id=runtime.binding.project_id,
        repository_binding=RepositoryBinding(root_commit_sha=state.root_commit),
        authority_keys=(
            AuthorityKey(
                key_id="fixture",
                public_key=public,
                fingerprint=fingerprint,
                created_at="2026-10-04",
            ),
        ),
    )
    record = ApplyApprovalRecord(
        project_id=runtime.binding.project_id,
        run_id="run",
        plan_id="plan",
        step_id="step",
        changeset_id="cs",
        changeset_digest="digest",
        policy_digest="policy",
        base_revision=state.revision,
        worktree_fingerprint=state.fingerprint,
        validation_digest="val",
        actor="fixture",
        assurance_level=AssuranceLevel.MODE_A,
        key_fingerprint=fingerprint,
        nonce="nonce",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    record = record.model_copy(
        update={
            "signature": "ed25519-base64:"
            + base64.b64encode(private.sign(record.signing_digest.encode())).decode()
        }
    )
    proof = LocalApprovalProof(runtime.trust, runtime.state)
    source_authority = runtime.binding.project_root / ".agent" / "trust.json"
    source_authority.parent.mkdir()
    source_authority.write_text(authority.model_dump_json())
    assert not proof.verify(record, state.root_commit)
    runtime.trust.mkdir()
    path = runtime.trust / f"{runtime.binding.project_id}.json"
    path.write_text(authority.model_dump_json())
    assert proof.verify(record, state.root_commit)
    assert not proof.verify(record, "different-root")
    assert not proof.verify(
        record.model_copy(update={"changeset_digest": "altered"}), state.root_commit
    )
    path.write_text(
        authority.model_copy(
            update={
                "authority_keys": (
                    authority.authority_keys[0].model_copy(update={"revoked": True}),
                )
            }
        ).model_dump_json()
    )
    assert not proof.verify(record, state.root_commit)


def test_production_validation_requires_isolation(workflow):
    runtime, plan, step = workflow
    operation = runtime.dispatch("stage", plan, step, "stage", background=False)
    assert operation.status == OperationStatus.SUCCEEDED
    validation = runtime.dispatch(
        "validate", plan, step, "validate", profile="TYPECHECK", background=False
    )
    assert (
        validation.status == OperationStatus.FAILED and "ISOLATION_REQUIRED" in validation.message
    )
    assert runtime.proposals.evidence.repository_state().clean
    assert (
        runtime.dispatch("validate", plan, step, "validate", profile="TYPECHECK", background=False)
        == validation
    )


def test_fenced_runner_executes_bounded_offline_fixture(workflow):
    runtime, plan, step = workflow
    runtime.dispatch("stage", plan, step, "stage", background=False)
    record = runtime.store.get_workflow(runtime.binding.project_id, plan, step)
    Path(record.staging_path, "fixture_test.py").write_text("def test_ok():\n    assert True\n")
    command = ValidationCommand(
        executable="pytest",
        args=("-q", "-p", "no:cacheprovider", "fixture_test.py"),
        profile=ValidationProfile.TEST,
    )
    runner = FencedValidationRunner(runtime.staging, permitted=(command,))
    result = runner.run(command, Path(record.staging_path), lambda: None)
    assert result.status == ValidationStatus.PASSED, result.sanitized_output
    assert len(result.sanitized_output.encode()) <= 65536
    with pytest.raises(ValueError, match="COMMAND_REJECTED"):
        runner.run(
            command.model_copy(update={"args": ("--invalid",)}),
            Path(record.staging_path),
            lambda: None,
        )


def test_cli_human_confirmation_then_shared_apply(workflow, monkeypatch):
    record = validated(workflow)
    runtime, plan, step = workflow
    from migration_agent.adapters.workflow_cli import runtime_for

    def fixture_runtime(*args, **kwargs):
        selected = runtime_for(*args, **kwargs)
        selected.apply_service.execution_gate = ValidationFixture()
        selected.apply_service.browser_gate = None  # Explicit CLI approval test harness.
        return selected

    monkeypatch.setattr("migration_agent.adapters.workflow_cli.runtime_for", fixture_runtime)
    monkeypatch.setattr(
        ConsoleHumanReview, "confirm", lambda self, review: HumanFixture().confirm(review)
    )
    options = ["--state-dir", str(runtime.state), "--staging-root", str(runtime.staging)]
    result = CliRunner().invoke(
        app,
        [
            "approve",
            step,
            "--project-root",
            str(runtime.binding.project_root),
            "--plan",
            plan,
            *options,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "APPROVAL_RECORDED" in result.output
    assert runtime.proposals.evidence.repository_state().clean
    applied = CliRunner().invoke(
        app,
        [
            "apply",
            str(runtime.binding.project_root),
            "--plan",
            plan,
            "--changeset",
            record.changeset_id,
            *options,
        ],
    )
    assert applied.exit_code == 0, applied.output
    assert (
        runtime.store.get_workflow(runtime.binding.project_id, plan, step).state
        == Lifecycle.APPLY_COMPLETED
    )


def test_immutable_validation_provenance_cannot_be_forged(workflow):
    validated(workflow)
    runtime, plan, step = workflow
    with runtime.store._get_connection() as conn:
        conn.execute("UPDATE validation_executions SET content_json='{}'")
    with pytest.raises(ValueError):
        runtime.apply_service.approve(plan, step, HumanFixture())
    assert runtime.store.get_workflow(runtime.binding.project_id, plan, step).approval_nonce is None


def test_missing_planned_validation_profile_blocks_approval(workflow):
    runtime, plan, step = workflow
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "fixture", ttl=900)
    try:
        runtime.apply_service.stage(plan, step, lease)
        runtime.apply_service.validate(
            plan,
            step,
            (ValidationCommand(executable="pytest", args=("-q",), profile=ValidationProfile.TEST),),
            ValidationFixture(),
            lease,
        )
    finally:
        runtime.store.release_lease(lease)
    with pytest.raises(ValueError, match="VALIDATION_REQUIRED"):
        runtime.apply_service.approve(plan, step, HumanFixture())
    assert runtime.store.get_workflow(runtime.binding.project_id, plan, step).approval_nonce is None


def test_repository_tools_cannot_impersonate_git_or_docker(workflow, monkeypatch):
    runtime, plan, step = workflow
    staged = runtime.dispatch("stage", plan, step, "stage", background=False)
    assert staged.status == OperationStatus.SUCCEEDED
    record = runtime.store.get_workflow(runtime.binding.project_id, plan, step)
    source = runtime.binding.project_root
    monkeypatch.setattr("shutil.which", lambda name, **_: str(source / f"{name}.exe"))
    with pytest.raises(ValueError, match="EXECUTABLE_UNTRUSTED"):
        runtime.proposals.evidence.repository_state()
    runner = FencedValidationRunner(
        runtime.staging, source_root=source, container_image="fixture/toolchain@sha256:" + "a" * 64
    )
    command = ValidationCommand(
        executable="tsc", args=("--noEmit",), profile=ValidationProfile.TYPECHECK
    )
    with pytest.raises(ValueError, match="EXECUTABLE_UNTRUSTED"):
        runner.run(command, Path(record.staging_path), lambda: None)


@pytest.mark.parametrize("cleanup", ["removed", "already-removed", "unverified"])
def test_container_cleanup_is_verified_before_validation_success(tmp_path, monkeypatch, cleanup):
    source = tmp_path / "source"
    source.mkdir()
    staging = tmp_path / "staging"
    work = staging / "workspace"
    work.mkdir(parents=True)
    runner = FencedValidationRunner(
        staging, source_root=source, container_image="fixture/toolchain@sha256:" + "a" * 64
    )
    monkeypatch.setattr("shutil.which", lambda *args, **kwargs: str(Path(__file__).resolve()))
    launches = []

    class ProcessFixture:
        stdout = io.BytesIO(b"fixture validation\n")
        stderr = io.BytesIO()

        def poll(self):
            return 0

        def wait(self, **kwargs):
            return 0

    def launch(args, **kwargs):
        launches.append(args)
        assert not kwargs["shell"]
        assert "OPENAI_API_KEY" not in kwargs["env"]
        return ProcessFixture()

    def remove(args, **kwargs):
        assert args[1:3] == ["rm", "--force"]
        return subprocess.CompletedProcess(
            args,
            0 if cleanup == "removed" else 1,
            b"",
            b"No such container: fixture"
            if cleanup == "already-removed"
            else b"daemon unavailable",
        )

    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(subprocess, "run", remove)
    monkeypatch.setattr(runner, "_stop", lambda process: None)
    command = ValidationCommand(
        executable="tsc", args=("--noEmit",), profile=ValidationProfile.TYPECHECK
    )
    if cleanup == "unverified":
        with pytest.raises(ValueError, match="CONTAINER_CLEANUP_UNVERIFIED"):
            runner.run(command, work, lambda: None)
    else:
        assert runner.run(command, work, lambda: None).status == ValidationStatus.PASSED
    assert "--network=none" in launches[0] and "--read-only" in launches[0]
    assert "--cap-drop=ALL" in launches[0] and "--security-opt=no-new-privileges" in launches[0]
    assert "--pull=never" in launches[0] and "--user=65534:65534" in launches[0]
    assert (
        f"source={work.resolve()},target=/workspace,readonly"
        in launches[0][launches[0].index("--mount") + 1]
    )


def test_repair_changes_identity_and_requires_revalidation(workflow):
    from migration_agent.domain.canonical import compute_canonical_digest
    from migration_agent.domain.host_workflow import RepairFile, RepairProposal

    runtime, plan, step = workflow
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "fixture", ttl=900)

    class FailedFixture:
        def run(self, command, working_dir, fence):
            fence()
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=ValidationStatus.FAILED,
                exit_code=1,
                diagnostics=("fixture failure",),
            )

    try:
        runtime.apply_service.stage(plan, step, lease)
        record = runtime.apply_service.validate(
            plan,
            step,
            (
                ValidationCommand(
                    executable="tsc", args=("--noEmit",), profile=ValidationProfile.TYPECHECK
                ),
            ),
            FailedFixture(),
            lease,
        )
    finally:
        runtime.store.release_lease(lease)
    cs = runtime.store.get_changeset(record.changeset_id)
    proposal = RepairProposal(
        plan_id=plan,
        step_id=step,
        changeset_id=record.changeset_id,
        diagnostic_digest=compute_canonical_digest(
            [r.model_dump(mode="json") for r in record.validation_results]
        ),
        files=(
            RepairFile(
                path=cs.changes[0].path,
                text=cs.changes[0].content_bytes.decode() + "\n// fixture repair\n",
            ),
        ),
    )
    path = runtime.state / "repair-proposal.json"
    path.write_text(proposal.model_dump_json(), encoding="utf-8")
    submitted = CliRunner().invoke(
        app,
        [
            "submit-repair",
            str(path),
            "--project-root",
            str(runtime.binding.project_root),
            "--state-dir",
            str(runtime.state),
            "--staging-root",
            str(runtime.staging),
            "--request-id",
            "repair",
        ],
    )
    assert submitted.exit_code == 0, submitted.output
    assert json.loads(submitted.output)["status"] == "SUCCEEDED"
    repaired = runtime.store.get_workflow(runtime.binding.project_id, plan, step)
    assert repaired.state == Lifecycle.REPAIRING and repaired.changeset_id != cs.changeset_id
    assert repaired.validation_digest is None and repaired.approval_nonce is None
    with pytest.raises(ValueError, match="VALIDATION_REQUIRED"):
        runtime.apply_service.approve(plan, step, HumanFixture())
    assert (
        runtime.dispatch("stage", plan, step, "restage", background=False).status
        == OperationStatus.SUCCEEDED
    )


@pytest.mark.parametrize(
    "outcome,budget,expected_attempts",
    [
        ("fixed", 3, 1),
        ("repeated", 3, 1),
        ("budget", 1, 1),
        ("disabled", 0, 0),
    ],
)
def test_standalone_repair_uses_shared_gates(workflow, outcome, budget, expected_attempts):
    from migration_agent.adapters import FakeCommandRunner, LocalWorkspaceAdapter
    from migration_agent.application.validation import BoundedRepairService

    runtime, plan_id, step = workflow

    class CompilerFixture:
        checks = 0

        def run(self, command, working_dir, fence):
            fence()
            failing = False
            diagnostic = ""
            if command.profile == ValidationProfile.TYPECHECK:
                self.checks += 1
                failing = outcome != "fixed" or self.checks == 1
                symbol = "FormsModule" if outcome == "budget" and self.checks > 1 else "HttpClient"
                target = next(working_dir.rglob("*.component.ts"))
                path = target.relative_to(working_dir).as_posix()
                diagnostic = f"{path}(1,1): error TS2304: Cannot find name '{symbol}'."
            return ValidationResult(
                command=command.rendered_command,
                profile=command.profile,
                status=ValidationStatus.FAILED if failing else ValidationStatus.PASSED,
                exit_code=1 if failing else 0,
                sanitized_output=diagnostic if failing else "",
                diagnostics=(diagnostic,) if failing else (),
            )

    runtime.runner = CompilerFixture()
    service = BoundedRepairService(
        FakeCommandRunner(),
        LocalWorkspaceAdapter(),
        max_budget=3,
        checkpoint_store=runtime.store,
    )
    record, attempts = service.prepare_workflow(
        runtime, runtime.store.get_plan(plan_id), step, False, budget
    )
    assert len(attempts) == expected_attempts
    assert runtime.runner.checks == expected_attempts + 1
    assert record.approval_nonce is None
    assert runtime.proposals.evidence.repository_state().clean
    if outcome == "fixed":
        assert record.state == Lifecycle.VALIDATION_PASSED and record.validation_digest
        changeset = runtime.current_changeset(record.changeset_id)
        assert any(b"import { HttpClient }" in (c.content_bytes or b"") for c in changeset.changes)
        assert attempts[0].previous_changeset_digest != attempts[0].new_changeset_digest
        assert runtime.store.get_validation_execution(record.validation_digest)
    else:
        assert record.state == Lifecycle.VALIDATION_FAILED
        with pytest.raises(ValueError, match="VALIDATION_REQUIRED"):
            runtime.apply_service.approve(plan_id, step, HumanFixture())


def test_standalone_repair_runtime_guidance_stays_in_scope(workflow):
    from migration_agent.adapters import FakeCommandRunner, LocalWorkspaceAdapter
    from migration_agent.application.validation import BoundedRepairService
    from migration_agent.domain.specialists import RepairDiagnosis

    runtime, plan_id, step = workflow

    class CompilerFixture(ValidationFixture):
        checks = 0

        def run(self, command, working_dir, fence):
            result = super().run(command, working_dir, fence)
            if command.profile == ValidationProfile.TYPECHECK:
                self.checks += 1
                if self.checks == 1:
                    return result.model_copy(
                        update={
                            "status": ValidationStatus.FAILED,
                            "exit_code": 1,
                            "diagnostics": ("unknown compiler diagnostic",),
                        }
                    )
            return result

    class RuntimeFixture:
        called = False

        def diagnose_repair(self, request):
            self.called = True
            assert request.failing_result.exit_code == 1
            target = next(
                path
                for path in request.allowed_scope
                if path.endswith(".ts") and not path.endswith(".spec.ts")
            )
            return RepairDiagnosis(
                root_cause_category="MISSING_IMPORT",
                actionable=True,
                confidence=0.9,
                suggested_file=target,
                diagnostic_details=f"{target}(1,1): error TS2304: Cannot find name 'HttpClient'.",
                suggested_fix_summary="Add the known Angular import.",
            )

    runtime.runner = CompilerFixture()
    specialist = RuntimeFixture()
    service = BoundedRepairService(
        FakeCommandRunner(),
        LocalWorkspaceAdapter(),
        specialist_runtime=specialist,
    )
    record, attempts = service.prepare_workflow(
        runtime, runtime.store.get_plan(plan_id), step, False, 2
    )
    assert specialist.called and len(attempts) == 1
    assert record.state == Lifecycle.VALIDATION_PASSED
    assert record.approval_nonce is None and runtime.proposals.evidence.repository_state().clean


def test_validate_blocks_when_prerequisites_not_applied(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(Path("tests/fixtures/ember-classic-mini"), root)
    for args in [
        ("init",),
        ("add", "."),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "Fixture",
        ),
    ]:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    runtime = WorkflowRuntime(
        ProjectBinding(root),
        Settings(
            state_dir=tmp_path / "state",
            staging_root=tmp_path / "staging",
            trust_root=tmp_path / "trust",
        ),
        authorization=WorkflowAuthorizationFixture(),
    )
    base_proposal = plan_proposal(runtime.proposals)
    step1 = base_proposal.steps[0]
    step2 = step1.model_copy(update={"step_id": "step-2", "dependencies": [step1.step_id]})
    proposal = base_proposal.model_copy(update={"steps": (step1, step2)})
    operation = runtime.proposals.submit_plan("two-step-plan", proposal)
    assert operation.status == OperationStatus.SUCCEEDED
    plan_id = operation.plan_id

    lease = runtime.store.acquire_lease(runtime.binding.project_id, "dep-fixture", ttl=900)
    try:
        runtime.apply_service.stage(plan_id, step1.step_id, lease)
        runtime.apply_service.stage(plan_id, step2.step_id, lease)

        gate = ValidationFixture()
        runtime.apply_service.execution_gate = gate
        runtime.apply_service.browser_gate = None
        with pytest.raises(ValueError, match="DEPENDENCY_NOT_READY"):
            runtime.apply_service.validate(
                plan_id,
                step2.step_id,
                (
                    ValidationCommand(
                        executable="tsc",
                        args=("--noEmit",),
                        profile=ValidationProfile.TYPECHECK,
                    ),
                ),
                gate,
                lease,
            )
    finally:
        runtime.store.release_lease(lease)
        runtime.close()
