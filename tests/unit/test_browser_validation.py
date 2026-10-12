"""Offline browser gates, captured-image review, repair and final E2E ordering."""

import hashlib
import os
import shutil
import struct
import zlib
from pathlib import Path

import pytest
from test_native_validation import native as native
from test_shared_apply import HumanFixture, ValidationFixture
from test_shared_apply import workflow as workflow

from migration_agent.adapters.browser_validation import BrowserValidationGate, WorkerResult
from migration_agent.adapters.fenced_validation import VALIDATION_COMMANDS
from migration_agent.adapters.validation_backend import ValidationBackend
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.browser_validation import evaluate_review
from migration_agent.application.validation import BoundedRepairService
from migration_agent.domain.browser_validation import (
    BrowserAssertion,
    BrowserCapture,
    BrowserCase,
    BrowserImage,
    BrowserReview,
    BrowserValidationPlan,
    CaseReview,
    JourneyResult,
    ObjectiveFinding,
    ReviewCheck,
    UIRepair,
    Viewport,
)
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.execution import ValidationMode
from migration_agent.domain.host_workflow import (
    Lifecycle,
    OperationStatus,
    workflow_diagnostic_digest,
)
from migration_agent.domain.validation import ValidationProfile


def ui_plan(**updates):
    values = dict(
        version="fixture-v1",
        build_root="dist/app",
        design_requirements="Keep controls visible, aligned and readable at the supported sizes.",
        test_data_identity="synthetic-fixture-v1",
        viewports=(
            Viewport(id="mobile", width=360, height=800),
            Viewport(id="desktop", width=1440, height=900),
        ),
        cases=(
            BrowserCase(
                id="home",
                state="initial",
                expected="Named action and title are visible.",
                assertions=(BrowserAssertion(kind="visible", selector="h1"),),
            ),
        ),
    )
    values.update(updates)
    return BrowserValidationPlan(**values)


