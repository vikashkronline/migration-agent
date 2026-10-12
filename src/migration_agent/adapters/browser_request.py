"""Fixed browser-worker launch manifest, never a model-generated program."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.browser_validation import BrowserValidationPlan


class BrowserWorkerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    plan: BrowserValidationPlan
    phase: Literal["ui", "e2e"]
    build_root: str
    output_root: str
    browser_path: str
    playwright_entry: str
    chromium_sandbox: bool
    case_keys: tuple[str, ...] = Field(min_length=1, max_length=4)
