"""Provider request contracts and the guarded visual repair cycle, entirely offline."""

import base64
import json
from types import SimpleNamespace

import pytest
from test_browser_validation import (
    browser_workflow as browser_workflow,
)
from test_browser_validation import capture, png, review, ui_plan, validate_ui
from test_native_validation import authorize
from test_native_validation import native as native
from test_shared_apply import HumanFixture
from test_shared_apply import workflow as workflow

from migration_agent.adapters import visual_specialist as visual
from migration_agent.adapters.browser_validation import BrowserReviewRequest
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.validation import BoundedRepairService
from migration_agent.config import Settings
from migration_agent.domain.browser_validation import UIRepair
from migration_agent.domain.execution import BrowserProviderDisclosure
from migration_agent.domain.host_workflow import Lifecycle


def configured(provider="openai", **updates):
    return Settings(
        browser_review_mode="provider",
        browser_provider_export=True,
        runtime_provider=provider,
        runtime_model="test-vision-model",
    ).model_copy(update=updates)


def request_for(plan=None):
    plan = plan or ui_plan()
    return BrowserReviewRequest(
        plan=plan,
        capture=capture(plan),
        editable_files={"src/card.scss": ".card { padding: 16px; }\n"},
        screenshot_paths=("C:/private/artifacts/capture.png",),
    )


def response_for(request, key, fail=None, repairs=()):
    case = next(
        item for item in review(request.plan, request.capture, fail).cases if item.case_key == key
    )
    return visual.CaseVisualResponse(case=case, repairs=repairs)


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_sdk_receives_verified_images_and_bounded_metadata_at_fixed_destination(
    monkeypatch, provider
):
    import openai
    from google import genai
    from google.genai import types

    plan = ui_plan(source_url="http://127.0.0.1:1234", source_identity="synthetic-legacy-v1")
    request = request_for(plan)
    constructors, calls = [], []

    class Client:
        def __init__(self, **kwargs):
            constructors.append(kwargs)
            self.responses = SimpleNamespace(parse=self.parse)
            self.models = SimpleNamespace(generate_content=self.generate)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def parse(self, **kwargs):
            calls.append(kwargs)
            metadata = json.loads(kwargs["input"][0]["content"][0]["text"])
            result = response_for(request, metadata["case_key"])
            return SimpleNamespace(status="completed", output_parsed=result)

        def generate(self, **kwargs):
            calls.append(kwargs)
            metadata = json.loads(kwargs["contents"].parts[0].text)
            result = response_for(request, metadata["case_key"])
            return SimpleNamespace(
                candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
                text=result.model_dump_json(),
            )

    monkeypatch.setattr(openai, "OpenAI", Client)
    monkeypatch.setattr(genai, "Client", Client)
    result = visual.review_with_provider(
        configured(provider), request, lambda i: png(i.viewport), lambda: None
    )
    assert len(result.cases) == len(plan.coverage)
    assert result.reviewer == f"provider:{provider}:test-vision-model"
    for constructor, call in zip(constructors, calls, strict=True):
        if provider == "openai":
            assert constructor == dict(
                base_url="https://api.openai.com/v1", timeout=30, max_retries=0
            )
            assert call["store"] is False and call["max_output_tokens"] == 8192
            assert call["text_format"] is visual.CaseVisualResponse
            parts = call["input"][0]["content"]
            metadata = json.loads(parts[0]["text"])
            images = [base64.b64decode(p["image_url"].split(",", 1)[1]) for p in parts[1:]]
        else:
            assert constructor["vertexai"] is False and constructor["enterprise"] is False
            options = constructor["http_options"]
            assert options.base_url == "https://generativelanguage.googleapis.com"
            assert options.timeout == 30000 and options.retry_options.attempts == 1
            assert call["config"].response_schema is visual.CaseVisualResponse
            assert call["config"].max_output_tokens == 8192
            parts = call["contents"].parts
            metadata = json.loads(parts[0].text)
            images = [p.inline_data.data for p in parts[1:]]
        assert [image["origin"] for image in metadata["images_in_order"]] == ["target", "source"]
        assert len(images) == 2 and all(data.startswith(b"\x89PNG") for data in images)
        assert "private" not in json.dumps(metadata) and "screenshot_paths" not in metadata
        assert "source_url" not in metadata and "build_root" not in metadata
        assert "filename" not in metadata["images_in_order"][0]
        assert metadata["editable_files"] == request.editable_files
        assert call["model"] == "test-vision-model"