def png(viewport):
    width = round(viewport.width * viewport.device_scale_factor)
    height = round(viewport.height * viewport.device_scale_factor)

    def chunk(kind, content):
        return (
            struct.pack(">I", len(content))
            + kind
            + content
            + struct.pack(">I", zlib.crc32(kind + content))
        )

    rows = b"".join(b"\0" + b"\xff\xff\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def capture(plan, **updates):
    images = tuple(
        BrowserImage(
            case_key=f"{case.id}--{viewport.id}",
            origin=origin,
            filename=f"{case.id}--{viewport.id}--{origin}.png",
            viewport=viewport,
            sha256=hashlib.sha256(png(viewport)).hexdigest(),
        )
        for origin in ("source", "target")
        if origin == "target" or plan.source_url
        for case in plan.cases
        for viewport in plan.viewports
    )
    values = dict(
        capture_id="browser-" + "a" * 32,
        project_id="project",
        plan_id="plan",
        step_id="step",
        changeset_digest="cs-digest",
        source_revision="base",
        config_digest=plan.digest,
        build_digest="build",
        tool_digest="tools",
        browser_version="fixture-chromium",
        images=images,
        cleanup_verified=True,
    )
    values.update(updates)
    return BrowserCapture(**values)


def review(plan, shot, fail=None, repairs=()):
    sources = {i.case_key: i for i in shot.images if i.origin == "source"}
    return BrowserReview(
        capture_id=shot.capture_id,
        reviewer="image-analysis-fixture",
        cases=tuple(
            CaseReview(
                case_key=image.case_key,
                screenshot_sha256=image.sha256,
                source_sha256=sources[image.case_key].sha256 if image.case_key in sources else None,
                checks=tuple(
                    ReviewCheck(
                        rule_id=rule.id,
                        verdict="fail" if fail == rule.id else "pass",
                        explanation="Fixture visual evidence checked.",
                    )
                    for rule in plan.rules
                ),
            )
            for image in shot.images
            if image.origin == "target"
        ),
        repairs=repairs,
    )


def test_visual_review_requires_all_rules_and_actual_hashes():
    plan = ui_plan()
    shot = capture(plan)
    assert evaluate_review(plan, shot, None).status == "REVIEW_REQUIRED"
    assert evaluate_review(plan, shot, review(plan, shot)).passed
    assert evaluate_review(plan, shot, review(plan, shot, fail="spacing")).status == "FAILED"


@pytest.mark.parametrize("tamper", ["viewport", "duplicate", "cleanup", "policy"])
def test_incomplete_or_relabelled_capture_never_passes(tamper):
    plan = ui_plan()
    shot = capture(plan)
    updates = {
        "viewport": {"images": shot.images[:-1]},
        "duplicate": {"images": (*shot.images, shot.images[0])},
        "cleanup": {"cleanup_verified": False},
        "policy": {"config_digest": "other"},
    }[tamper]
    with pytest.raises(ValueError, match="BROWSER_EVIDENCE_INVALID"):
        evaluate_review(plan, shot.model_copy(update=updates), None)


@pytest.mark.parametrize("tamper", ["case", "hash", "rule", "duplicate_rule", "capture"])
def test_fabricated_or_incomplete_ai_reviews_reject(tamper):
    plan = ui_plan()
    shot = capture(plan)
    value = review(plan, shot)
    first = value.cases[0]
    if tamper == "case":
        value = value.model_copy(update={"cases": value.cases[:-1]})
    if tamper == "hash":
        value = value.model_copy(
            update={
                "cases": (
                    first.model_copy(update={"screenshot_sha256": "f" * 64}),
                    *value.cases[1:],
                )
            }
        )
    if tamper == "rule":
        value = value.model_copy(
            update={
                "cases": (first.model_copy(update={"checks": first.checks[:-1]}), *value.cases[1:])
            }
        )
    if tamper == "duplicate_rule":
        value = value.model_copy(
            update={
                "cases": (
                    first.model_copy(update={"checks": (first.checks[0],) * len(first.checks)}),
                    *value.cases[1:],
                )
            }
        )
    if tamper == "capture":
        value = value.model_copy(update={"capture_id": "browser-" + "b" * 32})
    with pytest.raises(ValueError, match="BROWSER_REVIEW_INVALID"):
        evaluate_review(plan, shot, value)


def test_ai_uncertainty_and_measured_defects_cannot_be_waived():
    plan = ui_plan()
    shot = capture(plan)
    measured = shot.images[0].model_copy(
        update={
            "findings": (
                ObjectiveFinding(rule_id="responsive", description="Horizontal overflow measured."),
            )
        }
    )
    shot = shot.model_copy(update={"images": (measured, *shot.images[1:])})
    assert not evaluate_review(plan, shot, review(plan, shot)).passed
    clean = capture(plan)
    value = review(plan, clean)
    first = value.cases[0]
    uncertain = first.checks[0].model_copy(update={"verdict": "uncertain"})
    value = value.model_copy(
        update={
            "cases": (
                first.model_copy(update={"checks": (uncertain, *first.checks[1:])}),
                *value.cases[1:],
            )
        }
    )
    assert not evaluate_review(plan, clean, value).passed


def test_optional_source_comparison_requires_paired_evidence_when_selected():
    no_source = ui_plan()
    assert evaluate_review(
        no_source, capture(no_source), review(no_source, capture(no_source))
    ).passed
    plan = ui_plan(source_url="http://127.0.0.1:12345", source_identity="legacy-build-v1")
    shot = capture(plan)
    assert evaluate_review(plan, shot, review(plan, shot)).passed
    first = review(plan, shot).cases[0].model_copy(update={"source_sha256": None})
    value = review(plan, shot).model_copy(update={"cases": (first, *review(plan, shot).cases[1:])})
    with pytest.raises(ValueError, match="BROWSER_REVIEW_INVALID"):
        evaluate_review(plan, shot, value)


def test_unready_source_reference_cannot_be_called_compared():
    plan = ui_plan(source_url="http://127.0.0.1:12345", source_identity="legacy")
    shot = capture(plan)
    source = shot.images[0].model_copy(update={"ready": False})
    shot = shot.model_copy(update={"images": (source, *shot.images[1:])})
    with pytest.raises(ValueError, match="BROWSER_SOURCE_NOT_READY"):
        evaluate_review(plan, shot, review(plan, shot))


def test_original_execution_policy_and_v2_hashes_are_preserved():
    from datetime import UTC, datetime

    from migration_agent.domain.execution import ExecutionPolicy
    from migration_agent.domain.host_workflow import ValidationExecution

    policy = ExecutionPolicy(
        mode=ValidationMode.CONTAINER,
        project_policy_digest="policy",
        network="none",
        filesystem="container",
        supervision="legacy",
    )
    assert not any(key.startswith("browser_") for key in policy.model_dump())
    legacy_policy = policy.model_dump(mode="json")
    assert policy.digest == compute_canonical_digest(legacy_policy)
    execution = ValidationExecution(
        schema_version=2,
        project_id="project",
        plan_id="plan",
        step_id="step",
        changeset_id="cs",
        changeset_digest="digest",
        staging_fingerprint="stage",
        results=(),
        completed_at=datetime.now(UTC),
    )
    legacy = execution.model_dump(mode="json")
    assert "browser_evidence" not in legacy
    assert compute_canonical_digest(
        ValidationExecution.model_validate(legacy).model_dump(mode="json")
    ) == compute_canonical_digest(legacy)


@pytest.mark.parametrize(
    "updates",
    [
        {"build_root": "../source"},
        {"source_url": "http://localhost:1234"},
        {"source_url": "https://127.0.0.1:1234"},
        {"e2e_enabled": True},
        {"rules": ()},
        {"viewports": (Viewport(id="same", width=360, height=800),) * 2},
    ],
)
def test_unsafe_or_incomplete_browser_plans_reject(updates):
    with pytest.raises(ValueError):
        ui_plan(**updates)


@pytest.fixture
def browser_workflow(workflow, tmp_path, monkeypatch):
    runtime, plan_id, step_id = workflow
    plan = ui_plan()
    config = tmp_path / "browser-plan.json"
    config.write_text(plan.model_dump_json(), encoding="utf-8")
    settings = runtime.settings.model_copy(
        update={
            "validation_mode": ValidationMode.NATIVE,
            "browser_validation_plan": config,
            "browser_review_mode": "host",
        }
    )
    runtime.settings = settings

    class BuildFixture(ValidationFixture):
        def prepare(self, record, commands, lease):
            from migration_agent.adapters.visual_specialist import provider_disclosure

            result = super().prepare(record, commands, lease)
            policy = result.policy.model_copy(
                update={
                    "browser_provider_disclosure": provider_disclosure(
                        runtime.browser_gate.settings
                    )
                }
            )
            return result.model_copy(update={"policy": policy, "policy_digest": policy.digest})

        def verify_browser_session(self, record, provenance):
            assert provenance.policy.supervision == "test-harness"

        def run(self, command, working_dir, fence):
            result = super().run(command, working_dir, fence)
            output = working_dir / "dist/app"
            output.mkdir(parents=True, exist_ok=True)
            (output / "index.html").write_text("<h1>Fixture</h1>", encoding="utf-8")
            return result

    gate = BuildFixture()
    runtime.runner = gate
    runtime.apply_service.execution_gate = gate
    browser = BrowserValidationGate(settings, gate, runtime.store, runtime.state)
    runtime.browser_gate = browser
    runtime.apply_service.browser_gate = browser
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "browser-fixture", ttl=900)
    record = runtime.apply_service.stage(plan_id, step_id, lease)
    build = Path(record.staging_path) / plan.build_root
    build.mkdir(parents=True, exist_ok=True)
    (build / "index.html").write_text("<h1>Fixture</h1>", encoding="utf-8")
    runtime.store.release_lease(lease)
    calls = []
    journey_pass = [True]

    def worker(current_plan, current, output, phase, fence):
        fence()
        calls.append(phase)
        output.mkdir(parents=True)
        if phase == "e2e":
            return WorkerResult(
                browser_version="fixture",
                images=(),
                journeys=tuple(
                    JourneyResult(case_id=c.id, passed=journey_pass[0], details="Fixture journey.")
                    for c in current_plan.e2e_cases
                ),
            )
        shot = capture(current_plan)
        for image in shot.images:
            (output / image.filename).write_bytes(png(image.viewport))
        return WorkerResult(browser_version="fixture", images=shot.images, journeys=())

    monkeypatch.setattr(browser, "_worker", worker)
    return runtime, plan_id, step_id, plan, config, calls, journey_pass


