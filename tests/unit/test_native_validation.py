"""Offline native evidence, consent and Windows process lifecycle scenarios."""

import ctypes
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_shared_apply import HumanFixture, ValidationFixture
from test_shared_apply import workflow as workflow

from migration_agent.adapters.fenced_validation import VALIDATION_COMMANDS
from migration_agent.adapters.human_review import ConsoleHumanReview
from migration_agent.adapters.native_process import WindowsJobProcess
from migration_agent.adapters.validation_backend import ValidationBackend, tree_digest
from migration_agent.config import Settings
from migration_agent.domain.execution import NativeExecutionConsent, ValidationMode
from migration_agent.domain.host_workflow import Lifecycle
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.validation import ValidationProfile


@pytest.fixture
def native(workflow, tmp_path):
    if sys.platform == "linux" and os.geteuid() == 0:
        pytest.skip("Native integration requires a standard non-root account.")
    if sys.platform == "win32" and ctypes.WinDLL("shell32").IsUserAnAdmin():
        pytest.skip("Native integration requires a standard non-elevated account.")
    runtime, plan, step = workflow
    node = shutil.which("node")
    if not node:
        pytest.skip("Offline native integration requires installed Node.")
    root = tmp_path / "tool chain Ω"
    root.mkdir()
    target_node = root / ("node.exe" if os.name == "nt" else "bin/node")
    target_node.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(node, target_node)
    target_node.chmod(0o755)
    script = """
const fs = require('fs');
if (process.env.OPENAI_API_KEY || process.env.NODE_OPTIONS || process.env.SSH_AUTH_SOCK) {
  throw Error('credential environment inherited');
}
fs.mkdirSync('dist', {recursive: true});
fs.writeFileSync('dist/result.txt', 'output');
console.log('offline native check');
"""
    for relative in ("npm/bin/npm-cli.js", "typescript/bin/tsc", "@angular/cli/bin/ng.js"):
        target = root / "node_modules" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(script, encoding="utf-8")
    dependencies = tmp_path / "offline dependencies"
    dependencies.mkdir()
    (dependencies / "fixture.json").write_text('{"approved":true}', encoding="utf-8")
    settings = runtime.settings.model_copy(
        update={
            "validation_mode": ValidationMode.NATIVE,
            "native_toolchain_root": root,
            "native_dependencies_root": dependencies,
            "validation_image": "leftover-image",
        }
    )
    runtime.settings = settings
    runtime.runner = ValidationBackend(
        settings, runtime.proposals, runtime.store, runtime.staging, runtime.state, runtime.trust
    )
    runtime.apply_service.execution_gate = runtime.runner
    runtime.apply_service.browser_gate = (
        None  # Native process tests have separate browser coverage.
    )
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "native-fixture", ttl=900)
    record = runtime.apply_service.stage(plan, step, lease)
    commands = tuple(command for values in VALIDATION_COMMANDS.values() for command in values)
    yield runtime, record, commands, lease
    runtime.store.release_lease(lease)


def authorize(native, repair_budget=0):
    runtime, record, commands, lease = native
    consent = runtime.runner.consent_request(record, commands, repair_budget)
    consent = consent.model_copy(update={"signature": runtime.runner.proof.sign(consent)})
    runtime.store.save_native_consent(consent, lease)
    return consent


def validate(native):
    runtime, record, commands, lease = native
    return runtime.apply_service.validate(
        record.plan_id, record.step_id, commands, runtime.runner, lease
    )


def test_selection_is_explicit_and_image_compatible():
    assert (
        Settings(validation_mode=None, validation_image=None).effective_validation_mode
        == ValidationMode.RESTRICTED
    )
    assert (
        Settings(validation_mode=None, validation_image="pinned").effective_validation_mode
        == ValidationMode.CONTAINER
    )
    assert (
        Settings(
            validation_mode=ValidationMode.NATIVE, validation_image="pinned"
        ).effective_validation_mode
        == ValidationMode.NATIVE
    )