@pytest.mark.parametrize(
    "updates",
    [
        {"browser_provider_export": False},
        {"browser_review_mode": "host"},
        {"runtime_provider": "unknown"},
        {"runtime_model": None, "agent_model": None},
        {"runtime_model": "https://untrusted.invalid"},
    ],
)
def test_missing_opt_in_or_invalid_configuration_never_calls_provider(monkeypatch, updates):
    calls = []
    monkeypatch.setattr(visual, "_generate", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="BROWSER_PROVIDER_"):
        visual.review_with_provider(
            configured(**updates), request_for(), lambda i: png(i.viewport), lambda: None
        )
    assert not calls


def test_provider_destination_and_policy_binding_are_validated(tmp_path):
    from migration_agent.adapters.mcp.setup import setup_client

    settings = configured()
    disclosure = visual.provider_disclosure(settings)
    assert disclosure.provider == "openai" and disclosure.payload == "browser-visual-v1"
    source = tmp_path / "source"
    source.mkdir()
    settings = settings.model_copy(
        update={"state_dir": tmp_path / "state", "staging_root": tmp_path / "staging"}
    )
    preview = setup_client("codex", source, settings, tmp_path / "client/config.toml")
    env = preview.entry["env"]
    assert env["AGENT_BROWSER_PROVIDER_EXPORT"] == "true"
    assert env["AGENT_RUNTIME_MODEL"] == "test-vision-model"
    assert env["AGENT_RUNTIME_PROVIDER"] == "openai"
    assert not any("API_KEY" in key for key in env)
    with pytest.raises(ValueError, match="CONFIGURATION_INVALID"):
        setup_client(
            "codex",
            source,
            settings.model_copy(update={"runtime_model": "sk-synthetic-fixture-not-a-real-key"}),
            tmp_path / "client/config.toml",
        )
    with pytest.raises(ValueError, match="DESTINATION_INVALID"):
        BrowserProviderDisclosure.model_validate(
            {**disclosure.model_dump(), "endpoint": "https://generativelanguage.googleapis.com"}
        )


@pytest.mark.parametrize("unsafe", ["oversize", "secret", "bad_image", "late_bad_image"])
def test_entire_export_is_preflighted_before_any_call(monkeypatch, unsafe):
    request = request_for()
    calls = []
    monkeypatch.setattr(visual, "_generate", lambda *args: calls.append(args))
    if unsafe == "oversize":
        request = request.model_copy(update={"editable_files": {"src/card.scss": "a" * 32769}})
    if unsafe == "secret":
        request = request.model_copy(
            update={"editable_files": {"src/card.scss": "sk-synthetic-fixture-not-a-real-key"}}
        )

    def image_reader(image):
        if unsafe == "bad_image" or (
            unsafe == "late_bad_image" and image.case_key == request.plan.coverage[-1]
        ):
            return b"wrong-image"
        return png(image.viewport)

    with pytest.raises(ValueError, match="BROWSER_PROVIDER_"):
        visual.review_with_provider(configured(), request, image_reader, lambda: None)
    assert not calls


@pytest.mark.parametrize("provider", ["openai", "gemini"])
@pytest.mark.parametrize("failure", ["exception", "refusal", "invalid", "incomplete"])
def test_sdk_errors_are_sanitized_and_do_not_create_review(monkeypatch, provider, failure):
    import openai
    from google import genai
    from google.genai import types

    class Client:
        def __init__(self, **kwargs):
            self.responses = SimpleNamespace(parse=self.call)
            self.models = SimpleNamespace(generate_content=self.call)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def call(self, **kwargs):
            if failure == "exception":
                raise RuntimeError("confidential transport details")
            if provider == "openai":
                return SimpleNamespace(
                    status="incomplete" if failure == "incomplete" else "completed",
                    output_parsed=None
                    if failure == "refusal"
                    else {"invalid": "confidential details"},
                )
            return SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        finish_reason=types.FinishReason.MAX_TOKENS
                        if failure == "incomplete"
                        else types.FinishReason.STOP
                    )
                ],
                text=None if failure == "refusal" else "confidential details",
            )

    monkeypatch.setattr(openai, "OpenAI", Client)
    monkeypatch.setattr(genai, "Client", Client)
    with pytest.raises(ValueError, match="BROWSER_PROVIDER_REVIEW_FAILED") as error:
        visual.review_with_provider(
            configured(provider), request_for(), lambda i: png(i.viewport), lambda: None
        )
    assert "confidential" not in str(error.value)