def validate_ui(value):
    runtime, plan, step, *_ = value
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "validate-fixture", ttl=900)
    try:
        return runtime.apply_service.validate(
            plan,
            step,
            tuple(command for items in VALIDATION_COMMANDS.values() for command in items),
            runtime.runner,
            lease,
        )
    finally:
        runtime.store.release_lease(lease)


def test_browser_review_is_mandatory_and_cannot_approve_pending(browser_workflow):
    runtime, plan_id, step_id, plan, *_ = browser_workflow
    record = validate_ui(browser_workflow)
    assert record.state == Lifecycle.VALIDATION_FAILED
    assert record.browser_evidence.status == "REVIEW_REQUIRED"
    assert runtime.store.get_validation_execution(record.validation_digest).schema_version == 3
    with pytest.raises(ValueError):
        runtime.apply_service.approve(plan_id, step_id, HumanFixture())
    analysis = review(plan, record.browser_evidence.capture)
    operation = runtime.submit_browser_review(plan_id, step_id, "visual-reviewed", analysis)
    assert operation.status == OperationStatus.SUCCEEDED, operation.message
    assert (
        runtime.store.get_workflow(runtime.binding.project_id, plan_id, step_id).state
        == Lifecycle.VALIDATION_FAILED
    )
    record = validate_ui(browser_workflow)
    assert record.state == Lifecycle.VALIDATION_PASSED
    runtime.apply_service.approve(plan_id, step_id, HumanFixture())
    result = runtime.apply_service.apply(plan_id, step_id, record.changeset_id)
    assert result.status.value == "APPLIED"