@pytest.mark.parametrize("mode", ["restricted", "native", "container"])
@pytest.mark.parametrize("entry", ["validate", "run", "resume"])
def test_legacy_live_entry_points_cannot_bypass_execution_consent(
    tmp_path, monkeypatch, mode, entry
):
    from typer.testing import CliRunner

    from migration_agent.cli import app

    monkeypatch.setenv("AGENT_VALIDATION_MODE", mode)
    monkeypatch.setattr(
        "migration_agent.adapters.command_runner.SubprocessCommandRunner.run_command",
        lambda *args: pytest.fail("unapproved legacy execution"),
    )
    args = (
        ["validate", str(tmp_path)]
        if entry == "validate"
        else ["run", str(tmp_path), "--plan", "fixture"]
        if entry == "run"
        else ["run", "resume", "unknown"]
    )
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert "ACCESS_BOOTSTRAP_REQUIRED" in result.output


def test_native_selection_alone_never_authorizes_execution(native, monkeypatch):
    monkeypatch.setattr(
        "migration_agent.adapters.validation_backend.launch_native",
        lambda *a: pytest.fail("must not launch"),
    )
    with pytest.raises(ValueError, match="NATIVE_CONSENT_REQUIRED"):
        validate(native)


def test_dependency_copy_checks_consent_at_bounded_checkpoints(native, monkeypatch):
    runtime, record, commands, lease = native
    dependencies = runtime.settings.native_dependencies_root
    for index in range(130):
        (dependencies / f"module-{index:03}.json").write_text("{}", encoding="utf-8")
    authorize(native)
    original = runtime.runner._consent
    checks = []

    def checked(*args, **kwargs):
        checks.append(kwargs.get("verify_inputs", True))
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime.runner, "_consent", checked)
    monkeypatch.setattr("migration_agent.adapters.validation_backend.time.monotonic", lambda: 100)
    runtime.runner.prepare(record, commands, lease)
    assert len(checks) == 5  # Initial verification, files 0/64/128, completion.
    assert len(list((Path(record.staging_path) / "node_modules").glob("*.json"))) == 131


def test_dependency_hash_reuses_only_the_exact_verified_toolchain_tree(native, monkeypatch):
    from migration_agent.domain.execution import ToolIdentity

    runtime, _, _, _ = native
    dependencies = runtime.settings.native_dependencies_root
    identity = ToolIdentity(path=str(dependencies), sha256="1" * 64)
    calls = []

    def fingerprint(path):
        calls.append(path)
        return "2" * 64

    monkeypatch.setattr("migration_agent.adapters.validation_backend.tree_digest", fingerprint)
    assert runtime.runner._dependency_digest((identity,)) == "1" * 64
    assert not calls
    foreign = identity.model_copy(update={"path": str(dependencies.parent / "other")})
    assert runtime.runner._dependency_digest((foreign,)) == "2" * 64
    assert calls == [dependencies]


def test_opened_file_escape_is_rejected_before_reading_bytes(tmp_path, monkeypatch):
    import io

    from migration_agent.adapters.validation_backend import file_digest

    root = tmp_path / "inputs"
    root.mkdir()
    path = root / "module.js"
    path.write_text("approved", encoding="utf-8")

    class GuardedBytes(io.BytesIO):
        def read(self, *args):
            pytest.fail("escaped file contents must never be read")

    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: GuardedBytes())
    monkeypatch.setattr(
        "migration_agent.adapters.validation_backend._opened_path",
        lambda handle: tmp_path / "outside/module.js",
    )
    with pytest.raises(ValueError, match="NATIVE_PATH_UNSAFE"):
        file_digest(path, root)


