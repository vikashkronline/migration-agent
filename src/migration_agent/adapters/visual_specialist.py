"""Opt-in, bounded vision requests to fixed provider destinations."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.application.browser_validation import evaluate_review
from migration_agent.config import Settings
from migration_agent.domain.browser_validation import (
    BrowserImage,
    BrowserReview,
    CaseReview,
    UIRepair,
)
from migration_agent.domain.execution import BrowserProviderDisclosure
from migration_agent.domain.redaction import RedactionPolicy

if TYPE_CHECKING:
    from migration_agent.adapters.browser_validation import BrowserReviewRequest


class CaseVisualResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case: CaseReview
    repairs: tuple[UIRepair, ...] = Field(default=(), max_length=100)


def provider_disclosure(settings: Settings) -> BrowserProviderDisclosure | None:
    if settings.browser_review_mode != "provider" or not settings.browser_provider_export:
        return None
    if settings.runtime_provider not in {"openai", "gemini"} or not settings.effective_model:
        raise ValueError(
            "BROWSER_PROVIDER_CONFIGURATION_REQUIRED: select a provider and vision model."
        )
    if RedactionPolicy().contains_secret(settings.effective_model):
        raise ValueError(
            "BROWSER_PROVIDER_CONFIGURATION_INVALID: non-secret model identifier required."
        )
    try:
        return BrowserProviderDisclosure.model_validate(
            {
                "provider": settings.runtime_provider,
                "model": settings.effective_model,
                "endpoint": "https://api.openai.com/v1"
                if settings.runtime_provider == "openai"
                else "https://generativelanguage.googleapis.com",
            }
        )
    except ValueError:
        raise ValueError(
            "BROWSER_PROVIDER_CONFIGURATION_INVALID: invalid model identifier."
        ) from None


def _generate(
    disclosure: BrowserProviderDisclosure,
    instructions: str,
    metadata: str,
    images: tuple[bytes, ...],
) -> CaseVisualResponse:
    """SDKs obtain credentials internally; their errors and payloads are never logged."""
    try:
        if disclosure.provider == "openai":
            from openai import OpenAI
            from openai.types.responses import EasyInputMessageParam, ResponseInputContentParam

            content: list[ResponseInputContentParam] = [{"type": "input_text", "text": metadata}]
            content.extend(
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii"),
                    "detail": "high",
                }
                for data in images
            )
            message: EasyInputMessageParam = {"role": "user", "content": content}
            with OpenAI(
                base_url=disclosure.endpoint,
                timeout=disclosure.timeout_seconds_per_case,
                max_retries=0,
            ) as client:
                result = client.responses.parse(
                    model=disclosure.model,
                    instructions=instructions,
                    input=[message],
                    text_format=CaseVisualResponse,
                    store=False,
                    max_output_tokens=disclosure.max_output_tokens_per_case,
                )
                if result.status != "completed" or result.output_parsed is None:
                    raise ValueError("Incomplete or refused response.")
                response = CaseVisualResponse.model_validate(result.output_parsed)
        else:
            from google import genai
            from google.genai import types

            with genai.Client(
                vertexai=False,
                enterprise=False,
                http_options=types.HttpOptions(
                    base_url=disclosure.endpoint,
                    timeout=disclosure.timeout_seconds_per_case * 1000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client:
                generated = client.models.generate_content(
                    model=disclosure.model,
                    contents=types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=metadata),
                            *(
                                types.Part.from_bytes(data=data, mime_type="image/png")
                                for data in images
                            ),
                        ],
                    ),
                    config=types.GenerateContentConfig(
                        system_instruction=instructions,
                        response_mime_type="application/json",
                        response_schema=CaseVisualResponse,
                        max_output_tokens=disclosure.max_output_tokens_per_case,
                    ),
                )
                if (
                    not generated.candidates
                    or len(generated.candidates) != 1
                    or generated.candidates[0].finish_reason != types.FinishReason.STOP
                    or not generated.text
                    or len(generated.text.encode("utf-8")) > 128 * 1024
                ):
                    raise ValueError("Incomplete or refused response.")
                response = CaseVisualResponse.model_validate_json(generated.text)
        if len(response.model_dump_json().encode("utf-8")) > 128 * 1024:
            raise ValueError("Response exceeds limit.")
        return response
    except Exception:
        raise ValueError(
            "BROWSER_PROVIDER_REVIEW_FAILED: unavailable, refused, incomplete or invalid visual "
            "response; configure credentials and an image-capable model."
        ) from None


def review_with_provider(
    settings: Settings,
    request: BrowserReviewRequest,
    image_reader: Callable[[BrowserImage], bytes],
    fence: Callable[[], None],
) -> BrowserReview:
    disclosure = provider_disclosure(settings)
    if disclosure is None:
        raise ValueError(
            "BROWSER_PROVIDER_DISCLOSURE_REQUIRED: enable trusted launcher export opt-in."
        )
    plan, capture = request.plan, request.capture
    evaluate_review(plan, capture, None)
    if sum(len(text.encode("utf-8")) for text in request.editable_files.values()) > 32768:
        raise ValueError("BROWSER_PROVIDER_DATA_LIMIT: editable code exceeds 32 KiB.")
    cases = {
        f"{case.id}--{viewport.id}": case for case in plan.cases for viewport in plan.viewports
    }
    targets = {image.case_key: image for image in capture.images if image.origin == "target"}
    sources = {image.case_key: image for image in capture.images if image.origin == "source"}
    responses: list[CaseVisualResponse] = []
    # Preflight the complete export before making any network request.
    payloads: list[tuple[str, tuple[bytes, ...]]] = []
    for key in plan.coverage:
        fence()
        selected = (targets[key],) + ((sources[key],) if key in sources else ())
        images = tuple(image_reader(image) for image in selected)
        if sum(map(len, images)) > disclosure.max_image_bytes_per_case or any(
            data[:8] != b"\x89PNG\r\n\x1a\n" or hashlib.sha256(data).hexdigest() != image.sha256
            for image, data in zip(selected, images, strict=True)
        ):
            raise ValueError(
                "BROWSER_PROVIDER_IMAGE_INVALID: verified bounded PNG evidence required."
            )
        metadata = json.dumps(
            {
                "capture_id": capture.capture_id,
                "case_key": key,
                "case": cases[key].model_dump(mode="json"),
                "source_case": next(
                    (
                        case.model_dump(mode="json")
                        for case in plan.source_cases
                        if case.id == cases[key].id
                    ),
                    None,
                ),
                "source_identity": plan.source_identity,
                "rules": [rule.model_dump(mode="json") for rule in plan.rules],
                "design_requirements": plan.design_requirements,
                "approved_design_changes": plan.approved_design_changes,
                "images_in_order": [
                    image.model_dump(mode="json", exclude={"filename"}) for image in selected
                ],
                "editable_files": dict(sorted(request.editable_files.items())),
                "response_scope": "Review only this case. Cite only this case in proposed repairs.",
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        if len(
            metadata.encode("utf-8")
        ) > disclosure.max_metadata_bytes_per_case or RedactionPolicy().contains_secret(metadata):
            raise ValueError(
                "BROWSER_PROVIDER_DATA_UNSAFE: bounded non-secret synthetic data required."
            )
        payloads.append((metadata, images))
    for key, (metadata, images) in zip(plan.coverage, payloads, strict=True):
        fence()
        response = _generate(disclosure, request.instructions, metadata, images)
        fence()
        if (
            response.case.case_key != key
            or response.case.screenshot_sha256 != targets[key].sha256
            or response.case.source_sha256 != (sources[key].sha256 if key in sources else None)
            or any(set(repair.case_keys) != {key} for repair in response.repairs)
        ):
            raise ValueError(
                "BROWSER_PROVIDER_REVIEW_INVALID: case or screenshot citation mismatch."
            )
        responses.append(response)
    patches: dict[str, UIRepair] = {}
    for response in responses:
        for repair in response.repairs:
            previous = patches.get(repair.path)
            if previous:
                if previous.text != repair.text:
                    raise ValueError(
                        "BROWSER_PROVIDER_REPAIR_CONFLICT: incompatible full-file repairs."
                    )
                repair = repair.model_copy(
                    update={
                        "case_keys": tuple(sorted(set(previous.case_keys + repair.case_keys))),
                        "rule_ids": tuple(sorted(set(previous.rule_ids + repair.rule_ids))),
                    }
                )
            patches[repair.path] = repair
    review = BrowserReview(
        capture_id=capture.capture_id,
        reviewer=f"provider:{disclosure.provider}:{disclosure.model}",
        cases=tuple(response.case for response in responses),
        repairs=tuple(patches[path] for path in sorted(patches)),
    )
    evaluate_review(plan, capture, review)
    if not set(patches) <= set(request.editable_files):
        raise ValueError("BROWSER_REPAIR_SCOPE_INVALID: provider repair expands editable scope.")
    fence()
    return review
