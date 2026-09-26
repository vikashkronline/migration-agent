"""Structured Pydantic output schemas shared across model runtime adapters."""

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.domain import (
    AnalysisFinding,
    AnalysisResult,
    ContextualAnswer,
    EvidenceReference,
    FindingCategory,
    FindingSeverity,
    InventoryInterpretation,
    MigrationStep,
    PlanCritique,
    PlanCritiquePoint,
    RepairDiagnosis,
    StepRisk,
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


class AgentPlanStep(BaseModel):
    """Structured step schema from planner agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(description="Unique stable step identifier (e.g. 'step-001').")
    title: str = Field(description="Short descriptive title of this migration step.")
    description: str = Field(description="Detailed instructions and rationale for this step.")
    dependencies: tuple[str, ...] = Field(
        default=(),
        description="IDs of prerequisite steps that must complete before this step.",
    )
    scope: str = Field(
        default="component",
        description="Scope category (e.g. 'component', 'dependency', 'configuration').",
    )
    risk: StepRisk = Field(
        default=StepRisk.MEDIUM,
        description="Assessed risk level: LOW, MEDIUM, HIGH, CRITICAL.",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    evidence: tuple[AgentEvidenceReference, ...] = Field(
        default=(),
        description="Source evidence references justifying this step.",
    )
    expected_files: tuple[str, ...] = Field(
        default=(),
        description="Normalized relative POSIX paths of files expected to be created or modified.",
    )
    validation_strategy: tuple[str, ...] = Field(
        default=(),
        description="Validation commands or checks required to verify step completion.",
    )
    rollback_note: str = Field(
        default="",
        description="Actionable notes explaining how to revert this step if validation fails.",
    )
    acceptance_criteria: tuple[str, ...] = Field(
        default=(),
        description="Concrete, verifiable acceptance criteria for step success.",
    )
    unresolved_questions: tuple[str, ...] = Field(
        default=(),
        description="Open questions for developer review prior to execution.",
    )


class AgentPlanningOutput(BaseModel):
    """Top-level structured output contract from planner agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    steps: tuple[AgentPlanStep, ...] = Field(
        default=(),
        description="Ordered sequence of migration steps.",
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


def map_agent_plan_output_to_domain(
    output: AgentPlanningOutput,
) -> list[MigrationStep]:
    """Translate provider-agnostic planner structured output to domain MigrationStep list."""
    return [
        MigrationStep(
            step_id=step.step_id,
            title=step.title,
            description=step.description,
            dependencies=list(step.dependencies),
            scope=step.scope,
            risk=step.risk,
            confidence=step.confidence,
            evidence=[
                EvidenceReference(
                    path=ref.path,
                    description=ref.description,
                    line_number=ref.line_number,
                    sample=ref.sample,
                )
                for ref in step.evidence
            ],
            expected_files=list(step.expected_files),
            validation_strategy=list(step.validation_strategy),
            rollback_note=step.rollback_note,
            acceptance_criteria=list(step.acceptance_criteria),
            unresolved_questions=list(step.unresolved_questions),
        )
        for step in output.steps
    ]


class AgentInventoryInterpretationOutput(BaseModel):
    """Structured output contract for inventory interpreter agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    architectural_summary: str = Field(description="High-level architectural assessment.")
    framework_notes: dict[str, str] = Field(
        default_factory=dict,
        description="Framework-specific assessment notes.",
    )
    key_risks: tuple[str, ...] = Field(
        default=(),
        description="Architectural or technical risks.",
    )
    recommended_migration_strategy: str = Field(
        default="",
        description="High-level recommended migration strategy.",
    )


class AgentPlanCritiquePoint(BaseModel):
    """Critique point from plan critic agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str | None = Field(default=None, description="Step ID if step-specific.")
    severity: FindingSeverity = Field(description="Severity of the critique point.")
    category: str = Field(description="Category of the critique.")
    critique: str = Field(description="Explanation of the potential issue.")
    recommendation: str = Field(default="", description="Suggested fix or mitigation.")


class AgentPlanCritiqueOutput(BaseModel):
    """Structured output contract for plan critic agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Plan quality score between 0.0 and 1.0.",
    )
    approval_recommended: bool = Field(description="Whether the plan is ready for approval.")
    critique_points: tuple[AgentPlanCritiquePoint, ...] = Field(
        default=(),
        description="List of critique points.",
    )
    flagged_step_ids: tuple[str, ...] = Field(
        default=(),
        description="IDs of steps flagged as requiring modification.",
    )
    summary: str = Field(default="", description="Summary of the plan critique.")


class AgentRepairDiagnosisOutput(BaseModel):
    """Structured output contract for repair diagnostician agent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    root_cause_category: str = Field(description="Category of the failure root cause.")
    actionable: bool = Field(description="Whether the issue can be automatically repaired.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the diagnosis.")
    suggested_file: str | None = Field(
        default=None,
        description="Specific allowed file to repair.",
    )
    diagnostic_details: str = Field(default="", description="Detailed diagnostic explanation.")
    suggested_fix_summary: str = Field(default="", description="Summary of suggested fix.")


def map_agent_interpretation_output_to_domain(
    output: AgentInventoryInterpretationOutput,
) -> InventoryInterpretation:
    """Translate agent inventory interpretation output to domain model."""
    return InventoryInterpretation(
        architectural_summary=output.architectural_summary,
        framework_notes=output.framework_notes,
        key_risks=output.key_risks,
        recommended_migration_strategy=output.recommended_migration_strategy,
    )


def map_agent_critique_output_to_domain(
    output: AgentPlanCritiqueOutput,
) -> PlanCritique:
    """Translate agent plan critique output to domain model."""
    return PlanCritique(
        overall_score=output.overall_score,
        approval_recommended=output.approval_recommended,
        critique_points=tuple(
            PlanCritiquePoint(
                step_id=p.step_id,
                severity=p.severity,
                category=p.category,
                critique=p.critique,
                recommendation=p.recommendation,
            )
            for p in output.critique_points
        ),
        flagged_step_ids=output.flagged_step_ids,
        summary=output.summary,
    )


def map_agent_diagnosis_output_to_domain(
    output: AgentRepairDiagnosisOutput,
) -> RepairDiagnosis:
    """Translate agent repair diagnosis output to domain model."""
    return RepairDiagnosis(
        root_cause_category=output.root_cause_category,
        actionable=output.actionable,
        confidence=output.confidence,
        suggested_file=output.suggested_file,
        diagnostic_details=output.diagnostic_details,
        suggested_fix_summary=output.suggested_fix_summary,
    )


class AgentQAOutput(BaseModel):
    """Structured QA output schema for agent runtime."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    answer: str = Field(description="Comprehensive evidence-based response to query.")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Confidence score.")
    citations: tuple[AgentEvidenceReference, ...] = Field(
        default=(),
        description="Citations to repository files.",
    )
    referenced_decisions: tuple[str, ...] = Field(
        default=(),
        description="IDs of referenced ADRs.",
    )
    referenced_learnings: tuple[str, ...] = Field(
        default=(),
        description="IDs of referenced learnings.",
    )
    assumptions: tuple[str, ...] = Field(
        default=(),
        description="Underlying assumptions made.",
    )
    follow_up_suggestions: tuple[str, ...] = Field(
        default=(),
        description="Suggested next actions or queries.",
    )


def map_agent_qa_output_to_domain(
    output: AgentQAOutput,
    query: str,
) -> ContextualAnswer:
    """Translate agent QA output to domain ContextualAnswer."""
    return ContextualAnswer(
        query=query,
        answer=output.answer,
        confidence=output.confidence,
        citations=tuple(
            EvidenceReference(
                path=c.path,
                description=c.description,
                line_number=c.line_number,
                sample=c.sample,
            )
            for c in output.citations
        ),
        referenced_decisions=output.referenced_decisions,
        referenced_learnings=output.referenced_learnings,
        assumptions=output.assumptions,
        follow_up_suggestions=output.follow_up_suggestions,
    )