def test_input_fingerprinting_cancellation_stops_before_file_reads(tmp_path, monkeypatch):
    root = tmp_path / "inputs"
    root.mkdir()
    (root / "module.js").write_text("approved", encoding="utf-8")
    clock = iter(range(100, 200))
    monkeypatch.setattr(
        "migration_agent.adapters.validation_backend.time.monotonic", lambda: next(clock)
    )
    calls = []

    def fence():
        calls.append(True)
        if len(calls) == 2:
            raise ValueError("CANCEL_REQUESTED")

    monkeypatch.setattr(
        "migration_agent.adapters.validation_backend.file_digest",
        lambda *args: pytest.fail("cancelled fingerprint cannot read file contents"),
    )
    with pytest.raises(ValueError, match="CANCEL_REQUESTED"):
        tree_digest(root, fence=fence)
    assert len(calls) == 2


def test_native_evidence_inspection_requires_read_capability_without_running_code(
    native, monkeypatch
):
    from migration_agent.domain.access import AccessDenied

    runtime, _, _, _ = native
    authorize(native)
    record = validate(native)
    execution = runtime.store.get_validation_execution(record.validation_digest)
    original = runtime.proposals.authorization.require

    def inspection(capability, expected_digest=None):
        if capability == "validation.run":
            raise AccessDenied("CAPABILITY_DENIED: read-only review")
        return original(capability, expected_digest)

    monkeypatch.setattr(runtime.proposals.authorization, "require", inspection)
    monkeypatch.setattr(
        "migration_agent.adapters.validation_backend.launch_native",
        lambda *args: pytest.fail("evidence inspection cannot execute application code"),
    )
    runtime.runner.verify_execution(execution, record)


@pytest.mark.parametrize(
    "failure",
    [
        "expired",
        "revoked",
        "forged",
        "toolchain",
        "dependencies",
        "configuration",
        "scope",
        "policy",
    ],
)
def test_invalid_consent_fails_before_launch(native, monkeypatch, failure):
    runtime, record, _commands, _lease = native
    consent = authorize(native)
    if failure == "revoked":
        runtime.store.revoke_native_consent(record.project_id, consent.consent_id)
    elif failure in {"expired", "forged"}:
        updated = (
            consent.model_copy(
                update={
                    "created_at": datetime.now(UTC) - timedelta(hours=1),
                    "expires_at": datetime.now(UTC) - timedelta(seconds=1),
                }
            )
            if failure == "expired"
            else consent.model_copy(update={"signature": "forged"})
        )
        with runtime.store._get_connection() as connection:
            connection.execute(
                "UPDATE native_consents SET content_json=? WHERE consent_id=?",
                (updated.model_dump_json(), consent.consent_id),
            )
    elif failure == "toolchain":
        entry = runtime.settings.native_toolchain_root / "node_modules/typescript/bin/tsc"
        entry.write_text("changed", encoding="utf-8")
    elif failure == "dependencies":
        (runtime.settings.native_dependencies_root / "changed.json").write_text(
            "{}", encoding="utf-8"
        )
    elif failure == "configuration":
        (Path(record.staging_path) / "tsconfig.json").write_text("{}", encoding="utf-8")
    elif failure == "scope":
        monkeypatch.setattr(runtime.runner, "_scope", lambda _: ("outside.ts",))
    else:
        original = runtime.proposals.evidence.policy()
        monkeypatch.setattr(
            runtime.proposals.evidence,
            "policy",
            lambda: original.model_copy(update={"execution_mode": "container"}),
        )
    monkeypatch.setattr(
        "migration_agent.adapters.validation_backend.launch_native",
        lambda *a: pytest.fail("must not launch"),
    )
    with pytest.raises(ValueError, match=r"NATIVE_CONSENT|EXECUTION_POLICY|STAGING_CHANGED"):
        validate(native)