@pytest.mark.parametrize(
    "invalid", ["hash", "rules", "case", "scope", "uncited", "secret", "conflict"]
)
def test_model_output_cannot_forge_evidence_or_expand_repairs(monkeypatch, invalid):
    request = request_for()

    def generate(disclosure, instructions, metadata, images):
        key = json.loads(metadata)["case_key"]
        result = response_for(request, key, "spacing")
        case = result.case
        if invalid == "hash":
            case = case.model_copy(update={"screenshot_sha256": "0" * 64})
        if invalid == "rules":
            case = case.model_copy(update={"checks": (case.checks[0],) * 8})
        if invalid == "case":
            case = case.model_copy(update={"case_key": "unknown"})
        repairs = ()
        if invalid in {"scope", "uncited", "secret", "conflict"}:
            repairs = (
                UIRepair(
                    path="src/other.scss" if invalid == "scope" else "src/card.scss",
                    text="sk-synthetic-fixture-not-a-real-key"
                    if invalid == "secret"
                    else (key if invalid == "conflict" else ".card { padding: 20px; }"),
                    case_keys=(key,),
                    rule_ids=("typography" if invalid == "uncited" else "spacing",),
                ),
            )
        return result.model_copy(update={"case": case, "repairs": repairs})

    monkeypatch.setattr(visual, "_generate", generate)
    with pytest.raises(ValueError, match="BROWSER_"):
        visual.review_with_provider(configured(), request, lambda i: png(i.viewport), lambda: None)


def test_revocation_after_first_response_stops_further_transfer(monkeypatch):
    request = request_for()
    calls = []

    def generate(disclosure, instructions, metadata, images):
        calls.append(metadata)
        return response_for(request, json.loads(metadata)["case_key"])

    def fence():
        if calls:
            raise ValueError("NATIVE_CONSENT_REVOKED")

    monkeypatch.setattr(visual, "_generate", generate)
    with pytest.raises(ValueError, match="REVOKED"):
        visual.review_with_provider(configured(), request, lambda i: png(i.viewport), fence)
    assert len(calls) == 1


def enable_provider(runtime):
    settings = runtime.settings.model_copy(
        update={
            "browser_review_mode": "provider",
            "browser_provider_export": True,
            "runtime_provider": "openai",
            "runtime_model": "test-vision-model",
        }
    )
    runtime.settings = runtime.browser_gate.settings = settings


def passing_response(disclosure, instructions, metadata, images):
    data = json.loads(metadata)
    from migration_agent.domain.browser_validation import CaseReview, ReviewCheck

    return visual.CaseVisualResponse(
        case=CaseReview(
            case_key=data["case_key"],
            screenshot_sha256=data["images_in_order"][0]["sha256"],
            source_sha256=data["images_in_order"][1]["sha256"] if len(images) == 2 else None,
            checks=tuple(
                ReviewCheck(rule_id=r["id"], verdict="pass", explanation="Inspected fixture image.")
                for r in data["rules"]
            ),
        )
    )


def test_complete_provider_review_is_cached_and_policy_changes_recapture(
    browser_workflow, monkeypatch
):
    runtime, plan_id, step_id, _, _, calls, _ = browser_workflow
    enable_provider(runtime)
    reviews = []

    def generate(*args):
        reviews.append(args[2])
        return passing_response(*args)

    monkeypatch.setattr(visual, "_generate", generate)
    first = validate_ui(browser_workflow)
    assert first.state == Lifecycle.VALIDATION_PASSED
    assert first.approval_nonce is None
    assert validate_ui(browser_workflow).state == Lifecycle.VALIDATION_PASSED
    assert len(reviews) == 2 and calls == ["ui"]
    runtime.browser_gate.settings = runtime.settings.model_copy(
        update={"runtime_model": "new-vision-model"}
    )
    with pytest.raises(ValueError, match="BROWSER_EVIDENCE_STALE"):
        runtime.apply_service.approve(plan_id, step_id, HumanFixture())
    second = validate_ui(browser_workflow)
    assert second.browser_evidence.capture.capture_id != first.browser_evidence.capture.capture_id
    assert calls == ["ui", "ui"] and len(reviews) == 4


