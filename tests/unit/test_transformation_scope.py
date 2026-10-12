"""Exact pod selection and feature-qualified paths across repeated basenames."""

from migration_agent.adapters.filesystem import SafeFilesystemInspector
from migration_agent.adapters.mcp.tools import _create_default_framework_registry
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.transformation import TransformationService
from migration_agent.domain.planning import MigrationPlan, MigrationStep


def test_pod_scope_selects_exact_bundle_before_extraction_and_preserves_namespace(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "package.json").write_text('{"dependencies":{"ember-source":"3.8.1"}}')
    for namespace in ("alpha", "beta"):
        folder = root / "app/features/components" / namespace / "shared"
        folder.mkdir(parents=True)
        source = "import Component from '@ember/component'; export default Component.extend({});"
        if namespace == "beta":
            source = "unsupported source that must not be extracted for the alpha task"
        (folder / "component.js").write_text(source)
        (folder / "template.hbs").write_text("<h2>{{@title}}</h2>")
    plan = MigrationPlan(
        plan_id="scope-plan",
        source_root=str(root),
        run_id="scope-run",
        steps=[
            MigrationStep(
                step_id="alpha",
                title="Alpha",
                description="Alpha only",
                expected_files=["app/features/components/alpha/shared/component.js"],
                validation_strategy=["build"],
            )
        ],
    )
    service = TransformationService(
        LocalWorkspaceAdapter(),
        registry=_create_default_framework_registry(),
        filesystem=SafeFilesystemInspector(),
    )
    changeset, _ = service.preview(root, plan, "alpha")
    assert len(changeset.changes) == 4
    assert all(
        change.path.startswith("src/app/components/alpha/shared/") for change in changeset.changes
    )
    assert b"app-alpha-shared" in next(
        change.content_bytes
        for change in changeset.changes
        if change.path.endswith(".component.ts")
    )
