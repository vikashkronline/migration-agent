"""Browser coverage, visual review and optional final journey evidence."""

from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from migration_agent.domain.canonical import compute_canonical_digest

STANDARD_RULES = {
    "spacing": "Consistent spacing, padding and margins against the declared design rules.",
    "alignment": "Consistent alignment, grids and visual hierarchy; no unintended overlap.",
    "typography": "Readable typography, wrapping, truncation and approved colors.",
    "responsive": "Supported widths and zoom reflow without clipping or unwanted overflow.",
    "accessibility": "Accessible names, contrast, keyboard use and visible unobscured focus.",
    "interaction": "Usable controls and expected feedback in the declared UI state.",
    "states": "Correct loading, empty, error, disabled and other declared state presentation.",
    "capability": "All declared visible content and controls remain present and usable.",
}


class BrowserModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or value != path.as_posix()
        or any(p in {"..", "."} for p in path.parts)
        or any(c in value for c in ("\\", ":", "\x00"))
    ):
        raise ValueError("BROWSER_PATH_INVALID: use a normalized relative path.")
    return value


class Viewport(BrowserModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,32}$")
    width: int = Field(ge=240, le=2560)
    height: int = Field(ge=240, le=2560)
    device_scale_factor: float = Field(default=1, ge=1, le=3)
    zoom: float = Field(default=1, ge=1, le=4)

    @model_validator(mode="after")
    def pixel_budget(self) -> "Viewport":
        if self.width * self.height * self.device_scale_factor**2 > 16000000:
            raise ValueError("BROWSER_VIEWPORT_LIMIT: required capture exceeds the pixel budget.")
        return self


class BrowserAction(BrowserModel):
    kind: Literal["click", "fill", "press", "select", "check"]
    selector: str = Field(min_length=1, max_length=256)
    value: str = Field(default="", max_length=1024)


class BrowserAssertion(BrowserModel):
    kind: Literal["visible", "text", "value", "count", "url"]
    selector: str = Field(default="", max_length=256)
    expected: str = Field(default="", max_length=1024)


class GeometryRule(BrowserModel):
    rule_id: Literal["spacing", "alignment", "typography", "accessibility"]
    kind: Literal["gap", "align_left", "font_size", "contrast", "target_size"]
    selector: str = Field(min_length=1, max_length=256)
    peer: str = Field(default="", max_length=256)
    axis: Literal["x", "y"] = "y"
    minimum: float = Field(default=0, ge=0, le=2560)
    maximum: float = Field(default=2560, ge=0, le=2560)

    @model_validator(mode="after")
    def bounds(self) -> "GeometryRule":
        if self.minimum > self.maximum or (self.kind in {"gap", "align_left"} and not self.peer):
            raise ValueError("BROWSER_RULE_INVALID: invalid measurement bounds/peer.")
        return self


class BrowserCase(BrowserModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,32}$")
    route: str = Field(default="/", max_length=256)
    state: str = Field(min_length=1, max_length=256)
    expected: str = Field(min_length=1, max_length=2048)
    ready_selector: str = Field(default="body", min_length=1, max_length=256)
    actions: tuple[BrowserAction, ...] = Field(default=(), max_length=30)
    assertions: tuple[BrowserAssertion, ...] = Field(min_length=1, max_length=30)
    geometry: tuple[GeometryRule, ...] = Field(default=(), max_length=30)

    @field_validator("route")
    @classmethod
    def local_route(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or url.netloc
            or url.scheme
            or url.query
            or ".." in value
            or "\\" in value
            or "%" in value
        ):
            raise ValueError("BROWSER_ROUTE_INVALID: use a local path without queries/traversal.")
        return value


class UIRule(BrowserModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,48}$")
    instruction: str = Field(min_length=1, max_length=2048)