def test_native_all_profiles_without_docker_separate_approval_apply_once(native, monkeypatch):
    runtime, _staged, _commands, lease = native
    authorize(native)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-credential")
    monkeypatch.setenv("NODE_OPTIONS", "--require=untrusted-startup.js")
    monkeypatch.setenv("SSH_AUTH_SOCK", "synthetic-agent")
    original_which = shutil.which

    def trusted_git_only(name, *args, **kwargs):
        if name != "git":
            pytest.fail("native must not discover Docker or PATH executables")
        return original_which(name, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", trusted_git_only)
    record = validate(native)
    assert record.state == Lifecycle.VALIDATION_PASSED
    evidence = runtime.store.get_validation_execution(record.validation_digest)
    assert evidence.schema_version == 2
    assert evidence.provenance.backend == ValidationMode.NATIVE
    assert evidence.provenance.cleanup_verified
    assert {result.profile for result in evidence.results} == set(ValidationProfile)
    assert (Path(record.staging_path) / "dist/result.txt").read_text() == "output"
    monkeypatch.undo()
    runtime.store.release_lease(lease)
    with pytest.raises(ValueError, match="APPROVAL_REQUIRED"):
        runtime.apply_service.apply(record.plan_id, record.step_id, record.changeset_id)
    runtime.apply_service.approve(record.plan_id, record.step_id, HumanFixture())
    result = runtime.apply_service.apply(record.plan_id, record.step_id, record.changeset_id)
    assert result.applied_paths and Path(result.backup_snapshot_path).is_dir()
    with pytest.raises(ValueError, match=r"APPLY_STATE|APPROVAL_REQUIRED|BASE_CHANGED"):
        runtime.apply_service.apply(record.plan_id, record.step_id, record.changeset_id)


def test_fake_or_legacy_results_cannot_authorize_apply(native):
    runtime, record, commands, lease = native
    fake = runtime.apply_service.validate(
        record.plan_id, record.step_id, commands, ValidationFixture(), lease
    )
    assert fake.state == Lifecycle.VALIDATION_PASSED
    runtime.store.release_lease(lease)
    with pytest.raises(ValueError, match="VALIDATION_BACKEND_UNSUPPORTED"):
        runtime.apply_service.approve(record.plan_id, record.step_id, HumanFixture())


def test_human_native_consent_requires_interactive_terminal(native, monkeypatch):
    runtime, record, commands, _lease = native
    request = runtime.runner.consent_request(record, commands, 1)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(ValueError, match="HUMAN_CONSOLE_REQUIRED"):
        ConsoleHumanReview().confirm_native(request, "diff", ("tsc --noEmit",))
    with pytest.raises(ValueError, match="ASSURANCE_REQUIRED"):
        NativeExecutionConsent.model_validate(
            request.model_dump() | {"assurance_level": AssuranceLevel.MODE_C}
        )


def test_unsupported_native_isolation_fails(native, monkeypatch):
    runtime, record, commands, _lease = native
    policy = runtime.proposals.evidence.policy()
    for updates in (
        {"native_network": "none"},
        {"native_filesystem_isolation": True},
        {"execution_mode": "denied"},
    ):
        monkeypatch.setattr(
            runtime.proposals.evidence,
            "policy",
            lambda updates=updates: policy.model_copy(update=updates),
        )
        with pytest.raises(ValueError, match=r"EXECUTION_POLICY_UNSUPPORTED|ISOLATION_REQUIRED"):
            runtime.runner.consent_request(record, commands, 0)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows atomic Job Object contract")
@pytest.mark.parametrize("finish", ["normal", "cancel"])
def test_windows_job_terminates_grandchildren(tmp_path, finish):
    code = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-I','-c','import time; "
        "time.sleep(30)']); print(p.pid,flush=True); "
    ) + ("time.sleep(30)" if finish == "cancel" else "")
    process = WindowsJobProcess(
        [sys.executable, "-I", "-c", code],
        tmp_path,
        {"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")},
    )
    child = int(process.stdout.readline())
    if finish == "normal":
        deadline = time.monotonic() + 10
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert process.poll() == 0
    process.close()
    assert_not_running(child)


def assert_not_running(pid):
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if handle:
        try:
            assert kernel.WaitForSingleObject(handle, 5000) == 0
        finally:
            kernel.CloseHandle(handle)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows parent crash kill-on-close")
