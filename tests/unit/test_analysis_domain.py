import pytest
from pydantic import ValidationError

from migration_agent.domain import (
    AnalysisFinding,
    AnalysisResult,
    EvidenceReference,
    EvidenceStatus,
    FindingCategory,
    FindingSeverity,
    RepositoryDescriptor,
)


def test_evidence_reference_validation() -> None:
    ref = EvidenceReference(
        path="app/components/user-card.js",
        description="Component definition",
        line_number=10,
        sample="Component.extend({",
    )
    assert ref.path == "app/components/user-card.js"
    assert ref.status == EvidenceStatus.VALID
    assert ref.line_number == 10

    # Line number cannot be less than 1
    with pytest.raises(ValidationError):
        EvidenceReference(path="file.js", description="desc", line_number=0)

    # Immutability
    with pytest.raises(ValidationError):
        ref.path = "other.js"  # type: ignore[misc]


def test_analysis_finding_validation() -> None:
    finding = AnalysisFinding(
        id="finding-1",
        title="Legacy Component",
        category=FindingCategory.COMPONENT,
        severity=FindingSeverity.HIGH,
        confidence=0.9,
        description="Classic Ember component definition",
        evidence_references=(
            EvidenceReference(
                path="app/components/user-card.js",
                description="definition",
            ),
        ),
    )
    assert finding.category == "component"
    assert finding.severity == "high"
    assert finding.confidence == 0.9

    # Confidence must be between 0.0 and 1.0
    with pytest.raises(ValidationError):
        AnalysisFinding(
            id="bad-finding",
            title="Title",
            category=FindingCategory.COMPONENT,
            severity=FindingSeverity.LOW,
            confidence=1.5,
            description="desc",
        )

    # Id and title must not be empty
    with pytest.raises(ValidationError):
        AnalysisFinding(
            id="",
            title="",
            category=FindingCategory.COMPONENT,
            severity=FindingSeverity.LOW,
            confidence=0.5,
            description="desc",
        )


def test_analysis_result_schema_and_serialization(tmp_path) -> None:
    repo = RepositoryDescriptor(name="mini-repo", root=tmp_path)
    result = AnalysisResult(
        repository=repo,
        provider="gemini",
        model="gemini-2.5-pro",
        is_dry_run=True,
        summary="Analysis complete.",
        findings=(
            AnalysisFinding(
                id="f1",
                title="Finding 1",
                category=FindingCategory.ARCHITECTURE,
                severity=FindingSeverity.INFO,
                confidence=0.8,
                description="desc",
            ),
        ),
        unsupported_constructs=("Legacy construct",),
        assumptions=("Modern framework assumed",),
        questions=("Question 1?",),
    )

    data = result.model_dump(mode="json")
    assert data["schema_version"] == 1
    assert data["provider"] == "gemini"
    assert data["model"] == "gemini-2.5-pro"
    assert len(data["findings"]) == 1
    assert data["findings"][0]["id"] == "f1"

    # Forbid extra fields
    with pytest.raises(ValidationError):
        AnalysisResult(
            repository=repo,
            provider="gemini",
            model="gemini-2.5-pro",
            summary="test",
            extra_field="disallowed",  # type: ignore[call-arg]
        )
