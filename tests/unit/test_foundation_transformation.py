"""Unit tests for FoundationTransformationAdapter and foundation execution slice."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from migration_agent.adapters.foundation_transformation import (
    FoundationTransformationAdapter,
    sanitize_project_name,
)
from migration_agent.adapters.stack_catalog import get_default_target_preset
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.transformation import TransformationService
from migration_agent.domain import (
    ApprovalSignature,
    AssuranceLevel,
    EvidenceReference,
    EvidenceStatus,
    FileMode,
    FileOperation,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    StepRisk,
    compute_plan_digest,
)
from migration_agent.domain.stack import (
    PackageCoordinate,
    PackageMappingOutcome,
    ReplacementStrategy,
    StackRecommendationDraft,
    compute_draft_digest,
)


def test_sanitize_project_name() -> None:
    assert sanitize_project_name("Sample Frontend") == "sample-frontend"
    assert sanitize_project_name("my_awesome_project!") == "my-awesome-project"
    assert sanitize_project_name("---dirty---name---") == "dirty-name"
    assert sanitize_project_name("") == "modern-app"


def test_foundation_adapter_render_files() -> None:
    adapter = FoundationTransformationAdapter()
    files = adapter.render_foundation_files("sample-frontend")

    required_keys = [
        "package.json",
        "tsconfig.json",
        "tsconfig.app.json",
        "angular.json",
        "src/index.html",
        "src/main.ts",
        "src/app/app.config.ts",
        "src/app/app.routes.ts",
        "src/app/app.component.ts",
        "src/styles.scss",
    ]
    for key in required_keys:
        assert key in files, f"Missing expected foundation file '{key}'"

    # Validate package.json contents
    pkg_json = json.loads(files["package.json"])
    assert pkg_json["name"] == "sample-frontend"
    assert pkg_json["private"] is True
    assert "ng" in pkg_json["scripts"]
    assert "build" in pkg_json["scripts"]
    assert "test" in pkg_json["scripts"]
    assert pkg_json["dependencies"]["@angular/core"] == "21.2.25"
    assert pkg_json["dependencies"]["bootstrap"] == "^5.3.3"
    assert pkg_json["devDependencies"]["typescript"] == "~5.9.3"

    # Validate angular.json configuration
    angular_json = json.loads(files["angular.json"])
    assert "sample-frontend" in angular_json["projects"]
    proj = angular_json["projects"]["sample-frontend"]
    assert proj["architect"]["build"]["builder"] == "@angular/build:application"

    # Validate Angular code standards: standalone and OnPush
    comp_ts = files["src/app/app.component.ts"]
    assert "standalone: true" in comp_ts
    assert "ChangeDetectionStrategy.OnPush" in comp_ts
    assert "RouterOutlet" in comp_ts


def test_foundation_adapter_with_draft_mappings() -> None:
    preset = get_default_target_preset()
    draft = StackRecommendationDraft(
        draft_id="draft-001",
        project_id="sample-frontend",
        source_revision="rev-001",
        governance_revision="gov-001",
        preset=preset,
        mappings=(
            PackageMappingOutcome(
                legacy_name="moment",
                strategy=ReplacementStrategy.REPLACE,
                target_packages=(
                    PackageCoordinate(
                        name="date-fns",
                        version_spec="^3.6.0",
                        purpose="Lightweight modern date utilities",
                    ),
                ),
                rationale="Replaced moment with modern date-fns",
            ),
        ),
        unmapped_dependencies=(),
        content_digest=compute_draft_digest({"test": "digest"}),
        created_at="2026-10-10T00:00:00Z",
        updated_at="2026-10-10T00:00:00Z",
    )

    adapter = FoundationTransformationAdapter()
    files = adapter.render_foundation_files("sample-frontend", draft=draft)
    pkg_json = json.loads(files["package.json"])
    assert "date-fns" in pkg_json["dependencies"]
    assert pkg_json["dependencies"]["date-fns"] == "^3.6.0"


def test_foundation_adapter_render_changes() -> None:
    adapter = FoundationTransformationAdapter()
    changes = adapter.render_foundation_changes("sample-frontend")
    assert len(changes) >= 10
    paths = {c.path for c in changes}
    assert "package.json" in paths
    assert "src/main.ts" in paths
    for c in changes:
        assert c.operation == FileOperation.CREATE
        assert c.file_mode == FileMode.STANDARD
        assert c.content_bytes is not None
        assert c.content_digest.startswith("sha256:")
        assert len(c.content_digest) == 71


def _create_approved_foundation_plan(source_root: Path) -> MigrationPlan:
    step = MigrationStep(
        step_id="step-001",
        title="Initialize Angular 17 foundation",
        description="Scaffold root workspace, package manifests, and bootstrap files",
        dependencies=[],
        scope="foundation",
        risk=StepRisk.LOW,
        confidence=1.0,
        evidence=[
            EvidenceReference(
                path="package.json",
                description="Declared legacy package manifest",
                line_number=1,
                sample='{"name": "test"}',
                status=EvidenceStatus.VALID,
            )
        ],
        expected_files=[
            "package.json",
            "tsconfig.json",
            "angular.json",
            "src/main.ts",
        ],
        validation_strategy=["ng build"],
        rollback_note="revert",
        acceptance_criteria=["Target toolchain compiles skeleton cleanly"],
        unresolved_questions=[],
    )

    preliminary_plan = MigrationPlan(
        plan_id="plan-foundation-001",
        source_root=str(source_root),
        run_id="run-foundation-001",
        status=PlanStatus.NEEDS_APPROVAL,
        steps=[step],
        policy_digest="sha256:test-policy",
    )
    plan_digest = compute_plan_digest(preliminary_plan)
    sig = ApprovalSignature(
        actor="operator",
        plan_digest=plan_digest,
        policy_digest="sha256:test-policy",
        assurance_level=AssuranceLevel.MODE_B,
        signature=f"sig:{plan_digest[:16]}",
    )
    return preliminary_plan.model_copy(update={"status": PlanStatus.APPROVED, "approval": sig})


def test_transformation_service_foundation_preview_and_stage(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "package.json").write_text('{"name": "legacy-app"}', encoding="utf-8")

    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        foundation_adapter=FoundationTransformationAdapter(),
    )
    plan = _create_approved_foundation_plan(source_root)

    # 1. Preview foundation changeset
    changeset, diff = service.preview(source_root, plan, step_id="step-001")
    assert changeset.step_id == "step-001"
    assert len(changeset.changes) >= 10
    assert '+  "name": "legacy-app"' in diff or "legacy-app" in diff

    # 2. Stage foundation changeset
    staged_dir, _ = service.stage(
        staging_root=staging_root,
        run_id="run-foundation-001",
        source_root=source_root,
        plan=plan,
        step_id="step-001",
    )

    assert staged_dir.is_dir()
    assert (staged_dir / "package.json").is_file()
    assert (staged_dir / "angular.json").is_file()
    assert (staged_dir / "src" / "main.ts").is_file()
    assert (staged_dir / "src" / "app" / "app.component.ts").is_file()

    staged_pkg = json.loads((staged_dir / "package.json").read_text(encoding="utf-8"))
    assert staged_pkg["name"] == "legacy-app"
    assert staged_pkg["dependencies"]["@angular/core"] == "21.2.25"


def test_transformation_service_apply_target_root_isolation(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "package.json").write_text('{"name": "legacy-app"}', encoding="utf-8")

    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        foundation_adapter=FoundationTransformationAdapter(),
    )
    plan = _create_approved_foundation_plan(source_root)
    changeset, _ = service.preview(source_root, plan, step_id="step-001")

    # Overlapping target_root equals source_root must be rejected
    with pytest.raises(ValueError, match="OVERLAPPING_ROOTS_REJECTED"):
        service.apply(
            source_root=source_root,
            changeset=changeset,
            plan=plan,
            actor="architect",
            target_root=source_root,
        )

    # Overlapping target_root inside source_root must be rejected
    nested_target = source_root / "sub-target"
    nested_target.mkdir()
    with pytest.raises(ValueError, match="OVERLAPPING_ROOTS_REJECTED"):
        service.apply(
            source_root=source_root,
            changeset=changeset,
            plan=plan,
            actor="architect",
            target_root=nested_target,
        )

    # Distinct target_root routes correctly to apply_gateway
    mock_gateway = MagicMock()
    mock_apply_port = MagicMock()
    mock_gateway.return_value = mock_apply_port

    service_with_gateway = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        apply_gateway=mock_gateway,
    )
    distinct_target = tmp_path / "target"
    distinct_target.mkdir()

    service_with_gateway.apply(
        source_root=source_root,
        changeset=changeset,
        plan=plan,
        actor="architect",
        target_root=distinct_target,
    )

    mock_gateway.assert_called_once_with(distinct_target.resolve())
    mock_apply_port.apply.assert_called_once_with(
        plan.plan_id, changeset.step_id, changeset.changeset_id
    )


def test_host_proposal_service_accepts_foundation_step(tmp_path: Path) -> None:
    from hashlib import sha256

    from migration_agent.application.host_proposals import HostProposalService
    from migration_agent.domain.host_workflow import (
        EvidenceCitation,
        PlanProposal,
        RepositoryState,
        WriterLease,
    )

    source_root = tmp_path / "repo"
    source_root.mkdir()
    pkg_content = '{"name": "test-repo"}\n'
    (source_root / "package.json").write_text(pkg_content, encoding="utf-8")
    pkg_sha = sha256(pkg_content.encode("utf-8")).hexdigest()

    from migration_agent.domain import AnalysisFinding
    from migration_agent.domain.host_workflow import AnalysisProposal
    from migration_agent.ports.governance import ProjectPolicy

    evidence_port = MagicMock()
    evidence_port.read_text.return_value = pkg_content
    evidence_port.read_file.return_value = pkg_content
    evidence_port.policy_digest.return_value = "sha256:policy"
    evidence_port.policy.return_value = ProjectPolicy()
    evidence_port.inventory.return_value = None

    state = RepositoryState(
        revision="rev-001",
        root_commit="commit-001",
        fingerprint="fp-001",
        clean=True,
    )
    evidence_port.repository_state.return_value = state

    store = MagicMock()
    store.acquire_lease.return_value = WriterLease(
        project_id="test-proj",
        owner="architect",
        generation=1,
        expires_at=9999999999.0,
    )
    store.claim_request.side_effect = lambda op: (op, True)
    store.get_analysis.return_value = AnalysisProposal(
        base_revision="rev-001",
        worktree_fingerprint="fp-001",
        summary="Analysis",
        findings=(
            AnalysisFinding(
                id="finding-001",
                category="architecture",
                title="Legacy app",
                description="App overview",
                severity="low",
                confidence=1.0,
                evidence_references=(
                    EvidenceReference(
                        path="package.json",
                        description="Manifest",
                        line_number=1,
                        sample='{"name": "test-repo"}',
                        status=EvidenceStatus.VALID,
                    ),
                ),
            ),
        ),
        citations=(EvidenceCitation(path="package.json", sha256=pkg_sha, line=1),),
    )
    checkpoints = MagicMock()
    mock_decision = MagicMock()
    mock_decision.principal_id = "principal-001"
    mock_decision.access_digest = "sha256:access"
    auth = MagicMock()
    auth.require.return_value = mock_decision

    service = HostProposalService(
        project_id="test-proj",
        root=source_root,
        evidence=evidence_port,
        store=store,
        checkpoints=checkpoints,
        actor="architect",
        authorization=auth,
    )

    step = MigrationStep(
        step_id="step-001",
        title="Initialize Angular 17 foundation",
        description="Scaffold root workspace, package manifests, and bootstrap files",
        dependencies=[],
        scope="foundation",
        risk=StepRisk.LOW,
        confidence=1.0,
        evidence=[
            EvidenceReference(
                path="package.json",
                description="Declared legacy package manifest",
                line_number=1,
                sample='{"name": "test-repo"}',
                status=EvidenceStatus.VALID,
            )
        ],
        expected_files=[
            "package.json",
            "tsconfig.json",
            "angular.json",
            "src/main.ts",
        ],
        validation_strategy=["ng build"],
        rollback_note="revert",
        acceptance_criteria=["compiles cleanly"],
        unresolved_questions=[],
    )

    proposal = PlanProposal(
        base_revision="rev-001",
        worktree_fingerprint="fp-001",
        analysis_id="analysis-001",
        steps=(step,),
        citations=(EvidenceCitation(path="package.json", sha256=pkg_sha, line=1),),
    )

    op = service.submit_plan("req-001", proposal)
    assert op.status.value == "SUCCEEDED"
    assert op.plan_id is not None
