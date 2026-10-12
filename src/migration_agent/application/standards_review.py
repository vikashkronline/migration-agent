"""Reconcile rule outcomes against exact candidate and immutable validation evidence."""

from pathlib import PurePosixPath

from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.changeset import (
    ChangeSet,
    FileOperation,
    compute_changeset_digest,
    compute_file_sha256,
)
from migration_agent.domain.host_workflow import (
    ValidationExecution,
    WorkflowRecord,
    normalized_path,
)
from migration_agent.domain.redaction import RedactionPolicy
from migration_agent.domain.rules import (
    FileRuleReview,
    ReviewFile,
    RuleRegistry,
    StandardsReviewReport,
)
from migration_agent.ports.rules import RuleEvaluatorPort


class StandardsReviewService:
    def review(
        self,
        record: WorkflowRecord,
        changeset: ChangeSet,
        registry: RuleRegistry,
        evaluator: RuleEvaluatorPort,
        execution: ValidationExecution | None = None,
    ) -> StandardsReviewReport:
        if RedactionPolicy().contains_secret(registry.model_dump_json()):
            raise ValueError("RULE_REGISTRY_INVALID: credential-shaped registry content.")
        if (
            changeset.plan_id,
            changeset.step_id,
            changeset.changeset_id,
            changeset.changeset_digest,
            changeset.base_revision,
            changeset.worktree_fingerprint,
        ) != (
            record.plan_id,
            record.step_id,
            record.changeset_id,
            record.changeset_digest,
            record.base_revision,
            record.worktree_fingerprint,
        ) or compute_changeset_digest(changeset) != record.changeset_digest:
            raise ValueError("STANDARDS_ARTIFACT_INVALID: exact artifact binding is required.")
        if not record.staging_fingerprint or not 1 <= len(changeset.changes) <= 100:
            raise ValueError("STANDARDS_ARTIFACT_INVALID: bounded staged evidence is required.")
        if execution is None:
            if record.validation_digest is not None:
                raise ValueError("STANDARDS_VALIDATION_INVALID: recorded execution is missing.")
        elif (
            execution.project_id,
            execution.plan_id,
            execution.step_id,
            execution.changeset_id,
            execution.changeset_digest,
            execution.staging_fingerprint,
            execution.results,
        ) != (
            record.project_id,
            record.plan_id,
            record.step_id,
            record.changeset_id,
            record.changeset_digest,
            record.staging_fingerprint,
            record.validation_results,
        ) or compute_canonical_digest(
            execution.model_dump(mode="json")
        ) != record.validation_digest:
            raise ValueError("STANDARDS_VALIDATION_INVALID: execution does not bind this artifact.")

        files = []
        seen: set[str] = set()
        total_bytes = 0
        for change in sorted(changeset.changes, key=lambda item: item.path):
            normalized_path(change.path)
            if change.old_path is not None or change.path.casefold() in seen:
                raise ValueError("STANDARDS_ARTIFACT_INVALID: renames or duplicate paths.")
            seen.add(change.path.casefold())
            if RedactionPolicy.is_sensitive_path(PurePosixPath(change.path)):
                raise ValueError("STANDARDS_ARTIFACT_INVALID: protected path.")
            content = change.content_bytes
            if change.operation != FileOperation.DELETE:
                if content is None or compute_file_sha256(content) != change.content_digest:
                    raise ValueError("STANDARDS_ARTIFACT_INVALID: missing or altered file bytes.")
                total_bytes += len(content)
                if b"\x00" in content or total_bytes > 32768:
                    raise ValueError("STANDARDS_ARTIFACT_INVALID: binary or oversized content.")
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise ValueError(
                        "STANDARDS_ARTIFACT_INVALID: UTF-8 content required."
                    ) from error
                if RedactionPolicy().contains_secret(text):
                    raise ValueError("STANDARDS_ARTIFACT_INVALID: credential-shaped content.")
            file = ReviewFile(
                path=change.path,
                operation=change.operation,
                content_digest=change.content_digest,
                content_bytes=content,
            )
            rules = sorted(evaluator.applicable_rules(file, registry), key=lambda item: item.id)
            if len({rule.id for rule in rules}) != len(rules) or any(
                rule not in registry.rules for rule in rules
            ):
                raise ValueError("STANDARDS_EVALUATOR_INVALID: applicability is inconsistent.")
            evaluations = tuple(evaluator.evaluate(file, rule, execution) for rule in rules)
            for rule, evaluation in zip(rules, evaluations, strict=True):
                if evaluation.rule_id != rule.id or evaluation.severity != rule.severity:
                    raise ValueError(
                        "STANDARDS_EVALUATOR_INVALID: outcome belongs to another rule."
                    )
            files.append(
                FileRuleReview(
                    path=file.path,
                    operation=file.operation,
                    content_digest=file.content_digest,
                    applicable_rule_ids=tuple(rule.id for rule in rules),
                    evaluations=evaluations,
                )
            )
        return StandardsReviewReport(
            project_id=record.project_id,
            run_id=record.run_id,
            plan_id=record.plan_id,
            step_id=record.step_id,
            record_version=record.version,
            changeset_id=changeset.changeset_id,
            changeset_digest=changeset.changeset_digest,
            base_revision=changeset.base_revision,
            worktree_fingerprint=changeset.worktree_fingerprint,
            policy_digest=record.policy_digest,
            staging_fingerprint=record.staging_fingerprint,
            validation_digest=record.validation_digest,
            profile_id=registry.profile_id,
            profile_version=registry.version,
            registry_digest=registry.digest,
            files=tuple(files),
        )
