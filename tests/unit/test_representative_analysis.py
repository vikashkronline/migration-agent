import json
from pathlib import Path

from migration_agent.adapters.fake_runtime import FakeAgentRuntime
from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.frameworks import AngularAdapter, EmberClassicAdapter
from migration_agent.adapters.reporting import AnalysisReportWriter
from migration_agent.application import AnalysisService
from migration_agent.domain import EvidenceStatus, FindingCategory, FindingSeverity
from migration_agent.ports import FrameworkAdapterRegistry


def test_representative_ember_classic_analysis(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    output_dir = tmp_path / "analysis_output"

    service = AnalysisService(
        filesystem=SafeFilesystemInspector(),
        frameworks=FrameworkAdapterRegistry((EmberClassicAdapter(), AngularAdapter())),
        runtime=FakeAgentRuntime(),
    )

    inventory, analysis = service.analyze(
        fixture_path,
        provider="gemini",
        model="gemini-2.5-pro",
    )

    # 1. Assert inventory source of truth preserved
    assert inventory.repository.name == "ember-classic-mini"
    assert len(inventory.frameworks) == 1
    assert inventory.frameworks[0].framework_id == "ember-classic"

    # 2. Assert representative findings produced
    assert len(analysis.findings) >= 2
    comp_finding = next(
        (f for f in analysis.findings if f.category == FindingCategory.COMPONENT),
        None,
    )
    assert comp_finding is not None
    assert comp_finding.id == "finding-component-user-card"
    assert comp_finding.severity == FindingSeverity.HIGH
    assert comp_finding.confidence >= 0.9
    assert len(comp_finding.evidence_references) >= 2

    # Evidence paths are valid POSIX paths in inventory
    paths = [ref.path for ref in comp_finding.evidence_references]
    assert "app/components/user-card.js" in paths
    assert "app/templates/components/user-card.hbs" in paths
    for ref in comp_finding.evidence_references:
        assert ref.status == EvidenceStatus.VALID

    # Unsupported constructs and questions cited
    assert "Component.extend" in comp_finding.unsupported_constructs
    assert len(comp_finding.assumptions) > 0
    assert len(comp_finding.questions) > 0

    # 3. Report generation
    writer = AnalysisReportWriter()
    json_path, md_path = writer.write(analysis, output_dir)
    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["provider"] == "gemini"
    assert data["model"] == "gemini-2.5-pro"
    assert len(data["findings"]) == len(analysis.findings)
