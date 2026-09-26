"""Application service for managing curated project knowledge, challenges, solutions, and ADRs."""

import uuid
from datetime import UTC, datetime

from migration_agent.domain.analysis import EvidenceReference
from migration_agent.domain.knowledge import (
    ArchitecturalDecisionRecord,
    CandidateSolution,
    ChallengeRecord,
    ChallengeStatus,
    CuratedLearning,
    DecisionStatus,
    EpistemicStatus,
    SolutionStatus,
)
from migration_agent.ports.knowledge import KnowledgePort


class KnowledgeService:
    """Manages the curated project knowledge lifecycle (ADR-3, Invariant 16)."""

    def __init__(self, knowledge_port: KnowledgePort) -> None:
        self._port = knowledge_port

    # --- Challenges ---

    def record_challenge(
        self,
        project_root: str,
        title: str,
        description: str,
        category: str = "GENERAL",
        diagnostic_citations: tuple[str, ...] = (),
        challenge_id: str | None = None,
    ) -> ChallengeRecord:
        """Record a diagnostic hurdle or challenge encountered during migration."""
        cid = challenge_id or f"ch-{uuid.uuid4().hex[:8]}"
        record = ChallengeRecord(
            challenge_id=cid,
            title=title,
            category=category,
            description=description,
            diagnostic_citations=diagnostic_citations,
            observed_at=datetime.now(UTC),
            status=ChallengeStatus.OPEN,
            epistemic_status=EpistemicStatus.OBSERVED,
        )
        self._port.save_challenge(project_root, record)
        return record

    def get_challenge(self, project_root: str, challenge_id: str) -> ChallengeRecord | None:
        return self._port.get_challenge(project_root, challenge_id)

    def list_challenges(self, project_root: str) -> list[ChallengeRecord]:
        return self._port.list_challenges(project_root)

    # --- Candidate Solutions ---

    def propose_solution(
        self,
        project_root: str,
        challenge_id: str,
        proposed_approach: str,
        changeset_ref: str | None = None,
        verified_by_run_id: str | None = None,
        solution_id: str | None = None,
    ) -> CandidateSolution:
        """Record a candidate solution for a known challenge."""
        challenge = self._port.get_challenge(project_root, challenge_id)
        if challenge is None:
            raise ValueError(f"Challenge '{challenge_id}' not found.")

        sid = solution_id or f"sol-{uuid.uuid4().hex[:8]}"
        solution = CandidateSolution(
            solution_id=sid,
            challenge_id=challenge_id,
            proposed_approach=proposed_approach,
            changeset_ref=changeset_ref,
            verified_by_run_id=verified_by_run_id,
            status=SolutionStatus.PROPOSED,
            proposed_at=datetime.now(UTC),
            epistemic_status=EpistemicStatus.INFERRED,
        )
        self._port.save_solution(project_root, solution)
        return solution

    def get_solution(self, project_root: str, solution_id: str) -> CandidateSolution | None:
        return self._port.get_solution(project_root, solution_id)

    def list_solutions(self, project_root: str) -> list[CandidateSolution]:
        return self._port.list_solutions(project_root)

    # --- Curated Learnings ---

    def approve_learning(
        self,
        project_root: str,
        solution_id: str,
        approved_by: str,
        title: str,
        findings: str,
        recommended_pattern: str,
        anti_patterns: tuple[str, ...] = (),
        evidence_references: tuple[EvidenceReference, ...] = (),
        tags: tuple[str, ...] = (),
        learning_id: str | None = None,
    ) -> CuratedLearning:
        """Promote a candidate solution to a curated learning with human approval (Invariant 16)."""
        if not approved_by or not approved_by.strip():
            raise ValueError(
                "Invariant 16 violation: Human approved_by identifier is strictly required."
            )

        solution = self._port.get_solution(project_root, solution_id)
        if solution is None:
            raise ValueError(f"Solution '{solution_id}' not found.")

        challenge = self._port.get_challenge(project_root, solution.challenge_id)

        lid = learning_id or f"lrn-{uuid.uuid4().hex[:8]}"
        learning = CuratedLearning(
            learning_id=lid,
            title=title,
            source_challenge_id=solution.challenge_id,
            source_solution_id=solution_id,
            findings=findings,
            recommended_pattern=recommended_pattern,
            anti_patterns=anti_patterns,
            evidence_references=evidence_references,
            tags=tags,
            epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
            approved_by=approved_by.strip(),
            approved_at=datetime.now(UTC),
        )
        self._port.save_learning(project_root, learning)

        # Update solution status to PROMOTED
        promoted_sol = solution.model_copy(
            update={
                "status": SolutionStatus.PROMOTED,
                "epistemic_status": EpistemicStatus.HUMAN_CONFIRMED,
            }
        )
        self._port.save_solution(project_root, promoted_sol)

        # Update challenge status to RESOLVED
        if challenge is not None:
            resolved_ch = challenge.model_copy(
                update={
                    "status": ChallengeStatus.RESOLVED,
                    "epistemic_status": EpistemicStatus.HUMAN_CONFIRMED,
                }
            )
            self._port.save_challenge(project_root, resolved_ch)

        return learning

    def get_learning(self, project_root: str, learning_id: str) -> CuratedLearning | None:
        return self._port.get_learning(project_root, learning_id)

    def list_learnings(self, project_root: str) -> list[CuratedLearning]:
        return self._port.list_learnings(project_root)

    # --- Architectural Decisions (ADRs) ---

    def record_decision(
        self,
        project_root: str,
        decision_id: str,
        title: str,
        context: str,
        decision: str,
        consequences: str,
        decided_by: str,
        status: DecisionStatus = DecisionStatus.ACCEPTED,
    ) -> ArchitecturalDecisionRecord:
        """Record an Architectural Decision Record (ADR) governing project evolution."""
        if not decided_by or not decided_by.strip():
            raise ValueError("decided_by identifier is required for ADR records.")

        clean_id = decision_id.upper().strip()
        adr = ArchitecturalDecisionRecord(
            decision_id=clean_id,
            title=title,
            status=status,
            context=context,
            decision=decision,
            consequences=consequences,
            decided_by=decided_by.strip(),
            decided_at=datetime.now(UTC),
            epistemic_status=EpistemicStatus.HUMAN_CONFIRMED,
        )
        self._port.save_decision(project_root, adr)
        return adr

    def get_decision(
        self, project_root: str, decision_id: str
    ) -> ArchitecturalDecisionRecord | None:
        return self._port.get_decision(project_root, decision_id.upper().strip())

    def list_decisions(self, project_root: str) -> list[ArchitecturalDecisionRecord]:
        return self._port.list_decisions(project_root)
