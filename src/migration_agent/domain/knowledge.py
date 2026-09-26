"""Domain models for curated project knowledge, challenges, solutions, and ADRs (ADR-3, ADR-7)."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.analysis import EvidenceReference


class EpistemicStatus(StrEnum):
    """Epistemic classification of captured architectural and migration knowledge (ADR-7)."""

    OBSERVED = "OBSERVED"  # Directly observed in code, manifests, or compiler/test output
    INFERRED = "INFERRED"  # Inferred by agent reasoning or heuristic deduction
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"  # Formally verified and approved by a human engineer


class ChallengeStatus(StrEnum):
    """Operational status of a recorded migration hurdle or diagnostic challenge."""

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ABANDONED = "ABANDONED"


class SolutionStatus(StrEnum):
    """Status of a candidate solution in the knowledge lifecycle."""

    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class DecisionStatus(StrEnum):
    """Lifecycle status of an Architectural Decision Record (ADR)."""

    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class ChallengeRecord(BaseModel):
    """Diagnostic hurdle, compiler error, or architectural challenge in migration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    challenge_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(default="GENERAL")
    description: str = Field(min_length=1)
    diagnostic_citations: tuple[str, ...] = Field(default_factory=tuple)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: ChallengeStatus = ChallengeStatus.OPEN
    epistemic_status: EpistemicStatus = EpistemicStatus.OBSERVED
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateSolution(BaseModel):
    """Proposed or staged candidate solution for a recorded challenge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    solution_id: str = Field(min_length=1)
    challenge_id: str = Field(min_length=1)
    proposed_approach: str = Field(min_length=1)
    changeset_ref: str | None = None
    verified_by_run_id: str | None = None
    status: SolutionStatus = SolutionStatus.PROPOSED
    proposed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    epistemic_status: EpistemicStatus = EpistemicStatus.INFERRED
    metadata: dict[str, Any] = Field(default_factory=dict)


class CuratedLearning(BaseModel):
    """Human-approved durable project learning promoted from validated solutions (Invariant 16)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    learning_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_challenge_id: str = Field(min_length=1)
    source_solution_id: str = Field(min_length=1)
    findings: str = Field(min_length=1)
    recommended_pattern: str = Field(min_length=1)
    anti_patterns: tuple[str, ...] = Field(default_factory=tuple)
    evidence_references: tuple[EvidenceReference, ...] = Field(default_factory=tuple)
    tags: tuple[str, ...] = Field(default_factory=tuple)
    epistemic_status: EpistemicStatus = EpistemicStatus.HUMAN_CONFIRMED
    approved_by: str = Field(min_length=1)
    approved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArchitecturalDecisionRecord(BaseModel):
    """Recorded Architectural Decision Record (ADR) governing project evolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(min_length=1)  # e.g. "ADR-001"
    title: str = Field(min_length=1)
    status: DecisionStatus = DecisionStatus.ACCEPTED
    context: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    consequences: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    epistemic_status: EpistemicStatus = EpistemicStatus.HUMAN_CONFIRMED
    metadata: dict[str, Any] = Field(default_factory=dict)
