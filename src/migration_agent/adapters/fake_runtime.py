"""Deterministic fake agent runtime for offline testing and verification."""

from pathlib import Path

from migration_agent.domain import (
    AnalysisFinding,
    AnalysisResult,
    EvidenceReference,
    EvidenceStatus,
    FindingCategory,
    FindingSeverity,
    ProjectInventory,
)
from migration_agent.ports import AgentRuntimePort, AnalysisRequest, FileReaderPort


class FakeAgentRuntime(AgentRuntimePort):
    """Deterministic, offline runtime producing verifiable migration findings."""

    def __init__(
        self,
        *,
        canned_result: AnalysisResult | None = None,
        canned_findings: tuple[AnalysisFinding, ...] | None = None,
        summary: str | None = None,
    ) -> None:
        self.canned_result = canned_result
        self.canned_findings = canned_findings
        self.summary = summary or "Deterministic migration analysis completed successfully."
        self.recorded_requests: list[AnalysisRequest] = []

    def analyze(
        self,
        request: AnalysisRequest,
        file_reader: FileReaderPort,
    ) -> AnalysisResult:
        """Return canned or synthesized findings based on inventory."""
        self.recorded_requests.append(request)

        if self.canned_result is not None:
            return self.canned_result

        if self.canned_findings is not None:
            return AnalysisResult(
                repository=request.inventory.repository,
                provider=request.provider,
                model=request.model,
                is_dry_run=request.dry_run,
                summary=self.summary,
                findings=self.canned_findings,
                unsupported_constructs=("Legacy framework patterns require manual review",),
                assumptions=("Target framework baseline is modern standalone components",),
                questions=("Are there external runtime dependencies not listed in package.json?",),
            )

        findings = self._synthesize_findings(request.inventory, file_reader)
        return AnalysisResult(
            repository=request.inventory.repository,
            provider=request.provider,
            model=request.model,
            is_dry_run=request.dry_run,
            summary=self.summary,
            findings=findings,
            unsupported_constructs=(
                "Implicit component injection patterns",
                "Classic Ember Object prototype extensions",
            ),
            assumptions=(
                "Target architecture is Angular Standalone components with OnPush change detection",
            ),
            questions=(
                "Should Ember data adapters be converted to Angular HTTP services or NgRx?",
            ),
        )

    def _synthesize_findings(
        self,
        inventory: ProjectInventory,
        file_reader: FileReaderPort,
    ) -> tuple[AnalysisFinding, ...]:
        findings: list[AnalysisFinding] = []

        # Detect component files in inventory
        component_files = [
            f.path
            for f in inventory.files
            if "component" in f.path.lower() and f.path.endswith((".js", ".ts"))
        ]
        template_files = [f.path for f in inventory.files if f.path.endswith((".hbs", ".html"))]

        for comp_path in component_files:
            references = [
                EvidenceReference(
                    path=comp_path,
                    description="Component definition file with classic lifecycle",
                    line_number=1,
                    sample="Component.extend({",
                    status=EvidenceStatus.VALID,
                )
            ]

            matching_template = next(
                (t for t in template_files if Path(t).stem == Path(comp_path).stem),
                None,
            )
            if matching_template:
                references.append(
                    EvidenceReference(
                        path=matching_template,
                        description="Associated component template",
                        line_number=1,
                        sample="{{yield}}",
                        status=EvidenceStatus.VALID,
                    )
                )

            comp_name = Path(comp_path).stem
            findings.append(
                AnalysisFinding(
                    id=f"finding-component-{comp_name}",
                    title=f"Legacy Component Pattern: {comp_name}",
                    category=FindingCategory.COMPONENT,
                    severity=FindingSeverity.HIGH,
                    confidence=0.95,
                    description=(
                        f"Component '{comp_name}' uses classic subclassing and lifecycle hooks "
                        "that must be migrated to modern standalone class declarations."
                    ),
                    evidence_references=tuple(references),
                    unsupported_constructs=("Component.extend", "Two-way data binding helpers"),
                    assumptions=("Component state can be modeled cleanly using Angular Signals",),
                    questions=(f"Does '{comp_name}' rely on inherited controller properties?",),
                )
            )

        # Detect dependency issues or legacy dependencies
        legacy_deps = [d for d in inventory.dependencies if "ember" in d.name.lower()]
        if legacy_deps:
            manifest_path = legacy_deps[0].manifest_path
            findings.append(
                AnalysisFinding(
                    id="finding-framework-dependencies",
                    title="Legacy Framework Dependencies in Manifest",
                    category=FindingCategory.DEPENDENCY,
                    severity=FindingSeverity.MEDIUM,
                    confidence=0.90,
                    description=(
                        f"Repository declares {len(legacy_deps)} framework-specific packages "
                        "which must be replaced or removed in target framework."
                    ),
                    evidence_references=(
                        EvidenceReference(
                            path=manifest_path,
                            description="Package manifest declaring legacy dependencies",
                            line_number=1,
                            sample=legacy_deps[0].name,
                            status=EvidenceStatus.VALID,
                        ),
                    ),
                    unsupported_constructs=("Ember addon ecosystem packages",),
                    assumptions=("Modern npm package equivalents exist",),
                    questions=("Are any private company packages bundled here?",),
                )
            )

        if not findings and inventory.files:
            findings.append(
                AnalysisFinding(
                    id="finding-repository-baseline",
                    title="General Source Structure Assessed",
                    category=FindingCategory.ARCHITECTURE,
                    severity=FindingSeverity.INFO,
                    confidence=0.85,
                    description="Repository eligible source files inventoried.",
                    evidence_references=(
                        EvidenceReference(
                            path=inventory.files[0].path,
                            description="Representative source file",
                            line_number=1,
                            status=EvidenceStatus.VALID,
                        ),
                    ),
                    unsupported_constructs=(),
                    assumptions=(),
                    questions=(),
                )
            )

        return tuple(findings)
