"""Deterministic fake agent runtime for offline testing and verification."""

from pathlib import Path

from migration_agent.domain import (
    AnalysisFinding,
    AnalysisResult,
    ContextualAnswer,
    ContextualQARequest,
    EvidenceReference,
    EvidenceStatus,
    FindingCategory,
    FindingSeverity,
    InventoryInterpretation,
    InventoryInterpretationRequest,
    MigrationAnalysisOutput,
    MigrationAnalystRequest,
    MigrationStep,
    PlanCriticRequest,
    PlanCritique,
    PlanCritiquePoint,
    ProjectInventory,
    RepairDiagnosis,
    RepairDiagnosticianRequest,
    StepRisk,
)
from migration_agent.ports import (
    AgentRuntimePort,
    AnalysisRequest,
    FileReaderPort,
    PlanningRequest,
    SpecialistRuntimePort,
)


class FakeAgentRuntime(AgentRuntimePort, SpecialistRuntimePort):
    """Deterministic, offline runtime for findings, plans, and specialist insights."""

    def __init__(
        self,
        *,
        canned_result: AnalysisResult | None = None,
        canned_findings: tuple[AnalysisFinding, ...] | None = None,
        canned_steps: list[MigrationStep] | None = None,
        canned_interpretation: InventoryInterpretation | None = None,
        canned_specialist_analysis: MigrationAnalysisOutput | None = None,
        canned_critique: PlanCritique | None = None,
        canned_diagnosis: RepairDiagnosis | None = None,
        canned_answer: ContextualAnswer | None = None,
        summary: str | None = None,
    ) -> None:
        self.canned_result = canned_result
        self.canned_findings = canned_findings
        self.canned_steps = canned_steps
        self.canned_interpretation = canned_interpretation
        self.canned_specialist_analysis = canned_specialist_analysis
        self.canned_critique = canned_critique
        self.canned_diagnosis = canned_diagnosis
        self.canned_answer = canned_answer
        self.summary = summary or "Deterministic migration analysis completed successfully."
        self.recorded_requests: list[AnalysisRequest] = []
        self.recorded_planning_requests: list[PlanningRequest] = []
        self.recorded_interpretation_requests: list[InventoryInterpretationRequest] = []
        self.recorded_analyst_requests: list[MigrationAnalystRequest] = []
        self.recorded_critique_requests: list[PlanCriticRequest] = []
        self.recorded_diagnosis_requests: list[RepairDiagnosticianRequest] = []
        self.recorded_qa_requests: list[ContextualQARequest] = []

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

    def plan(
        self,
        request: PlanningRequest,
    ) -> list[MigrationStep]:
        """Return canned or synthesized migration steps based on findings."""
        self.recorded_planning_requests.append(request)

        if self.canned_steps is not None:
            return self.canned_steps

        steps: list[MigrationStep] = []
        dep_step_id = "step-001"

        # Check for dependency findings
        dep_findings = [
            f for f in request.analysis.findings if f.category == FindingCategory.DEPENDENCY
        ]
        if dep_findings:
            first_dep = dep_findings[0]
            steps.append(
                MigrationStep(
                    step_id=dep_step_id,
                    title="Initialize modern package dependencies",
                    description=(
                        "Update package.json to include target framework dependencies "
                        "and remove obsolete packages."
                    ),
                    dependencies=[],
                    scope="dependency",
                    risk=StepRisk.LOW,
                    confidence=0.95,
                    evidence=list(first_dep.evidence_references),
                    expected_files=["package.json"],
                    validation_strategy=["npm install --dry-run"],
                    rollback_note="Revert package.json changes.",
                    acceptance_criteria=["Package manifest defines target runtime dependencies."],
                    unresolved_questions=[],
                )
            )

        # Check for component findings
        comp_findings = [
            f for f in request.analysis.findings if f.category == FindingCategory.COMPONENT
        ]
        for idx, comp_finding in enumerate(comp_findings, start=2):
            step_id = f"step-{idx:03d}"
            comp_name = comp_finding.id.replace("finding-component-", "")
            prereqs = [dep_step_id] if steps else []
            steps.append(
                MigrationStep(
                    step_id=step_id,
                    title=f"Migrate {comp_name} to Angular Standalone component",
                    description=(
                        f"Transform {comp_name} component class and Handlebars template "
                        "into a modern Angular standalone component with OnPush change detection."
                    ),
                    dependencies=prereqs,
                    scope="component",
                    risk=StepRisk.MEDIUM,
                    confidence=0.90,
                    evidence=list(comp_finding.evidence_references),
                    expected_files=[
                        f"src/app/components/{comp_name}/{comp_name}.component.ts",
                        f"src/app/components/{comp_name}/{comp_name}.component.spec.ts",
                    ],
                    validation_strategy=["ng test --no-watch", "ng build"],
                    rollback_note=f"Remove generated files in src/app/components/{comp_name}/.",
                    acceptance_criteria=[
                        f"{comp_name} component compiles cleanly and passes unit tests."
                    ],
                    unresolved_questions=list(comp_finding.questions),
                )
            )

        if not steps and request.inventory.files:
            steps.append(
                MigrationStep(
                    step_id="step-001",
                    title="Baseline workspace setup",
                    description="Verify source files and staging readiness.",
                    dependencies=[],
                    scope="workspace",
                    risk=StepRisk.LOW,
                    confidence=1.0,
                    evidence=[
                        EvidenceReference(
                            path=request.inventory.files[0].path,
                            description="Baseline repository evidence",
                            status=EvidenceStatus.VALID,
                        )
                    ],
                    expected_files=[request.inventory.files[0].path],
                    validation_strategy=["test -f package.json"],
                    rollback_note="No changes to revert.",
                    acceptance_criteria=["Repository baseline verified."],
                    unresolved_questions=[],
                )
            )

        return steps

    def _synthesize_findings(
        self,
        inventory: ProjectInventory,
        file_reader: FileReaderPort,
    ) -> tuple[AnalysisFinding, ...]:
        findings: list[AnalysisFinding] = []

        component_files = [
            f.path
            for f in inventory.files
            if "component" in f.path.lower()
            and f.path.endswith((".js", ".ts"))
            and not f.path.startswith("tests/")
            and not f.path.endswith(("-test.js", "-test.ts"))
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

    def interpret_inventory(
        self,
        request: InventoryInterpretationRequest,
    ) -> InventoryInterpretation:
        """Synthesize high-level domain insights and framework notes from repository inventory."""
        self.recorded_interpretation_requests.append(request)

        if self.canned_interpretation is not None:
            return self.canned_interpretation

        framework_notes = {
            f.framework_id: f"Detected with confidence {f.confidence:.2f}"
            for f in request.inventory.frameworks
        }
        repo_name = request.inventory.repository.name
        summary = (
            f"Repository '{repo_name}' contains {len(request.inventory.files)} eligible files "
            f"and {len(request.inventory.dependencies)} declared dependencies across "
            f"{len(request.inventory.frameworks)} frameworks."
        )
        risks = (
            "Legacy architectural patterns require conversion to modern standalone components",
            "Dependency versions may require updating during framework migration",
        )
        strategy = "Bottom-up component extraction into standalone Angular components"
        return InventoryInterpretation(
            architectural_summary=summary,
            framework_notes=framework_notes,
            key_risks=risks,
            recommended_migration_strategy=strategy,
        )

    def analyze_migration(
        self,
        request: MigrationAnalystRequest,
        file_reader: FileReaderPort,
    ) -> MigrationAnalysisOutput:
        """Perform deep code-level migration analysis against eligible repository files."""
        self.recorded_analyst_requests.append(request)

        if self.canned_specialist_analysis is not None:
            return self.canned_specialist_analysis

        analysis_req = AnalysisRequest(
            inventory=request.inventory,
            provider="fake",
            model="fake-analyst",
            max_turns=request.max_turns,
            dry_run=True,
        )
        analysis_res = self.analyze(analysis_req, file_reader)
        return MigrationAnalysisOutput(
            summary=analysis_res.summary,
            findings=analysis_res.findings,
            assumptions=analysis_res.assumptions,
            unsupported_constructs=analysis_res.unsupported_constructs,
            questions=analysis_res.questions,
        )

    def criticize_plan(
        self,
        request: PlanCriticRequest,
    ) -> PlanCritique:
        """Audit candidate migration plan for risk, missing dependencies, and quality issues."""
        self.recorded_critique_requests.append(request)

        if self.canned_critique is not None:
            return self.canned_critique

        critique_points: list[PlanCritiquePoint] = []
        flagged_step_ids: list[str] = []
        step_ids = {s.step_id for s in request.plan.steps}

        for step in request.plan.steps:
            # Check for unknown dependencies
            for dep in step.dependencies:
                if dep not in step_ids:
                    critique_points.append(
                        PlanCritiquePoint(
                            step_id=step.step_id,
                            severity=FindingSeverity.HIGH,
                            category="DEPENDENCY",
                            critique=(
                                f"Step '{step.step_id}' references non-existent "
                                f"prerequisite '{dep}'."
                            ),
                            recommendation=f"Remove or correct dependency '{dep}'.",
                        )
                    )
                    flagged_step_ids.append(step.step_id)

            # Check for oversized step file scopes
            if len(step.expected_files) > 10:
                critique_points.append(
                    PlanCritiquePoint(
                        step_id=step.step_id,
                        severity=FindingSeverity.MEDIUM,
                        category="SCOPE",
                        critique=(
                            f"Step '{step.step_id}' targets {len(step.expected_files)} files, "
                            "exceeding recommended granularity."
                        ),
                        recommendation="Partition step into smaller single-component units.",
                    )
                )
                flagged_step_ids.append(step.step_id)

        has_high_severity = any(
            p.severity in (FindingSeverity.HIGH, FindingSeverity.CRITICAL) for p in critique_points
        )
        approval_recommended = not has_high_severity
        score = 0.60 if has_high_severity else (0.85 if critique_points else 0.95)

        if not critique_points:
            critique_points.append(
                PlanCritiquePoint(
                    step_id=None,
                    severity=FindingSeverity.INFO,
                    category="GENERAL",
                    critique="Migration plan DAG and file scopes are well-formed and actionable.",
                    recommendation="Proceed with user approval signing.",
                )
            )

        summary = (
            f"Plan critic evaluated {len(request.plan.steps)} steps: "
            f"{'approval recommended' if approval_recommended else 'revisions required'} "
            f"with score {score:.2f}."
        )

        return PlanCritique(
            overall_score=score,
            approval_recommended=approval_recommended,
            critique_points=tuple(critique_points),
            flagged_step_ids=tuple(flagged_step_ids),
            summary=summary,
        )

    def diagnose_repair(
        self,
        request: RepairDiagnosticianRequest,
    ) -> RepairDiagnosis:
        """Diagnose validation command failure and propose targeted, in-scope repair guidance."""
        self.recorded_diagnosis_requests.append(request)

        if self.canned_diagnosis is not None:
            return self.canned_diagnosis

        target_file = request.allowed_scope[0] if request.allowed_scope else None
        diag = (
            request.failing_result.diagnostics[0]
            if request.failing_result.diagnostics
            else (
                request.failing_result.sanitized_output[:120]
                if request.failing_result.sanitized_output
                else "Command failure"
            )
        )

        fix_summary = (
            f"Adjust implementation in '{target_file}' to resolve assertion failure."
            if target_file
            else "No target file available in scope."
        )
        return RepairDiagnosis(
            root_cause_category="VALIDATION_ASSERTION_FAILURE",
            actionable=bool(target_file),
            confidence=0.90 if target_file else 0.30,
            suggested_file=target_file,
            diagnostic_details=f"Command '{request.failing_result.command}' failed: {diag}",
            suggested_fix_summary=fix_summary,
        )

    def ask(
        self,
        request: ContextualQARequest,
    ) -> ContextualAnswer:
        """Answer a contextual user query using bounded context."""
        self.recorded_qa_requests.append(request)

        if self.canned_answer is not None:
            return self.canned_answer

        envelope = request.envelope
        citations: list[EvidenceReference] = list(envelope.evidence_references)
        if not citations and envelope.selected_artifact:
            citations.append(
                EvidenceReference(
                    path=envelope.selected_artifact,
                    description="Referenced artifact context",
                )
            )

        answer_text = (
            f"Based on project context at '{envelope.project_root}', "
            f"in response to '{envelope.query}': "
            f"The architecture maintains decoupled boundaries and deterministic evidence."
        )

        return ContextualAnswer(
            query=envelope.query,
            answer=answer_text,
            confidence=1.0,
            citations=tuple(citations),
            referenced_decisions=envelope.relevant_decisions,
            referenced_learnings=envelope.relevant_learnings,
            assumptions=("Assumes clean working tree and validated inventory.",),
            follow_up_suggestions=(
                "Run 'migration-agent inventory' to inspect recent file changes.",
            ),
        )
