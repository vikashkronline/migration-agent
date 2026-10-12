"""Technical rule registry and coverage checks for the existing Angular workflow."""

from pathlib import Path

from pydantic import ValidationError

from migration_agent.adapters.filesystem import read_repository_text
from migration_agent.domain.changeset import FileOperation
from migration_agent.domain.host_workflow import ValidationExecution
from migration_agent.domain.rules import (
    ReviewFile,
    Rule,
    RuleEnforcement,
    RuleEvaluation,
    RuleOutcome,
    RuleRegistry,
)
from migration_agent.domain.validation import ValidationStatus

_APPLICABILITY_TYPES = {
    "FILES",
    "FRAMEWORK",
    "AST",
    "E2E",
    "SPEC_TS",
    "TS",
    "HTML",
    "SCSS",
    "OTHER",
}


def load_rule_registry(path: Path | None = None) -> RuleRegistry:
    selected = (
        path or Path(__file__).parents[1] / "resources" / "rules" / "ember-angular-baseline.json"
    )
    try:
        selected = selected.expanduser().absolute()
        if any(
            parent.is_symlink() or parent.is_junction() for parent in (selected, *selected.parents)
        ):
            raise ValueError("RULE_REGISTRY_INVALID: linked registry paths are unsupported.")
        text = read_repository_text(selected.absolute().parent, selected.name)
        registry = RuleRegistry.model_validate_json(text)
        if any(set(rule.applies_to) - _APPLICABILITY_TYPES for rule in registry.rules):
            raise ValueError("RULE_REGISTRY_INVALID: unsupported Angular applicability.")
        return registry
    except (ValidationError, UnicodeError, OSError, ValueError) as error:
        raise ValueError(
            "RULE_REGISTRY_INVALID: select a safe, bounded, supported JSON registry."
        ) from error


class AngularRuleEvaluator:
    """No semantic rule is inferred from prose or claimed complete without evidence."""

    def applicable_rules(self, file: ReviewFile, registry: RuleRegistry) -> tuple[Rule, ...]:
        name = file.path.casefold()
        types = {"FILES", "FRAMEWORK", "AST"}
        if name.endswith((".cy.ts", ".e2e.ts")):
            types.update(("E2E", "TS"))
        elif name.endswith(".spec.ts"):
            types.update(("SPEC_TS", "TS"))
        elif name.endswith(".ts"):
            types.add("TS")
        elif name.endswith((".html", ".htm")):
            types.add("HTML")
        elif name.endswith((".scss", ".sass", ".css", ".less")):
            types.add("SCSS")
        else:
            types.add("OTHER")
        return tuple(rule for rule in registry.rules if types.intersection(rule.applies_to))

    def evaluate(
        self, file: ReviewFile, rule: Rule, execution: ValidationExecution | None
    ) -> RuleEvaluation:
        outcome = RuleOutcome.BLOCKED
        summary = "No supported deterministic evaluator; this check remains blocked."
        evidence: tuple[str, ...] = ()
        line = None
        evaluator = "angular-rules-v1:unimplemented"
        if "AST" in rule.applies_to:
            evaluator = "angular-rules-v1:source-analysis-obligation"
            summary = (
                "Source AST evidence is unavailable in G1; analysis obligations remain blocked."
            )
        elif rule.evaluator_id == "line-endings":
            evaluator = "angular-rules-v1:line-endings"
            if file.operation == FileOperation.DELETE:
                summary = (
                    "Deleted file requires dependency review; formatting cannot establish safety."
                )
            elif file.content_bytes is not None:
                position = file.content_bytes.find(b"\r")
                outcome = RuleOutcome.PASS if position == -1 else RuleOutcome.FAIL
                summary = (
                    "Candidate uses LF line endings."
                    if position == -1
                    else "Candidate contains CR line endings."
                )
                evidence = ("candidate:" + file.content_digest,)
                if position != -1:
                    line = file.content_bytes[:position].count(b"\n") + 1
        elif rule.evaluator_id == "validation-profiles":
            evaluator = "angular-rules-v1:validation-profiles"
            if (
                execution is None
                or execution.schema_version not in {2, 3}
                or execution.provenance is None
                or not execution.provenance.cleanup_verified
            ):
                summary = (
                    "Verified execution provenance is required; "
                    "commands were not run by this review."
                )
            else:
                results = tuple(
                    result
                    for result in execution.results
                    if result.profile in rule.required_profiles
                )
                missing = set(rule.required_profiles) - {result.profile for result in results}
                failed = any(
                    result.status != ValidationStatus.PASSED or result.exit_code != 0
                    for result in results
                )
                outcome = (
                    RuleOutcome.BLOCKED
                    if missing
                    else RuleOutcome.FAIL
                    if failed
                    else RuleOutcome.PASS
                )
                summary = (
                    "Missing required validation profiles: " + ", ".join(sorted(missing))
                    if missing
                    else "Recorded required commands failed."
                    if failed
                    else "Recorded required commands passed."
                )
                evidence = tuple(
                    "validation-profile:" + profile.value
                    for profile in sorted(rule.required_profiles)
                )
        elif rule.enforcement == RuleEnforcement.MANUAL:
            evaluator = "angular-rules-v1:manual-obligation"
            outcome = RuleOutcome.PENDING_MANUAL
            summary = rule.text
        return RuleEvaluation(
            rule_id=rule.id,
            outcome=outcome,
            severity=rule.severity,
            evaluator=evaluator,
            summary=summary,
            evidence=evidence,
            line_number=line,
        )