def test_windows_server_crash_leaves_no_job_descendants(tmp_path):
    script = tmp_path / "supervisor.py"
    script.write_text(
        (
            "from migration_agent.adapters.native_process import "
            "WindowsJobProcess\nimport sys,time,os\nfrom pathlib import "
            "Path\np=WindowsJobProcess([sys.executable,'-I','-c','import "
            "os,time; print(os.getpid(),flush=True); "
            "time.sleep(30)'],Path.cwd(),{'SYSTEMROOT':os.environ.get('SYSTEMR"
            "OOT',r'C:\\Windows')})\nprint(p.stdout.readline().decode().strip(),"
            "flush=True)\ntime.sleep(30)\n"
        ),
        encoding="utf-8",
    )
    parent = subprocess.Popen(
        [sys.executable, str(script)], cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        child = int(parent.stdout.readline())
        parent.kill()
        parent.wait(timeout=5)
        assert_not_running(child)
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=5)


def test_dependency_digest_rejects_missing_roots(tmp_path):
    with pytest.raises(ValueError, match="NATIVE_DEPENDENCIES_REQUIRED"):
        tree_digest(tmp_path / "missing")


def test_native_doctor_reports_missing_prerequisites_without_docker(monkeypatch):
    from migration_agent.application.doctor import collect_diagnostics

    monkeypatch.setattr(shutil, "which", lambda *args, **kwargs: pytest.fail("no Docker discovery"))
    report = collect_diagnostics(
        settings=Settings(
            validation_mode=ValidationMode.NATIVE,
            native_toolchain_root=None,
            native_dependencies_root=None,
        )
    )
    check = next(item for item in report["checks"] if item["name"] == "validation_backend")
    assert check["details"]["mode"] == "native"
    assert check["details"]["missing_prerequisites"] == [
        "external_native_toolchain",
        "external_offline_dependencies",
        "per_step_human_execution_consent",
        "browser_validation_plan",
    ]


def test_repository_wrappers_cannot_impersonate_native_tools(native):
    runtime, record, commands, _lease = native
    for name in ("node.exe", "npm.cmd", "tsc.cmd", "ng.cmd", "pytest.exe"):
        wrapper = Path(record.staging_path) / name
        wrapper.write_text("untrusted", encoding="utf-8")
        with pytest.raises(ValueError, match="EXECUTABLE_UNTRUSTED"):
            runtime.runner.consent_request(record, commands, 0)
        wrapper.unlink()


def test_native_mode_a_heartbeat_rechecks_authority_without_shared_signer(native):
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    from migration_agent.adapters.approval_proof import public_key_fingerprint
    from migration_agent.domain.trust import AuthorityKey, RepositoryBinding, TrustRecord

    runtime, record, commands, lease = native
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
    key = AuthorityKey(
        key_id="fixture",
        public_key=public,
        fingerprint=public_key_fingerprint(public),
        created_at="2026-10-05",
    )
    authority = TrustRecord(
        project_id=record.project_id,
        repository_binding=RepositoryBinding(root_commit_sha=record.root_commit),
        authority_keys=(key,),
    )
    runtime.trust.mkdir()
    path = runtime.trust / f"{record.project_id}.json"
    path.write_text(authority.model_dump_json(), encoding="utf-8")
    consent = runtime.runner.consent_request(record, commands, 0).model_copy(
        update={"assurance_level": AssuranceLevel.MODE_A, "key_fingerprint": key.fingerprint}
    )
    consent = consent.model_copy(
        update={
            "signature": "ed25519-base64:"
            + base64.b64encode(private.sign(consent.signing_digest.encode())).decode()
        }
    )
    runtime.store.save_native_consent(consent, lease)
    assert runtime.runner._consent(record, commands).consent_id == consent.consent_id
    assert (
        runtime.runner._consent(
            record, commands, consent.consent_id, verify_inputs=False
        ).consent_id
        == consent.consent_id
    )
    path.write_text(
        authority.model_copy(
            update={"authority_keys": (key.model_copy(update={"revoked": True}),)}
        ).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="AUTHORITY_REQUIRED"):
        runtime.runner._consent(record, commands, consent.consent_id, verify_inputs=False)


