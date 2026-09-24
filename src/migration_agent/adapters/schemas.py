"""Structured Pydantic output schemas shared across model runtime adapters."""

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain import (
    AnalysisFinding,
    AnalysisResult,
    EvidenceReference,
    FindingCategory,
    FindingSeverity,
)
from migration_agent.ports import AnalysisRequest


class AgentEvidenceReference(BaseModel):
    """Structured evidence citation schema for agent output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(description="Repository-relative POSIX path of file containing evidence.")
    description: str = Field(description="Explanation of what this evidence demonstrates.")
    line_number: int | None = Field(default=None, description="Optional 1-indexed line number.")
    sample: str | None = Field(
        default=None,
        description="Optional brief snippet or symbol from file.",
    )


class AgentFinding(BaseModel):
    """Structured finding schema for agent output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(description="Unique stable slug identifier for this finding.")
    title: str = Field(description="Short descriptive title of the finding.")
    category: FindingCategory = Field(description="Category of the finding.")
    severity: FindingSeverity = Field(
        description="Severity assessment: info, low, medium, high, critical.",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0.")
    description: str = Field(description="Detailed analysis of the issue or pattern.")
    evidence_references: tuple[AgentEvidenceReference, ...] = Field(
        default=(),
        description="Evidence files supporting this finding.",
    )
    unsupported_constructs: tuple[str, ...] = Field(
        default=(),
        description="Legacy or unsupported APIs/patterns found.",
    )
    assumptions: tuple[str, ...] = Field(
        default=(),
        description="Assumptions made in reaching this conclusion.",
    )
    questions: tuple[str, ...] = Field(
        default=(),
        description="Open questions for developers or architects.",
    )


class AgentAnalysisOutput(BaseModel):
    """Top-level structured output contract expected from analysis agents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: str = Field(description="High-level migration analysis summary.")
    findings: tuple[AgentFinding, ...] = Field(description="List of migration findings.")
    unsupported_constructs: tuple[str, ...] = Field(
        default=(),
        description="Global unsupported constructs across the repository.",
    )
    assumptions: tuple[str, ...] = Field(
        default=(),
        description="Global assumptions made during analysis.",
    )
    questions: tuple[str, ...] = Field(
        default=(),
        description="Global unresolved questions that require developer decision.",
    )


def map_agent_output_to_domain(
    output: AgentAnalysisOutput,
    request: AnalysisRequest,
) -> AnalysisResult:
    """Translate provider-agnostic agent structured output to domain AnalysisResult."""
    findings = tuple(
        AnalysisFinding(
            id=finding.id,
            title=finding.title,
            category=finding.category,
            severity=finding.severity,
            confidence=finding.confidence,
            description=finding.description,
            evidence_references=tuple(
                EvidenceReference(
                    path=ref.path,
                    description=ref.description,
                    line_number=ref.line_number,
                    sample=ref.sample,
                )
                for ref in finding.evidence_references
            ),
            unsupported_constructs=finding.unsupported_constructs,
            assumptions=finding.assumptions,
            questions=finding.questions,
        )
        for finding in output.findings
    )

    return AnalysisResult(
        repository=request.inventory.repository,
        provider=request.provider,
        model=request.model,
        is_dry_run=request.dry_run,
        summary=output.summary,
        findings=findings,
        unsupported_constructs=output.unsupported_constructs,
        assumptions=output.assumptions,
        questions=output.questions,
    )
