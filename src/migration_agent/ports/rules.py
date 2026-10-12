"""Framework-owned rule applicability and deterministic checks."""

from typing import Protocol

from migration_agent.domain.host_workflow import ValidationExecution
from migration_agent.domain.rules import ReviewFile, Rule, RuleEvaluation, RuleRegistry


class RuleEvaluatorPort(Protocol):
    def applicable_rules(self, file: ReviewFile, registry: RuleRegistry) -> tuple[Rule, ...]: ...

    def evaluate(
        self, file: ReviewFile, rule: Rule, execution: ValidationExecution | None
    ) -> RuleEvaluation: ...
