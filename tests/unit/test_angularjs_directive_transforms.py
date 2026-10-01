"""Unit tests for AngularJS directive extraction and Angular Standalone rendering."""

import shutil
from pathlib import Path

from migration_agent.adapters import (
    AngularJsDirectiveExtractor,
    AngularStandaloneComponentRenderer,
    LocalWorkspaceAdapter,
)
from migration_agent.application.transformation import TransformationService
from migration_agent.domain import (
    ApprovalSignature,
    AssuranceLevel,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    StepRisk,
    compute_plan_digest,
)


def _approved_plan(repo: Path) -> MigrationPlan:
    step = MigrationStep(
        step_id="step-001",
        title="Migrate UserBadge directive to modern Angular standalone component.",
        description="Migrate UserBadge directive to modern Angular standalone component.",
        expected_files=[
            "src/app/components/user-badge/user-badge.component.ts",
            "src/app/components/user-badge/user-badge.component.html",
            "src/app/components/user-badge/user-badge.component.scss",
            "src/app/components/user-badge/user-badge.component.spec.ts",
        ],
        risk=StepRisk.LOW,
    )
    draft = MigrationPlan(
        plan_id="plan-ngjs-001",
        source_root=str(repo),
        run_id="run-ngjs-001",
        status=PlanStatus.DRAFT,
        steps=[step],
        policy_digest="dummy-policy-digest",
    )
    digest = compute_plan_digest(draft)
    approval = ApprovalSignature(
        actor="operator@example.com",
        plan_digest=digest,
        policy_digest="dummy-policy-digest",
        assurance_level=AssuranceLevel.MODE_B,
        signature=f"sig:{digest[:16]}",
    )
    return draft.model_copy(update={"status": PlanStatus.APPROVED, "approval": approval})


def test_angularjs_directive_extractor_from_fixture() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    extractor = AngularJsDirectiveExtractor()

    bundles = extractor.discover_components(fixture_dir)
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.component_name == "UserBadge"
    assert any(f.endswith("user-badge.directive.js") for f in bundle.source_files)
    assert any(f.endswith("user-badge.template.html") for f in bundle.source_files)

    component = extractor.extract(
        component_source=bundle.component_source,
        template_source=bundle.template_source,
        style_source=bundle.style_source,
    )

    assert component.name == "UserBadge"
    assert component.tag_name == "app-user-badge"
    assert "name" in component.inputs
    assert "role" in component.inputs
    assert "isExpanded" in component.state_properties
    assert component.methods == ("toggleDetails",)
    assert component.input_types.get("name") == "string"
    assert component.input_types.get("role") == "string"
    assert component.state_types.get("isExpanded") == "boolean"
    assert component.metadata["source_framework"] == "angularjs-directive"


def test_angular_standalone_renderer_from_angularjs_directive() -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    extractor = AngularJsDirectiveExtractor()
    bundles = extractor.discover_components(fixture_dir)
    component = extractor.extract(
        component_source=bundles[0].component_source,
        template_source=bundles[0].template_source,
        style_source=bundles[0].style_source,
    )

    renderer = AngularStandaloneComponentRenderer()

    # 1. Component TypeScript
    ts_code = renderer.render_component_ts(component)
    assert "standalone: true" in ts_code
    assert "ChangeDetectionStrategy.OnPush" in ts_code
    assert "selector: 'app-user-badge'" in ts_code
    assert "templateUrl: './user-badge.component.html'" in ts_code
    assert "styleUrls: ['./user-badge.component.scss']" in ts_code
    assert "export class UserBadgeComponent" in ts_code
    assert "readonly name = input<string>('');" in ts_code
    assert "readonly role = input<string>('');" in ts_code
    assert "readonly isExpanded = signal<boolean>(false);" in ts_code
    assert "toggleDetails(): void" in ts_code
    assert "this.isExpanded.update((current) => !current);" in ts_code

    # 2. Template HTML
    html_code = renderer.render_template_html(component)
    assert '<article class="user-badge card p-3 shadow-sm">' in html_code
    assert "@if (isExpanded())" in html_code
    assert "*ngIf" not in html_code
    assert '(click)="toggleDetails()"' in html_code

    # 3. Component SCSS
    scss_code = renderer.render_style_scss(component)
    assert ".user-badge" in scss_code

    # 4. Spec TypeScript
    spec_code = renderer.render_spec_ts(component)
    assert "describe('UserBadgeComponent'" in spec_code
    assert "imports: [UserBadgeComponent]" in spec_code
    assert "component.toggleDetails();" in spec_code
    assert "expect(component.isExpanded()).toBeTrue();" in spec_code


def test_transformation_service_preview_angularjs_directive(tmp_path: Path) -> None:
    fixture_src = Path(__file__).parents[1] / "fixtures" / "angularjs-directive-mini"
    repo_dst = tmp_path / "repo"
    shutil.copytree(fixture_src, repo_dst)

    plan = _approved_plan(repo_dst)
    service = TransformationService(
        workspace_adapter=LocalWorkspaceAdapter(),
        extractor=AngularJsDirectiveExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
    )

    changeset, diff_text = service.preview(repo_dst, plan)

    assert changeset.plan_id == plan.plan_id
    assert len(changeset.changes) == 4
    assert any(c.path.endswith("user-badge.component.ts") for c in changeset.changes)
    assert any(c.path.endswith("user-badge.component.html") for c in changeset.changes)
    assert any(c.path.endswith("user-badge.component.scss") for c in changeset.changes)
    assert any(c.path.endswith("user-badge.component.spec.ts") for c in changeset.changes)
    assert "UserBadgeComponent" in diff_text
    assert changeset.changeset_digest.startswith("sha256:")