class BrowserValidationPlan(BrowserModel):
    schema_version: Literal[1] = 1
    version: str = Field(min_length=1, max_length=64)
    build_root: str
    viewports: tuple[Viewport, ...] = Field(min_length=1, max_length=8)
    cases: tuple[BrowserCase, ...] = Field(min_length=1, max_length=32)
    rules: tuple[UIRule, ...] = Field(
        default_factory=lambda: tuple(
            UIRule(id=key, instruction=value) for key, value in sorted(STANDARD_RULES.items())
        ),
        min_length=8,
        max_length=24,
    )
    design_requirements: str = Field(min_length=1, max_length=8192)
    test_data_identity: str = Field(min_length=1, max_length=256)
    source_url: str | None = None
    source_identity: str | None = Field(default=None, max_length=256)
    source_cases: tuple[BrowserCase, ...] = Field(default=(), max_length=32)
    test_origins: tuple[str, ...] = Field(default=(), max_length=4)
    approved_design_changes: tuple[str, ...] = Field(default=(), max_length=30)
    e2e_enabled: bool = False
    e2e_cases: tuple[BrowserCase, ...] = Field(default=(), max_length=16)
    max_repairs: int = Field(default=3, ge=0, le=10)
    max_validation_seconds: int = Field(default=600, ge=60, le=1800)
    full_page: bool = True

    _path = field_validator("build_root")(relative_path)

    @model_validator(mode="after")
    def complete(self) -> "BrowserValidationPlan":
        for items in (self.cases, self.viewports, self.rules, self.e2e_cases, self.source_cases):
            if len({item.id for item in items}) != len(items):
                raise ValueError("BROWSER_COVERAGE_INVALID: duplicate IDs.")
        if not set(STANDARD_RULES) <= {rule.id for rule in self.rules}:
            raise ValueError("BROWSER_RULES_REQUIRED: retain all mandatory review dimensions.")
        if len(self.cases) * len(self.viewports) > 64:
            raise ValueError("BROWSER_COVERAGE_INVALID: split coverage above 64 cells.")
        if self.e2e_enabled != bool(self.e2e_cases):
            raise ValueError("BROWSER_E2E_INVALID: enabled journeys require explicit cases.")
        if self.source_url:
            url = urlsplit(self.source_url)
            if (
                url.scheme != "http"
                or url.hostname != "127.0.0.1"
                or not url.port
                or url.username
                or url.password
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
                or not self.source_identity
            ):
                raise ValueError(
                    "BROWSER_SOURCE_INVALID: explicit loopback origin/identity required."
                )
        elif self.source_identity:
            raise ValueError("BROWSER_SOURCE_INVALID: identity requires an explicit source origin.")
        if self.source_cases and (
            not self.source_url
            or {case.id for case in self.source_cases} != {case.id for case in self.cases}
        ):
            raise ValueError(
                "BROWSER_SOURCE_INVALID: source cases must pair with every target case."
            )
        for origin in self.test_origins:
            url = urlsplit(origin)
            if (
                url.scheme != "http"
                or url.hostname != "127.0.0.1"
                or not url.port
                or url.username
                or url.password
                or url.path not in {"", "/"}
                or url.query
                or url.fragment
                or origin.rstrip("/") == (self.source_url or "").rstrip("/")
            ):
                raise ValueError(
                    "BROWSER_TEST_ORIGIN_INVALID: separate explicit loopback test origins required."
                )
        return self

    @property
    def digest(self) -> str:
        return compute_canonical_digest(self.model_dump(mode="json"))

    @property
    def coverage(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                f"{case.id}--{viewport.id}" for case in self.cases for viewport in self.viewports
            )
        )


class ObjectiveFinding(BrowserModel):
    rule_id: str
    description: str = Field(min_length=1, max_length=2048)


class BrowserImage(BrowserModel):
    case_key: str
    origin: Literal["target", "source"]
    filename: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    viewport: Viewport
    ready: bool = True
    capture_height_pixels: int | None = Field(default=None, ge=1, le=16384)
    facts: str = Field(default="", max_length=32768)
    findings: tuple[ObjectiveFinding, ...] = Field(default=(), max_length=100)
    _path = field_validator("filename")(relative_path)


class BrowserCapture(BrowserModel):
    capture_id: str = Field(pattern=r"^browser-[a-f0-9]{32}$")
    project_id: str
    plan_id: str
    step_id: str
    changeset_digest: str
    source_revision: str
    config_digest: str
    build_digest: str
    tool_digest: str
    browser_version: str
    images: tuple[BrowserImage, ...] = Field(min_length=1, max_length=128)
    cleanup_verified: bool
    consent_id: str | None = None
    review_policy_digest: str | None = None


class ReviewCheck(BrowserModel):
    rule_id: str = Field(min_length=1, max_length=48)
    verdict: Literal["pass", "fail", "uncertain"]
    explanation: str = Field(min_length=1, max_length=2048)


class CaseReview(BrowserModel):
    case_key: str
    screenshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checks: tuple[ReviewCheck, ...] = Field(min_length=8, max_length=24)


class UIRepair(BrowserModel):
    path: str
    text: str = Field(max_length=32768)
    case_keys: tuple[str, ...] = Field(min_length=1, max_length=64)
    rule_ids: tuple[str, ...] = Field(min_length=1, max_length=24)
    _path = field_validator("path")(relative_path)


class BrowserReview(BrowserModel):
    capture_id: str
    reviewer: str = Field(min_length=1, max_length=256)
    cases: tuple[CaseReview, ...] = Field(min_length=1, max_length=64)
    repairs: tuple[UIRepair, ...] = Field(default=(), max_length=100)


class JourneyResult(BrowserModel):
    case_id: str
    passed: bool
    details: str = Field(default="", max_length=2048)


class BrowserEvidence(BrowserModel):
    status: Literal["PASSED", "FAILED", "REVIEW_REQUIRED"]
    capture: BrowserCapture
    review: BrowserReview | None = None
    e2e_status: Literal["NOT_RUN", "PASSED", "FAILED", "PENDING"] = "NOT_RUN"
    e2e_results: tuple[JourneyResult, ...] = ()
    issues: tuple[str, ...] = ()
    max_repairs: int = Field(default=3, ge=0, le=10)

    @property
    def passed(self) -> bool:
        return self.status == "PASSED" and self.e2e_status in {"NOT_RUN", "PASSED"}

    @property
    def repairs(self) -> tuple[UIRepair, ...]:
        return self.review.repairs if self.review else ()
