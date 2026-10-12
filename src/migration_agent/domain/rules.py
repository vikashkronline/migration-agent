"""Versioned rule metadata and evidence-backed, report-only review results."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, computed_field, model_validator

from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import FileOperation
from migration_agent.domain.host_workflow import normalized_path
from migration_agent.domain.validation import ValidationProfile


class RuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class RuleSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKER = "BLOCKER"


class RuleEnforcement(StrEnum):
    LINT = "LINT"
    COMMAND = "COMMAND"
    LINT_AND_MANUAL = "LINT_AND_MANUAL"
    SCRIPT_AND_MANUAL = "SCRIPT_AND_MANUAL"
    MANUAL = "MANUAL"
    MANAGER = "MANAGER"
    SCHEMA_AND_MANUAL = "SCHEMA_AND_MANUAL"
    TEST = "TEST"


class RuleSource(RuleModel):
    reference: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=64)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Rule(RuleModel):
    id: str = Field(pattern=r"^RULE-[A-Z0-9]+(?:-[A-Z0-9]+)+$")
    category: str = Field(min_length=1, max_length=64)
    severity: RuleSeverity
    applies_to: tuple[str, ...] = Field(alias="appliesTo", min_length=1, max_length=32)
    enforcement: RuleEnforcement
    safe_autofix: StrictBool = Field(alias="safeAutofix")
    text: str = Field(min_length=1, max_length=8192)
    evaluator_id: Literal["line-endings", "validation-profiles"] | None = Field(
        default=None, alias="evaluatorId"
    )
    required_profiles: tuple[ValidationProfile, ...] = Field(
        default=(), alias="requiredProfiles", max_length=4
    )

    @model_validator(mode="after")
    def consistent(self) -> "Rule":
        if any(not value or not value.strip() for value in self.applies_to):
            raise ValueError("RULE_INVALID: applicability must be explicit.")
        if len(set(self.applies_to)) != len(self.applies_to):
            raise ValueError("RULE_INVALID: duplicate applicability.")
        if len(set(self.required_profiles)) != len(self.required_profiles):
            raise ValueError("RULE_INVALID: duplicate validation profiles.")
        if (self.evaluator_id == "validation-profiles") != bool(self.required_profiles):
            raise ValueError("RULE_INVALID: validation evaluator requires explicit profiles.")
        expected = {
            "line-endings": RuleEnforcement.LINT,
            "validation-profiles": RuleEnforcement.COMMAND,
        }
        if self.evaluator_id is not None and self.enforcement != expected[self.evaluator_id]:
            raise ValueError("RULE_INVALID: evaluator and enforcement do not agree.")
        return self


class RuleRegistry(RuleModel):
    schema_version: Literal[1] = 1
    profile_id: str = Field(
        default="external-registry", alias="profileId", min_length=1, max_length=128
    )
    version: str = Field(min_length=1, max_length=64)
    authority: str = Field(min_length=1, max_length=8192)
    source: RuleSource | None = None
    rules: tuple[Rule, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def unique_rules(self) -> "RuleRegistry":
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("RULE_REGISTRY_INVALID: duplicate rule IDs.")
        return self

    @property
    def digest(self) -> str:
        data = self.model_dump(mode="json")
        data["rules"] = [
            rule.model_dump(mode="json") for rule in sorted(self.rules, key=lambda r: r.id)
        ]
        return compute_canonical_digest(data)


class RuleOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    PENDING_MANUAL = "PENDING_MANUAL"


class RuleEvaluation(RuleModel):
    rule_id: str = Field(min_length=1)
    outcome: RuleOutcome
    severity: RuleSeverity
    evaluator: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()
    line_number: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def evidence_required(self) -> "RuleEvaluation":
        if self.outcome in {RuleOutcome.PASS, RuleOutcome.FAIL} and (
            not self.evidence or any(not value.strip() for value in self.evidence)
        ):
            raise ValueError("RULE_EVIDENCE_REQUIRED: completed checks require evidence.")
        return self


class ReviewFile(RuleModel):
    path: str
    operation: FileOperation
    content_digest: str
    content_bytes: bytes | None = Field(default=None, repr=False, exclude=True)


class FileRuleReview(RuleModel):
    path: str
    operation: FileOperation
    content_digest: str
    applicable_rule_ids: tuple[str, ...]
    evaluations: tuple[RuleEvaluation, ...]

    @model_validator(mode="after")
    def complete_inventory(self) -> "FileRuleReview":
        normalized_path(self.path)
        evaluated_ids = tuple(evaluation.rule_id for evaluation in self.evaluations)
        if (
            len(set(self.applicable_rule_ids)) != len(self.applicable_rule_ids)
            or evaluated_ids != self.applicable_rule_ids
        ):
            raise ValueError(
                "RULE_COVERAGE_INVALID: each applicable rule needs exactly one outcome."
            )
        return self


class StandardsReviewReport(RuleModel):
    schema_version: Literal[1] = 1
    report_only: Literal[True] = True
    project_id: str
    run_id: str
    plan_id: str
    step_id: str
    record_version: int
    changeset_id: str
    changeset_digest: str
    base_revision: str
    worktree_fingerprint: str
    policy_digest: str
    staging_fingerprint: str
    validation_digest: str | None
    profile_id: str
    profile_version: str
    registry_digest: str
    files: tuple[FileRuleReview, ...] = Field(min_length=1, max_length=100)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_files(self) -> int:
        return len(self.files)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def applicable_check_count(self) -> int:
        return sum(len(file.applicable_rule_ids) for file in self.files)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def completed_check_count(self) -> int:
        return sum(
            evaluation.outcome in {RuleOutcome.PASS, RuleOutcome.FAIL}
            for file in self.files
            for evaluation in file.evaluations
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> Literal["PASS", "FAIL", "BLOCKED"]:
        evaluations = [evaluation for file in self.files for evaluation in file.evaluations]
        if any(not file.applicable_rule_ids for file in self.files) or any(
            evaluation.outcome in {RuleOutcome.BLOCKED, RuleOutcome.PENDING_MANUAL}
            for evaluation in evaluations
        ):
            return "BLOCKED"
        if any(
            evaluation.outcome == RuleOutcome.FAIL
            and evaluation.severity in {RuleSeverity.ERROR, RuleSeverity.BLOCKER}
            for evaluation in evaluations
        ):
            return "FAIL"
        return "PASS"
