"""Deterministic coverage and evidence checks around untrusted visual analysis."""

from migration_agent.domain.browser_validation import (
    BrowserCapture,
    BrowserEvidence,
    BrowserReview,
    BrowserValidationPlan,
)
from migration_agent.domain.redaction import RedactionPolicy


def evaluate_review(
    plan: BrowserValidationPlan, capture: BrowserCapture, review: BrowserReview | None
) -> BrowserEvidence:
    expected = set(plan.coverage)
    targets = {image.case_key: image for image in capture.images if image.origin == "target"}
    sources = {image.case_key: image for image in capture.images if image.origin == "source"}
    if len(sources) != len([image for image in capture.images if image.origin == "source"]):
        raise ValueError("BROWSER_EVIDENCE_INVALID: duplicate source capture cells.")
    if any(not image.ready for image in sources.values()):
        raise ValueError(
            "BROWSER_SOURCE_NOT_READY: selected source baseline could not reach its declared state."
        )
    if (
        capture.config_digest != plan.digest
        or not capture.cleanup_verified
        or set(targets) != expected
        or len(targets) != len([image for image in capture.images if image.origin == "target"])
        or (set(sources) != expected if plan.source_url else bool(sources))
    ):
        raise ValueError("BROWSER_EVIDENCE_INVALID: coverage, policy or cleanup is incomplete.")
    issues = [
        f"{key}: {finding.rule_id}: {finding.description}"
        for key, image in sorted(targets.items())
        for finding in image.findings
    ]
    if review is None:
        return BrowserEvidence(
            status="REVIEW_REQUIRED",
            capture=capture,
            issues=tuple(issues),
            max_repairs=plan.max_repairs,
            e2e_status="PENDING" if plan.e2e_enabled else "NOT_RUN",
        )
    if (
        review.capture_id != capture.capture_id
        or len(review.cases) != len(expected)
        or {case.case_key for case in review.cases} != expected
        or RedactionPolicy().contains_secret(review.model_dump_json())
    ):
        raise ValueError("BROWSER_REVIEW_INVALID: exact capture coverage and safe output required.")
    required = {rule.id for rule in plan.rules}
    failed: set[tuple[str, str]] = set()
    for case in sorted(review.cases, key=lambda item: item.case_key):
        image = targets[case.case_key]
        source = sources.get(case.case_key)
        if (
            case.screenshot_sha256 != image.sha256
            or case.source_sha256 != (source.sha256 if source else None)
            or len(case.checks) != len(required)
            or {check.rule_id for check in case.checks} != required
        ):
            raise ValueError("BROWSER_REVIEW_INVALID: fabricated references or omitted standards.")
        for check in sorted(case.checks, key=lambda item: item.rule_id):
            if check.verdict != "pass":
                failed.add((case.case_key, check.rule_id))
                issues.append(
                    f"{case.case_key}: {check.rule_id}: {check.verdict}: {check.explanation}"
                )
        failed.update((case.case_key, finding.rule_id) for finding in image.findings)
    paths: set[str] = set()
    for repair in review.repairs:
        if (
            repair.path in paths
            or not set(repair.case_keys) <= expected
            or not set(repair.rule_ids) <= required
            or not any(
                (key, rule) in failed for key in repair.case_keys for rule in repair.rule_ids
            )
        ):
            raise ValueError("BROWSER_REPAIR_INVALID: repairs must cite captured current issues.")
        paths.add(repair.path)
    if sum(len(repair.text.encode("utf-8")) for repair in review.repairs) > 32768:
        raise ValueError("BROWSER_REPAIR_INVALID: proposed bytes exceed repair budget.")
    return BrowserEvidence(
        status="FAILED" if issues else "PASSED",
        capture=capture,
        review=review,
        max_repairs=plan.max_repairs,
        issues=tuple(sorted(set(issues))),
        e2e_status="PENDING" if plan.e2e_enabled else "NOT_RUN",
    )
