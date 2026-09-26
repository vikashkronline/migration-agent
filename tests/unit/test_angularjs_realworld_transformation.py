"""Unit tests for real-world enterprise AngularJS dashboard migration.

Covers multi-component and service transformation.
"""

from pathlib import Path

from migration_agent.adapters import (
    AngularJsDirectiveExtractor,
    AngularJsServiceExtractor,
    AngularStandaloneComponentRenderer,
    AngularStandaloneServiceRenderer,
    LocalWorkspaceAdapter,
)
from migration_agent.application.transformation import TransformationService
from migration_agent.domain import (
    MigrationPlan,
    MigrationStep,
)


def test_angularjs_realworld_dashboard_component_discovery() -> None:
    fixture_root = Path(__file__).parents[1] / "fixtures" / "angularjs-realworld-dashboard"
    extractor = AngularJsDirectiveExtractor()

    bundles = extractor.discover_components(fixture_root)
    assert len(bundles) == 2

    bundle_names = {b.component_name for b in bundles}
    assert "UserProfile" in bundle_names
    assert "ActivityFeed" in bundle_names


def test_angularjs_realworld_dashboard_service_discovery_and_extraction() -> None:
    fixture_root = Path(__file__).parents[1] / "fixtures" / "angularjs-realworld-dashboard"
    extractor = AngularJsServiceExtractor()

    bundles = extractor.discover_services(fixture_root)
    assert len(bundles) == 1
    assert bundles[0].service_name == "UserDataService"

    service = extractor.extract_service(bundles[0].service_source)
    assert service.name == "UserDataService"
    assert len(service.methods) == 2

    methods_by_name = {m.name: m for m in service.methods}
    assert "getUsers" in methods_by_name
    assert methods_by_name["getUsers"].http_method == "GET"
    assert methods_by_name["getUsers"].endpoint == "/api/v1/users"

    assert "updateStatus" in methods_by_name
    assert methods_by_name["updateStatus"].http_method == "POST"
    assert "/api/v1/users/" in methods_by_name["updateStatus"].endpoint


def test_angular_standalone_service_rendering() -> None:
    fixture_root = Path(__file__).parents[1] / "fixtures" / "angularjs-realworld-dashboard"
    extractor = AngularJsServiceExtractor()
    bundles = extractor.discover_services(fixture_root)
    service = extractor.extract_service(bundles[0].service_source)

    renderer = AngularStandaloneServiceRenderer()
    ts_code = renderer.render_service_ts(service)

    assert "@Injectable({" in ts_code
    assert "providedIn: 'root'" in ts_code
    assert "export class UserDataService" in ts_code
    assert "private readonly http = inject(HttpClient);" in ts_code
    assert "getUsers(): Observable<any>" in ts_code
    assert "return this.http.get<any>('/api/v1/users');" in ts_code
    assert "updateStatus(userId: any, status: any): Observable<any>" in ts_code

    spec_code = renderer.render_spec_ts(service)
    assert "describe('UserDataService'" in spec_code
    assert "HttpTestingController" in spec_code
    assert "provideHttpClientTesting()" in spec_code
    assert "httpMock.expectOne('/api/v1/users')" in spec_code


def test_angularjs_realworld_dashboard_component_rendering() -> None:
    fixture_root = Path(__file__).parents[1] / "fixtures" / "angularjs-realworld-dashboard"
    extractor = AngularJsDirectiveExtractor()
    bundles = extractor.discover_components(fixture_root)

    renderer = AngularStandaloneComponentRenderer()

    # 1. UserProfile component
    user_bundle = next(b for b in bundles if b.component_name == "UserProfile")
    user_comp = extractor.extract(
        user_bundle.component_source,
        user_bundle.template_source,
        user_bundle.style_source,
    )
    user_ts = renderer.render_component_ts(user_comp)
    assert "standalone: true" in user_ts
    assert "ChangeDetectionStrategy.OnPush" in user_ts
    assert "export class UserProfileComponent" in user_ts
    assert "readonly name = input<string>('');" in user_ts
    assert "readonly isExpanded = signal<boolean>(false);" in user_ts
    assert "toggleDetails(): void" in user_ts

    # 2. ActivityFeed component
    feed_bundle = next(b for b in bundles if b.component_name == "ActivityFeed")
    feed_comp = extractor.extract(
        feed_bundle.component_source,
        feed_bundle.template_source,
        feed_bundle.style_source,
    )
    feed_ts = renderer.render_component_ts(feed_comp)
    assert "standalone: true" in feed_ts
    assert "ChangeDetectionStrategy.OnPush" in feed_ts
    assert "export class ActivityFeedComponent" in feed_ts
    assert "readonly title = input<string>('');" in feed_ts
    assert "toggleFeed(): void" in feed_ts


def test_angular_template_migration_helpers() -> None:
    renderer = AngularStandaloneComponentRenderer()
    raw_tpl = """
    <div class="card pull-right col-xs-12">
      <button class="btn" ng-click="toggleDetails()">Toggle</button>
      <div ng-if="isExpanded">Details</div>
    </div>
    """
    comp = AngularJsDirectiveExtractor().extract("")
    migrated = renderer.migrate_template(raw_tpl, comp)

    assert "pull-right" not in migrated
    assert "ms-auto" in migrated
    assert "col-xs-12" not in migrated
    assert "col-12" in migrated
    assert '(click)="toggleDetails()"' in migrated
    assert "@if (isExpanded())" in migrated


def test_transformation_service_realworld_preview(tmp_path: Path) -> None:
    fixture_root = Path(__file__).parents[1] / "fixtures" / "angularjs-realworld-dashboard"
    workspace_adapter = LocalWorkspaceAdapter()

    service = TransformationService(
        workspace_adapter=workspace_adapter,
        extractor=AngularJsDirectiveExtractor(),
        renderer=AngularStandaloneComponentRenderer(),
        service_extractor=AngularJsServiceExtractor(),
        service_renderer=AngularStandaloneServiceRenderer(),
    )

    plan = MigrationPlan(
        plan_id="plan-dashboard",
        source_root=str(fixture_root),
        run_id="run-dash-01",
        steps=[MigrationStep(step_id="step-1", title="Migrate dashboard", description="desc")],
    )

    changeset, diff = service.preview(fixture_root, plan)

    # Verify both components and the service were generated
    changed_paths = {c.path for c in changeset.changes}
    assert "src/app/components/user-profile/user-profile.component.ts" in changed_paths
    assert "src/app/components/user-profile/user-profile.component.html" in changed_paths
    assert "src/app/components/activity-feed/activity-feed.component.ts" in changed_paths
    assert "src/app/components/activity-feed/activity-feed.component.html" in changed_paths
    assert "src/app/services/user-data-service.service.ts" in changed_paths
    assert "src/app/services/user-data-service.service.spec.ts" in changed_paths

    assert changeset.changeset_digest.startswith("sha256:")
    assert "diff --git" in diff or "---" in diff
