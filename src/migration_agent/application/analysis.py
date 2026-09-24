"""Application service for running read-only migration analysis."""

from pathlib import Path

from migration_agent.application.inventory import InventoryService
from migration_agent.domain import (
    AnalysisFinding,
    AnalysisResult,
    EvidenceReference,
    EvidenceStatus,
    ProjectInventory,
    RepositorySnapshot,
)
from migration_agent.ports import (
    AgentRuntimePort,
    AnalysisRequest,
    FilesystemInspectorPort,
    FrameworkAdapterRegistry,
    InspectionPolicy,
)


class SnapshotFileReader:
    """Read-only file reader backed by an inspected repository snapshot."""

    def __init__(self, snapshot: RepositorySnapshot) -> None:
        self._content_by_path = {file.path: file.content for file in snapshot.files}

    def read_file(self, path: str) -> str:
        """Return the inspected text content if present in the snapshot."""
        normalized = path.replace("\\", "/").strip().lstrip("/")
        if normalized not in self._content_by_path:
            raise KeyError(f"Path '{path}' is not an eligible inventory text file.")
        return self._content_by_path[normalized]


class AnalysisService:
    """Coordinates deterministic inventory and read-only agent analysis."""

    def __init__(
        self,
        *,
        filesystem: FilesystemInspectorPort,
        frameworks: FrameworkAdapterRegistry,
        runtime: AgentRuntimePort,
    ) -> None:
        self._filesystem = filesystem
        self._frameworks = frameworks
        self._runtime = runtime
        self._inventory_service = InventoryService(
            filesystem=filesystem,
            frameworks=frameworks,
        )

    def analyze(
        self,
        root: Path,
        *,
        model: str,
        provider: str = "gemini",
        policy: InspectionPolicy | None = None,
        max_turns: int = 15,
        max_tool_chars: int = 20_000,
        dry_run: bool = True,
    ) -> tuple[ProjectInventory, AnalysisResult]:
        """Perform inventory discovery and run bounded agent analysis."""
        inspection_policy = policy or InspectionPolicy()
        snapshot = self._filesystem.inspect(root, inspection_policy)
        inventory = self._inventory_service.inventory(root, policy=inspection_policy)

        file_reader = SnapshotFileReader(snapshot)
        request = AnalysisRequest(
            inventory=inventory,
            provider=provider,
            model=model,
            max_turns=max_turns,
            max_tool_chars=max_tool_chars,
            dry_run=dry_run,
        )

        raw_result = self._runtime.analyze(request, file_reader)
        validated_result = self.validate_evidence(raw_result, inventory)
        return inventory, validated_result

    @staticmethod
    def validate_evidence(
        result: AnalysisResult,
        inventory: ProjectInventory,
    ) -> AnalysisResult:
        """Verify that all evidence references correspond to eligible inventory files."""
        eligible_paths = {file.path for file in inventory.files}

        validated_findings: list[AnalysisFinding] = []
        global_unsupported = list(result.unsupported_constructs)

        for finding in result.findings:
            validated_references: list[EvidenceReference] = []
            has_hallucinated_evidence = False
            finding_unsupported = list(finding.unsupported_constructs)

            for ref in finding.evidence_references:
                normalized_path = ref.path.replace("\\", "/").strip().lstrip("/")
                if normalized_path in eligible_paths:
                    validated_references.append(
                        EvidenceReference(
                            path=normalized_path,
                            description=ref.description,
                            line_number=ref.line_number,
                            sample=ref.sample,
                            status=EvidenceStatus.VALID,
                            validation_note=None,
                        )
                    )
                else:
                    has_hallucinated_evidence = True
                    note = f"Path '{ref.path}' was not found in eligible repository inventory."
                    validated_references.append(
                        EvidenceReference(
                            path=ref.path,
                            description=ref.description,
                            line_number=ref.line_number,
                            sample=ref.sample,
                            status=EvidenceStatus.NOT_IN_INVENTORY,
                            validation_note=note,
                        )
                    )
                    finding_unsupported.append(f"Unverified evidence path: {ref.path}")

            confidence = finding.confidence
            if has_hallucinated_evidence:
                confidence = min(confidence, 0.3)
                global_unsupported.append(
                    f"Finding '{finding.id}' cites unsupported or unverified evidence paths."
                )

            validated_findings.append(
                AnalysisFinding(
                    id=finding.id,
                    title=finding.title,
                    category=finding.category,
                    severity=finding.severity,
                    confidence=confidence,
                    description=finding.description,
                    evidence_references=tuple(validated_references),
                    unsupported_constructs=tuple(dict.fromkeys(finding_unsupported)),
                    assumptions=finding.assumptions,
                    questions=finding.questions,
                )
            )

        return AnalysisResult(
            schema_version=result.schema_version,
            repository=inventory.repository,
            provider=result.provider,
            model=result.model,
            is_dry_run=result.is_dry_run,
            summary=result.summary,
            findings=tuple(validated_findings),
            unsupported_constructs=tuple(dict.fromkeys(global_unsupported)),
            assumptions=result.assumptions,
            questions=result.questions,
        )
