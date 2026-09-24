from pathlib import Path

import pytest

from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.application import AnalysisService, SnapshotFileReader
from migration_agent.domain import (
    AnalysisFinding,
    AnalysisResult,
    EvidenceReference,
    EvidenceStatus,
    ExclusionSummary,
    FileCategory,
    FindingCategory,
    FindingSeverity,
    InspectedTextFile,
    RepositoryDescriptor,
    RepositorySnapshot,
)
from migration_agent.ports import FrameworkAdapterRegistry


def test_snapshot_file_reader() -> None:
    snapshot = RepositorySnapshot(
        repository=RepositoryDescriptor(name="test", root=Path("C:/test")),
        files=(
            InspectedTextFile(
                path="app/test.js",
                category=FileCategory.SOURCE,
                size_bytes=14,
                sha256="e" * 64,
                content="console.log(1)",
            ),
        ),
        exclusions=ExclusionSummary(),
    )
    reader = SnapshotFileReader(snapshot)

    assert reader.read_file("app/test.js") == "console.log(1)"
    assert reader.read_file("app\\test.js") == "console.log(1)"

    with pytest.raises(KeyError):
        reader.read_file("app/missing.js")


def test_analysis_service_validates_and_catches_hallucinated_evidence() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"

    canned_finding = AnalysisFinding(
        id="finding-with-hallucination",
        title="Hallucinated Finding",
        category=FindingCategory.COMPONENT,
        severity=FindingSeverity.HIGH,
        confidence=0.9,
        description="A finding that cites a real path and a hallucinated path.",
        evidence_references=(
            EvidenceReference(
                path="app/components/user-card.js",
                description="Real component file in inventory",
            ),
            EvidenceReference(
                path="non_existent/hallucinated.js",
                description="Hallucinated file not in inventory",
            ),
        ),
    )

    canned_result = AnalysisResult(
        repository=RepositoryDescriptor(name="ember-classic-mini", root=fixture_path),
        provider="gemini",
        model="gemini-2.5-pro",
        summary="Canned result with hallucination.",
        findings=(canned_finding,),
    )

    runtime = FakeAgentRuntime(canned_result=canned_result)
    service = AnalysisService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
        runtime=runtime,
    )

    _inventory, validated_result = service.analyze(
        fixture_path,
        provider="gemini",
        model="gemini-2.5-pro",
    )

    assert len(validated_result.findings) == 1
    finding = validated_result.findings[0]

    # Real file is VALID
    assert finding.evidence_references[0].status == EvidenceStatus.VALID
    assert finding.evidence_references[0].validation_note is None

    # Hallucinated file is NOT_IN_INVENTORY with validation note
    assert finding.evidence_references[1].status == EvidenceStatus.NOT_IN_INVENTORY
    assert "was not found in eligible repository inventory" in (
        finding.evidence_references[1].validation_note or ""
    )

    # Finding confidence was downgraded due to unverified evidence
    assert finding.confidence <= 0.3

    # Unsupported constructs flagged the hallucination
    assert any("non_existent/hallucinated.js" in item for item in finding.unsupported_constructs)
    assert any(
        "cites unsupported or unverified" in item
        for item in validated_result.unsupported_constructs
    )