@pytest.mark.parametrize("stop", ["timeout", "cancel", "lease", "revoke"])
@pytest.mark.skipif(sys.platform != "win32", reason="Measured Windows descendant cleanup")
def test_native_heartbeat_stops_entire_job(native, monkeypatch, stop):
    runtime, record, commands, lease = native
    entry = runtime.settings.native_toolchain_root / "node_modules/npm/bin/npm-cli.js"
    entry.write_text(
        (
            "const fs=require('fs'),cp=require('child_process'); "
            "fs.mkdirSync('dist',{recursive:true}); const "
            "p=cp.spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{st"
            "dio:'ignore'}); "
            "fs.writeFileSync('dist/child.pid.tmp',String(p.pid)); "
            "fs.renameSync('dist/child.pid.tmp','dist/child.pid'); "
            "setInterval(()=>{},1000);"
        ),
        encoding="utf-8",
    )
    consent = authorize(native)
    pid_path = Path(record.staging_path) / "dist/child.pid"
    original_monotonic = time.monotonic
    if stop == "timeout":
        monkeypatch.setattr(
            time, "monotonic", lambda: original_monotonic() + (61 if pid_path.exists() else 0)
        )
    original_renew = runtime.store.renew_lease

    def renew(selected, ttl):
        if pid_path.exists():
            if stop == "revoke":
                runtime.store.revoke_native_consent(record.project_id, consent.consent_id)
            elif stop == "lease":
                runtime.store.release_lease(lease)
        return original_renew(selected, ttl)

    monkeypatch.setattr(runtime.store, "renew_lease", renew)
    try:
        if stop == "timeout":
            result = runtime.apply_service.validate(
                record.plan_id, record.step_id, commands[:1], runtime.runner, lease
            )
            assert result.state == Lifecycle.VALIDATION_FAILED
            assert result.validation_results[0].status.value == "TIMED_OUT"
        else:
            with pytest.raises(ValueError, match=r"NATIVE_CONSENT|CANCEL_REQUESTED|LEASE"):
                runtime.apply_service.validate(
                    record.plan_id,
                    record.step_id,
                    commands[:1],
                    runtime.runner,
                    lease,
                    cancelled=lambda: stop == "cancel" and pid_path.exists(),
                )
    finally:
        monkeypatch.setattr(time, "monotonic", original_monotonic)
    assert pid_path.exists()
    assert_not_running(int(pid_path.read_text()))


def test_input_mutation_and_unverified_cleanup_cannot_pass(native, monkeypatch):
    runtime, record, _commands, _lease = native
    entry = runtime.settings.native_toolchain_root / "node_modules/npm/bin/npm-cli.js"
    entry.write_text(
        "require('fs').writeFileSync('validation-config.json','changed');", encoding="utf-8"
    )
    authorize(native)
    with pytest.raises(ValueError, match="NATIVE_CONSENT_INPUT_CHANGED"):
        validate(native)
    assert (
        runtime.store.get_workflow(
            record.project_id, record.plan_id, record.step_id
        ).validation_digest
        is None
    )


def test_native_output_is_bounded_and_redacted(native):
    runtime, _record, _commands, _lease = native
    entry = runtime.settings.native_toolchain_root / "node_modules/npm/bin/npm-cli.js"
    entry.write_text(
        "console.log('sk-'+'a'.repeat(32)); process.stdout.write('z'.repeat(200000));",
        encoding="utf-8",
    )
    authorize(native)
    result = validate(native).validation_results[0]
    assert "sk-" not in result.sanitized_output
    assert "[REDACTED]" in result.sanitized_output
    assert len(result.sanitized_output.encode()) <= 65536


def test_execution_consent_revocation_invalidates_recorded_apply_approval(native):
    runtime, record, _commands, lease = native
    consent = authorize(native)
    record = validate(native)
    runtime.store.release_lease(lease)
    runtime.apply_service.approve(record.plan_id, record.step_id, HumanFixture())
    runtime.store.revoke_native_consent(record.project_id, consent.consent_id)
    with pytest.raises(ValueError, match="NATIVE_CONSENT_REQUIRED"):
        runtime.apply_service.apply(record.plan_id, record.step_id, record.changeset_id)
    assert runtime.proposals.evidence.repository_state().clean