def test_automatic_provider_repair_recaptures_then_runs_optional_e2e_last(
    browser_workflow, monkeypatch
):
    runtime, plan_id, step_id, plan, config, calls, _ = browser_workflow
    plan = ui_plan(e2e_enabled=True, e2e_cases=plan.cases)
    config.write_text(plan.model_dump_json(), encoding="utf-8")
    enable_provider(runtime)
    captures = []

    def generate(disclosure, instructions, metadata, images):
        data = json.loads(metadata)
        if data["capture_id"] not in captures:
            captures.append(data["capture_id"])
        result = passing_response(disclosure, instructions, metadata, images)
        if len(captures) == 1:
            checks = tuple(
                check.model_copy(update={"verdict": "fail"})
                if check.rule_id == "spacing"
                else check
                for check in result.case.checks
            )
            path = next(path for path in data["editable_files"] if path.endswith(".scss"))
            return visual.CaseVisualResponse(
                case=result.case.model_copy(update={"checks": checks}),
                repairs=(
                    UIRepair(
                        path=path,
                        text=".user-card { padding: 16px; max-width: 100%; }\n",
                        case_keys=(data["case_key"],),
                        rule_ids=("spacing",),
                    ),
                ),
            )
        return result

    monkeypatch.setattr(visual, "_generate", generate)
    service = BoundedRepairService(None, LocalWorkspaceAdapter(), max_budget=3)
    result, attempts = service.prepare_workflow(
        runtime, runtime.store.get_plan(plan_id), step_id, False, 3
    )
    assert result.state == Lifecycle.VALIDATION_PASSED
    assert result.browser_evidence.e2e_status == "PASSED"
    assert result.browser_repair_count == 1 and len(attempts) == 1
    assert len(captures) == 2 and calls == ["ui", "ui", "e2e"]
    assert result.approval_nonce is None and runtime.proposals.evidence.repository_state().clean
    runtime.apply_service.approve(plan_id, step_id, HumanFixture())
    assert (
        runtime.apply_service.apply(plan_id, step_id, result.changeset_id).status.value == "APPLIED"
    )


def test_provider_failure_preserves_pending_capture_without_cached_partial_review(
    browser_workflow, monkeypatch
):
    runtime, *_ = browser_workflow
    enable_provider(runtime)
    monkeypatch.setattr(
        visual,
        "_generate",
        lambda *args: (_ for _ in ()).throw(ValueError("BROWSER_PROVIDER_REVIEW_FAILED")),
    )
    record = validate_ui(browser_workflow)
    assert record.state == Lifecycle.VALIDATION_FAILED
    assert record.browser_evidence.status == "REVIEW_REQUIRED"
    assert (
        runtime.store.get_browser_review(
            record.project_id, record.browser_evidence.capture.capture_id
        )
        is None
    )
    monkeypatch.setattr(visual, "_generate", passing_response)
    assert validate_ui(browser_workflow).state == Lifecycle.VALIDATION_PASSED


def test_real_native_consent_binds_disclosure_and_revocation(native, tmp_path):
    runtime, record, commands, lease = native
    config = tmp_path / "browser-plan.json"
    config.write_text(ui_plan().model_dump_json(), encoding="utf-8")
    browser = tmp_path / "browser.exe"
    browser.write_bytes(b"external browser identity fixture; never executed")
    entry = runtime.settings.native_toolchain_root / "node_modules/playwright-core/index.js"
    entry.parent.mkdir(parents=True)
    entry.write_text("// external Playwright identity fixture", encoding="utf-8")
    settings = runtime.settings.model_copy(
        update={
            "browser_validation_plan": config,
            "native_browser_path": browser,
            "browser_review_mode": "provider",
            "browser_provider_export": True,
            "runtime_provider": "openai",
            "runtime_model": "test-vision-model",
        }
    )
    runtime.settings = runtime.runner.settings = settings
    consent = authorize(native)
    provenance = runtime.runner.prepare(record, commands, lease)
    assert provenance.policy.browser_provider_disclosure == visual.provider_disclosure(settings)
    runtime.runner.verify_browser_session(record, provenance)
    runtime.runner.settings = settings.model_copy(update={"runtime_model": "changed-model"})
    with pytest.raises(ValueError, match="BROWSER_PROVIDER_POLICY_CHANGED"):
        runtime.runner.verify_browser_session(record, provenance)
    runtime.runner.settings = settings
    runtime.store.revoke_native_consent(record.project_id, consent.consent_id)
    with pytest.raises(ValueError, match="NATIVE_CONSENT"):
        runtime.runner.verify_browser_session(record, provenance)
