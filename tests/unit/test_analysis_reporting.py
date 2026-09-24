import json
from pathlib import Path

import pytest

from migration_agent.adapters.reporting import AnalysisReportWriter
from migration_agent.domain import (
    AnalysisFinding,
    AnalysisResult,
    EvidenceReference,
    EvidenceStatus,
    FindingCategory,
    FindingSeverity,
    RepositoryDescriptor,
)


def test_analysis_report_writer_creates_reports(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    output_dir = tmp_path / "output"
    source_dir.mkdir()

    repo = RepositoryDescriptor(name="test-repo", root=source_dir)
    result = AnalysisResult(
        repository=repo,
        provider="gemini",
        model="gemini-2.5-pro",
        is_dry_run=True,
        summary="Comprehensive migration analysis summary.",
        findings=(
            AnalysisFinding(
                id="finding-test-1",
                title="Test Finding Title",
                category=FindingCategory.COMPONENT,
                severity=FindingSeverity.HIGH,
                confidence=0.92,
                description="Test description of component migration issue.",
                evidence_references=(
                    EvidenceReference(
                        path="app/test.js",
                        description="Test evidence description",
                        line_number=5,
                        sample="Component.extend",
                        status=EvidenceStatus.VALID,
                    ),
                ),
                unsupported_constructs=("Legacy construct 1",),
                assumptions=("Assumption 1",),
                questions=("Question 1?",),
            ),
        ),
        unsupported_constructs=("Global unsupported 1",),
        assumptions=("Global assumption 1",),
        questions=("Global question 1?",),
    )

    writer = AnalysisReportWriter()
    json_path, md_path = writer.write(result, output_dir)

    assert json_path.exists()
    assert md_path.exists()

    # JSON report check
    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_data["schema_version"] == 1
    assert json_data["provider"] == "gemini"
    assert json_data["model"] == "gemini-2.5-pro"
    assert len(json_data["findings"]) == 1

    # Markdown report check
    md_content = md_path.read_text(encoding="utf-8")
    assert "# Migration Analysis Report" in md_content
    assert "- Provider: `gemini`" in md_content
    assert "- Model: `gemini-2.5-pro`" in md_content
    assert "Test Finding Title" in md_content
    assert "`app/test.js:5`" in md_content
    assert "Legacy construct 1" in md_content
    assert "Global unsupported 1" in md_content


def test_analysis_report_writer_rejects_overlapping_directory(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    repo = RepositoryDescriptor(name="test-repo", root=source_dir)
    result = AnalysisResult(
        repository=repo,
        provider="gemini",
        model="gemini-2.5-pro",
        summary="summary",
    )
    writer = AnalysisReportWriter()

    # Subdirectory of source
    with pytest.raises(ValueError, match="output directory must not overlap"):
        writer.write(result, source_dir / "reports")

    # Parent of source
    with pytest.raises(ValueError, match="output directory must not overlap"):
        writer.write(result, tmp_path)