def test_partial_command_checks_cannot_run_browser_or_authorize_apply(browser_workflow):
    runtime, plan_id, step_id, _, _, calls, _ = browser_workflow
    lease = runtime.store.acquire_lease(runtime.binding.project_id, "partial-checks", ttl=900)
    try:
        command = VALIDATION_COMMANDS[ValidationProfile.TYPECHECK]
        record = runtime.apply_service.validate(plan_id, step_id, command, runtime.runner, lease)
    finally:
        runtime.store.release_lease(lease)
    assert record.state == Lifecycle.VALIDATION_FAILED
    assert record.browser_evidence is None and not calls


def test_renewed_consent_requires_fresh_browser_capture(browser_workflow, monkeypatch):
    runtime, plan_id, step_id, plan, _, calls, _ = browser_workflow
    record = validate_ui(browser_workflow)
    runtime.submit_browser_review(
        plan_id, step_id, "visual-pass", review(plan, record.browser_evidence.capture)
    )
    assert validate_ui(browser_workflow).state == Lifecycle.VALIDATION_PASSED
    original = runtime.runner.prepare
    monkeypatch.setattr(
        runtime.runner,
        "prepare",
        lambda *args: original(*args).model_copy(update={"consent_id": "renewed"}),
    )
    fresh = validate_ui(browser_workflow)
    assert fresh.browser_evidence.status == "REVIEW_REQUIRED"
    assert calls == ["ui", "ui"]


