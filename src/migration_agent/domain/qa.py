"""Domain models for contextual interaction, Q&A, and ContextEnvelope (Master Plan Section 6)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain.analysis import EvidenceReference


class ContextEnvelope(BaseModel):
    """Context-bounded container for interactions preventing context bloat and hallucination."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_root: str = Field(min_length=1)
    query: str = Field(min_length=1)
    selected_entity: str | None = None
    selected_artifact: str | None = None
    current_run_id: str | None = None
    relevant_decisions: tuple[str, ...] = Field(default_factory=tuple)
    relevant_learnings: tuple[str, ...] = Field(default_factory=tuple)
    evidence_references: tuple[EvidenceReference, ...] = Field(default_factory=tuple)
    active_policy_digest: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextualAnswer(BaseModel):
    """Evidence-backed structured response to a contextual user inquiry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    citations: tuple[EvidenceReference, ...] = Field(default_factory=tuple)
    referenced_decisions: tuple[str, ...] = Field(default_factory=tuple)
    referenced_learnings: tuple[str, ...] = Field(default_factory=tuple)
    assumptions: tuple[str, ...] = Field(default_factory=tuple)
    follow_up_suggestions: tuple[str, ...] = Field(default_factory=tuple)


class ContextualQARequest(BaseModel):
    """Application request parameters for contextual Q&A."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope: ContextEnvelope
    provider: str = "gemini"
    model: str = Field(min_length=1)
    max_turns: int = Field(default=5, ge=1)
    dry_run: bool = True