def test_renewed_execution_consent_requires_revalidation_and_new_apply_approval(native):
    runtime, _initial, commands, lease = native
    previous_consent = authorize(native)
    record = validate(native)
    request = runtime.runner.consent_request(record, commands, 1)
    renewed = request.model_copy(update={"signature": runtime.runner.proof.sign(request)})
    runtime.store.save_native_consent(renewed, lease)
    assert renewed.consent_id != previous_consent.consent_id
    old_evidence = runtime.store.get_validation_execution(record.validation_digest)
    with pytest.raises(ValueError, match="NATIVE_CONSENT_REQUIRED"):
        runtime.runner.verify_execution(old_evidence, record)
    fresh = runtime.apply_service.validate(
        record.plan_id, record.step_id, commands, runtime.runner, lease
    )
    assert fresh.state == Lifecycle.VALIDATION_PASSED
    assert fresh.validation_digest != record.validation_digest
    assert fresh.approval_nonce is None


def test_repair_budget_counts_distinct_changesets(native):
    runtime, record, _commands, lease = native
    consent = authorize(native, repair_budget=1)
    runtime.store.use_native_consent(consent, record.changeset_id, lease)
    runtime.store.use_native_consent(consent, "repaired-one", lease)
    runtime.store.use_native_consent(consent, "repaired-one", lease)
    with pytest.raises(ValueError, match="NATIVE_REPAIR_BUDGET_EXCEEDED"):
        runtime.store.use_native_consent(consent, "repaired-two", lease)


def test_real_native_repair_reuses_only_authorized_scope(native):
    from migration_agent.adapters.workspace import LocalWorkspaceAdapter
    from migration_agent.application.validation import BoundedRepairService

    runtime, initial, _commands, lease = native
    entry = runtime.settings.native_toolchain_root / "node_modules/typescript/bin/tsc"
    entry.write_text(
        """
const fs=require('fs'),path=require('path');
function find(root){ for(const name of fs.readdirSync(root).sort()){
  if(name==='node_modules'||name==='dist')continue;
  const p=path.join(root,name);
  if(fs.statSync(p).isDirectory()){const found=find(p);if(found)return found;}
  else if(name.endsWith('.component.ts'))return p;
}}
const target=find('.');
if(!fs.readFileSync(target,'utf8').includes('import { HttpClient }')) {
  console.log(target.replaceAll('\\\\','/')+"(1,1): error TS2304: Cannot find name 'HttpClient'.");
  process.exit(1);
}
""",
        encoding="utf-8",
    )
    consent = authorize(native, repair_budget=1)
    assert validate(native).state == Lifecycle.VALIDATION_FAILED
    runtime.store.release_lease(lease)
    service = BoundedRepairService(
        None, LocalWorkspaceAdapter(), checkpoint_store=runtime.store, max_budget=1
    )
    record, attempts = service.prepare_workflow(
        runtime, runtime.store.get_plan(initial.plan_id), initial.step_id, False, 1
    )
    assert len(attempts) == 1
    assert record.state == Lifecycle.VALIDATION_PASSED
    assert record.changeset_id != initial.changeset_id
    evidence = runtime.store.get_validation_execution(record.validation_digest)
    assert evidence.provenance.consent_id == consent.consent_id
    assert record.approval_nonce is None
    runtime.apply_service.approve(record.plan_id, record.step_id, HumanFixture())
    assert runtime.apply_service.apply(
        record.plan_id, record.step_id, record.changeset_id
    ).applied_paths