def test_container_browser_mounts_preserve_isolation_and_exact_template(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace

    from migration_agent.adapters.fenced_validation import (
        BROWSER_COMMAND,
        BrowserMounts,
        FencedValidationRunner,
    )
    from migration_agent.domain.execution import ToolIdentity

    source, staging, workspace, artifacts = (
        tmp_path / p for p in ("source", "staging", "staging/work", "captures")
    )
    for directory in (source, workspace, artifacts):
        directory.mkdir(parents=True)
    engine, worker = tmp_path / "docker.exe", tmp_path / "worker.cjs"
    engine.write_bytes(b"engine fixture")
    worker.write_bytes(b"fixed worker fixture")
    launches = []

    class Process:
        def __init__(self, argv, **kwargs):
            launches.append(argv)
            self.stdout, self.stderr = io.BytesIO(b"closed\n"), io.BytesIO()
            self.pid = 12345

        def poll(self):
            return 0

        def wait(self, **kwargs):
            return 0

    monkeypatch.setattr("migration_agent.adapters.fenced_validation.subprocess.Popen", Process)
    monkeypatch.setattr(
        "migration_agent.adapters.fenced_validation.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=b"", stdout=b""),
    )
    runner = FencedValidationRunner(
        staging, container_image="fixture@sha256:" + "a" * 64, source_root=source
    )
    mounts = BrowserMounts(
        worker=ToolIdentity(
            path=str(worker.resolve()), sha256=hashlib.sha256(worker.read_bytes()).hexdigest()
        ),
        artifacts=str(artifacts),
    )
    result = runner.run(
        BROWSER_COMMAND,
        workspace,
        lambda: None,
        engine_identity=ToolIdentity(
            path=str(engine.resolve()), sha256=hashlib.sha256(engine.read_bytes()).hexdigest()
        ),
        browser_mounts=mounts,
    )
    assert result.exit_code == 0
    args = launches[0]
    assert "--network=none" in args and "--read-only" in args
    assert "--cap-drop=ALL" in args and "--pull=never" in args
    assert any("target=/workspace,readonly" in arg for arg in args)
    assert any("target=/agent/browser_worker.cjs,readonly" in arg for arg in args)
    assert not any(str(source) in arg for arg in args)
    assert args[-3:] == ["node", "/agent/browser_worker.cjs", "/artifacts/request.json"]


@pytest.mark.parametrize("enabled", [False, True])
def test_e2e_is_optional_and_runs_only_after_visual_pass(browser_workflow, enabled):
    runtime, plan_id, step_id, plan, config, calls, _ = browser_workflow
    plan = ui_plan(e2e_enabled=enabled, e2e_cases=plan.cases if enabled else ())
    config.write_text(plan.model_dump_json(), encoding="utf-8")
    record = validate_ui(browser_workflow)
    assert calls == ["ui"]
    runtime.submit_browser_review(
        plan_id, step_id, "visual-pass", review(plan, record.browser_evidence.capture)
    )
    record = validate_ui(browser_workflow)
    assert calls == (["ui", "e2e"] if enabled else ["ui"])
    assert record.browser_evidence.e2e_status == ("PASSED" if enabled else "NOT_RUN")


def test_enabled_e2e_failure_blocks_source_approval(browser_workflow):
    runtime, plan_id, step_id, plan, config, _, passing = browser_workflow
    plan = ui_plan(e2e_enabled=True, e2e_cases=plan.cases)
    config.write_text(plan.model_dump_json(), encoding="utf-8")
    record = validate_ui(browser_workflow)
    runtime.submit_browser_review(
        plan_id, step_id, "visual-pass", review(plan, record.browser_evidence.capture)
    )
    passing[0] = False
    record = validate_ui(browser_workflow)
    assert record.browser_evidence.e2e_status == "FAILED"
    assert record.state == Lifecycle.VALIDATION_FAILED
    with pytest.raises(ValueError):
        runtime.apply_service.approve(plan_id, step_id, HumanFixture())


@pytest.mark.parametrize("tamper", ["image", "build", "plan"])
def test_stale_or_modified_browser_evidence_blocks_approval(browser_workflow, tamper):
    runtime, plan_id, step_id, plan, config, *_ = browser_workflow
    record = validate_ui(browser_workflow)
    runtime.submit_browser_review(
        plan_id, step_id, "visual-pass", review(plan, record.browser_evidence.capture)
    )
    record = validate_ui(browser_workflow)
    if tamper == "image":
        request = runtime.browser_gate.request(record)
        Path(request.screenshot_paths[0]).write_bytes(b"changed")
    if tamper == "build":
        (Path(record.staging_path) / plan.build_root / "index.html").write_text("changed")
    if tamper == "plan":
        config.write_text(ui_plan(version="v2").model_dump_json())
    with pytest.raises(ValueError, match="BROWSER_"):
        runtime.apply_service.approve(plan_id, step_id, HumanFixture())


def test_review_submission_is_idempotent_and_never_human_approval(browser_workflow):
    runtime, plan_id, step_id, plan, *_ = browser_workflow
    record = validate_ui(browser_workflow)
    analysis = review(plan, record.browser_evidence.capture)
    first = runtime.submit_browser_review(plan_id, step_id, "same-review", analysis)
    second = runtime.submit_browser_review(plan_id, step_id, "same-review", analysis)
    assert first.operation_id == second.operation_id
    assert (
        runtime.store.get_workflow(runtime.binding.project_id, plan_id, step_id).approval_nonce
        is None
    )


def test_unapproved_external_provider_transfer_is_blocked(browser_workflow):
    runtime, *_ = browser_workflow
    runtime.browser_gate.settings = runtime.settings.model_copy(
        update={"browser_review_mode": "provider"}
    )
    record = validate_ui(browser_workflow)
    assert record.state == Lifecycle.VALIDATION_FAILED
    assert any("DISCLOSURE_REQUIRED" in issue for issue in record.browser_evidence.issues)


def test_ai_repair_restages_recaptures_and_rechecks(browser_workflow, monkeypatch):
    runtime, plan_id, step_id, plan, _, calls, _ = browser_workflow
    record = validate_ui(browser_workflow)
    current = runtime.current_changeset(record.changeset_id)
    file = next(c for c in current.changes if c.path.endswith(".scss"))
    patch = UIRepair(
        path=file.path,
        text=".user-card { padding: 16px; max-width: 100%; }\n",
        case_keys=plan.coverage,
        rule_ids=("spacing",),
    )
    analysis = review(plan, record.browser_evidence.capture, fail="spacing", repairs=(patch,))
    runtime.submit_browser_review(plan_id, step_id, "visual-failure", analysis)
    original = runtime.prepare

    def prepare(plan_id, step_id, skip):
        result = original(plan_id, step_id, skip)
        if result.browser_evidence and result.changeset_id != current.changeset_id:
            report = review(plan, result.browser_evidence.capture)
            op = runtime.submit_browser_review(plan_id, step_id, "visual-fixed", report)
            assert op.status == OperationStatus.SUCCEEDED
            result = original(plan_id, step_id, skip)
        return result

    monkeypatch.setattr(runtime, "prepare", prepare)
    service = BoundedRepairService(None, LocalWorkspaceAdapter(), max_budget=3)
    record, attempts = service.prepare_workflow(
        runtime, runtime.store.get_plan(plan_id), step_id, False, 3
    )
    assert record.state == Lifecycle.VALIDATION_PASSED
    assert record.changeset_id != current.changeset_id
    assert record.browser_repair_count == 1
    assert len(attempts) == 1 and calls == ["ui", "ui"]
    assert runtime.proposals.evidence.repository_state().clean


def test_ui_repair_budget_is_durable_across_resume(browser_workflow):
    from migration_agent.domain.host_workflow import RepairFile, RepairProposal

    runtime, plan_id, step_id, plan, config, *_ = browser_workflow
    plan = ui_plan(max_repairs=0)
    config.write_text(plan.model_dump_json())
    record = validate_ui(browser_workflow)
    runtime.submit_browser_review(
        plan_id,
        step_id,
        "visual-failure",
        review(plan, record.browser_evidence.capture, fail="spacing"),
    )
    record = runtime.store.get_workflow(runtime.binding.project_id, plan_id, step_id)
    current = runtime.current_changeset(record.changeset_id)
    first = current.changes[0]
    proposal = RepairProposal(
        plan_id=plan_id,
        step_id=step_id,
        changeset_id=current.changeset_id,
        diagnostic_digest=workflow_diagnostic_digest(record),
        files=(RepairFile(path=first.path, text=first.content_bytes.decode()),),
    )
    operation = runtime.proposals.submit_repair("attempt-after-budget", proposal)
    assert operation.status == OperationStatus.FAILED
    assert "BROWSER_REPAIR_BUDGET_EXHAUSTED" in operation.message


def test_real_chromium_worker_measures_responsiveness_without_provider_keys(native, tmp_path):
    module = os.environ.get("AGENT_TEST_PLAYWRIGHT_CORE")
    chrome = os.environ.get("AGENT_TEST_BROWSER_PATH")
    if not module or not chrome or not Path(module).is_dir() or not Path(chrome).is_file():
        pytest.skip(
            "Provision external Playwright Core and Chromium for measured "
            "offline browser acceptance."
        )
    runtime, record, commands, lease = native
    root = runtime.settings.native_toolchain_root
    shutil.copytree(module, root / "node_modules/playwright-core")
    plan = ui_plan()
    config = tmp_path / "browser-plan.json"
    config.write_text(plan.model_dump_json())
    settings = runtime.settings.model_copy(
        update={
            "browser_validation_plan": config,
            "native_browser_path": Path(chrome),
            "browser_review_mode": "host",
        }
    )
    runtime.settings = settings
    runtime.runner = ValidationBackend(
        settings, runtime.proposals, runtime.store, runtime.staging, runtime.state, runtime.trust
    )
    runtime.browser_gate = BrowserValidationGate(
        settings, runtime.runner, runtime.store, runtime.state
    )
    runtime.apply_service.execution_gate = runtime.runner
    runtime.apply_service.browser_gate = runtime.browser_gate
    build = Path(record.staging_path) / plan.build_root
    build.mkdir(parents=True)
    (build / "index.html").write_text(
        '<html><head><title>Fixture</title></head><body style="width:900px">'
        '<h1>Fixture</h1><button aria-label="Continue">Continue</button></body></html>'
    )
    consent = runtime.runner.consent_request(record, commands, 1)
    runtime.store.save_native_consent(
        consent.model_copy(update={"signature": runtime.runner.proof.sign(consent)}), lease
    )
    result = runtime.apply_service.validate(
        record.plan_id, record.step_id, commands, runtime.runner, lease
    )
    assert result.state == Lifecycle.VALIDATION_FAILED
    assert result.browser_evidence.capture.cleanup_verified
    assert len(result.browser_evidence.capture.images) == 2
    mobile = next(i for i in result.browser_evidence.capture.images if i.viewport.id == "mobile")
    assert any(i.rule_id == "responsive" for i in mobile.findings)
    assert runtime.browser_gate.image(result.browser_evidence.capture, mobile).startswith(
        b"\x89PNG"
    )
    assert result.browser_evidence.e2e_status == "NOT_RUN"
    assert runtime.proposals.evidence.repository_state().clean
