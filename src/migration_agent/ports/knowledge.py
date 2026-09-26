"""Port definition for Git-native project knowledge, challenges, solutions, and ADRs."""

from typing import Protocol

from migration_agent.domain.knowledge import (
    ArchitecturalDecisionRecord,
    CandidateSolution,
    ChallengeRecord,
    CuratedLearning,
)


class KnowledgePort(Protocol):
    """Boundary for managing Git-versioned project knowledge in .agent/ (ADR-3)."""

    def save_challenge(self, project_root: str, challenge: ChallengeRecord) -> str:
        """Save a challenge record to .agent/challenges/<challenge_id>.md.

        Returns:
            The absolute path of the written file.
        """

    def get_challenge(self, project_root: str, challenge_id: str) -> ChallengeRecord | None:
        """Load a challenge record by ID from .agent/challenges/."""

    def list_challenges(self, project_root: str) -> list[ChallengeRecord]:
        """List all challenge records ordered deterministically by ID."""

    def save_solution(self, project_root: str, solution: CandidateSolution) -> str:
        """Save a candidate solution to .agent/solutions/<solution_id>.md.

        Returns:
            The absolute path of the written file.
        """

    def get_solution(self, project_root: str, solution_id: str) -> CandidateSolution | None:
        """Load a candidate solution by ID from .agent/solutions/."""

    def list_solutions(self, project_root: str) -> list[CandidateSolution]:
        """List all candidate solutions ordered deterministically by ID."""

    def save_learning(self, project_root: str, learning: CuratedLearning) -> str:
        """Save a human-approved curated learning to .agent/learnings/<learning_id>.md.

        Returns:
            The absolute path of the written file.
        """

    def get_learning(self, project_root: str, learning_id: str) -> CuratedLearning | None:
        """Load a curated learning by ID from .agent/learnings/."""

    def list_learnings(self, project_root: str) -> list[CuratedLearning]:
        """List all curated learnings ordered deterministically by ID."""

    def save_decision(self, project_root: str, decision: ArchitecturalDecisionRecord) -> str:
        """Save an Architectural Decision Record to .agent/decisions/<decision_id>.md.

        Returns:
            The absolute path of the written file.
        """

    def get_decision(
        self, project_root: str, decision_id: str
    ) -> ArchitecturalDecisionRecord | None:
        """Load an ADR by ID from .agent/decisions/."""

    def list_decisions(self, project_root: str) -> list[ArchitecturalDecisionRecord]:
        """List all ADRs ordered deterministically by ID."""