@pytest.mark.parametrize("mutation", ["backend", "cleanup", "dependencies", "toolchain"])
def test_provenance_tampering_blocks_new_approval(native, mutation):
    import json

    runtime, _original, _commands, lease = native
    authorize(native)
    record = validate(native)
    runtime.store.release_lease(lease)
    evidence = runtime.store.get_validation_execution(record.validation_digest).model_dump(
        mode="json"
    )
    if mutation == "backend":
        evidence["provenance"]["backend"] = "container"
    elif mutation == "cleanup":
        evidence["provenance"]["cleanup_verified"] = False
    elif mutation == "dependencies":
        evidence["provenance"]["dependency_digest"] = "changed"
    else:
        evidence["provenance"]["toolchain"][0]["sha256"] = "0" * 64
    with runtime.store._get_connection() as connection:
        connection.execute(
            "UPDATE validation_executions SET content_json=? WHERE digest=?",
            (json.dumps(evidence), record.validation_digest),
        )
    with pytest.raises(ValueError, match=r"VALIDATION_|EXECUTION_POLICY"):
        runtime.apply_service.approve(record.plan_id, record.step_id, HumanFixture())


def test_native_cli_authorize_and_revoke_are_separate_from_apply(native, monkeypatch):
    import getpass
    import json

    from typer.testing import CliRunner

    from migration_agent.cli import app
    from migration_agent.domain.apply_approval import HumanDecision

    runtime, record, _commands, lease = native
    runtime.store.release_lease(lease)
    monkeypatch.setattr("migration_agent.adapters.workflow_cli.runtime_for", lambda *args: runtime)
    monkeypatch.setattr(
        ConsoleHumanReview,
        "confirm_native",
        lambda *args: HumanDecision(
            confirmed=True, actor=getpass.getuser(), assurance=AssuranceLevel.MODE_B
        ),
    )
    args = [
        "--project-root",
        str(runtime.proposals.root),
        "--state-dir",
        str(runtime.state),
        "--staging-root",
        str(runtime.staging),
    ]
    result = CliRunner().invoke(
        app, ["validation", "authorize", record.step_id, "--plan", record.plan_id, *args]
    )
    assert result.exit_code == 0, result.output
    consent = json.loads(result.stdout)
    assert (
        runtime.store.get_workflow(record.project_id, record.plan_id, record.step_id).approval_nonce
        is None
    )
    result = CliRunner().invoke(app, ["validation", "revoke", consent["consent_id"], *args])
    assert result.exit_code == 0, result.output
    with pytest.raises(ValueError, match="NATIVE_CONSENT_REQUIRED"):
        runtime.store.get_native_consent(record.project_id, record.plan_id, record.step_id)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows creation failure contract")
def test_windows_assignment_failure_never_launches_repository_code(tmp_path, monkeypatch):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    original_update = kernel.UpdateProcThreadAttribute
    original_update.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]

    def reject_job(*args):
        if args[2] == 0x2000D:
            return 0
        return original_update(*args)

    kernel.UpdateProcThreadAttribute = reject_job
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: kernel)
    marker = tmp_path / "launched"
    with pytest.raises(OSError):
        WindowsJobProcess(
            [sys.executable, "-I", "-c", "from pathlib import Path; Path('launched').touch()"],
            tmp_path,
            {},
        )
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows direct real npm CLI")
def test_real_installed_npm_cli_works_without_cmd_launcher(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Installed Node required")
    npm = Path(node).parent / "node_modules/npm/bin/npm-cli.js"
    if not npm.is_file():
        pytest.skip("Installed npm required")
    workspace = tmp_path / "real npm Ω spaces"
    workspace.mkdir()
    import json

    (workspace / "package.json").write_text(
        json.dumps({"scripts": {"lint": "node -e \"console.log('real npm offline')\""}}),
        encoding="utf-8",
    )
    env = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "ComSpec": str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/cmd.exe"),
        "PATH": str(Path(node).parent)
        + os.pathsep
        + str(Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "npm_config_offline": "true",
        "npm_config_cache": str(tmp_path / "cache"),
        "npm_config_ignore_scripts": "true",
    }
    process = WindowsJobProcess([node, str(npm), "run", "lint"], workspace, env)
    try:
        output = process.stdout.read().decode(errors="replace")
        deadline = time.monotonic() + 10
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert process.poll() == 0, output
        assert "real npm offline" in output
    finally:
        process.close()
