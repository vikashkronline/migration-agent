"""Read a bounded, non-secret browser plan from the trusted launcher."""

from pathlib import Path

from migration_agent.config import Settings
from migration_agent.domain.browser_validation import BrowserValidationPlan
from migration_agent.domain.redaction import RedactionPolicy


def load_browser_plan(settings: Settings) -> BrowserValidationPlan:
    from migration_agent.adapters.validation_backend import safe_path

    if settings.browser_validation_plan is None:
        raise ValueError("BROWSER_PLAN_REQUIRED: configure AGENT_BROWSER_VALIDATION_PLAN.")
    path = safe_path(Path(settings.browser_validation_plan))
    if not path.is_file() or RedactionPolicy.is_sensitive_path(path) or path.stat().st_size > 65536:
        raise ValueError("BROWSER_PLAN_INVALID: bounded regular non-secret plan required.")
    text = path.read_text(encoding="utf-8")
    if RedactionPolicy().contains_secret(text):
        raise ValueError("BROWSER_PLAN_INVALID: browser plans cannot contain credentials.")
    plan = BrowserValidationPlan.model_validate_json(text)
    if not plan.build_root.startswith("dist/"):
        raise ValueError("BROWSER_PLAN_INVALID: serve an explicit staged dist subdirectory.")
    return plan
