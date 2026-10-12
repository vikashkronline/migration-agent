"""Regression coverage for the Phase 16A read boundary."""

import logging
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

from migration_agent.adapters.checkpoints import SqliteCheckpointStore
from migration_agent.adapters.filesystem import SafeFilesystemInspector, read_repository_text
from migration_agent.adapters.governance import GitGovernanceAdapter
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.mcp.server import (
    RedactingStreamHandler,
    create_mcp_server,
    run_mcp_server,
)
from migration_agent.adapters.mcp.tools import (
    handle_inventory,
    handle_plan_show,
    handle_run_status,
    handle_step_preview,
)
from migration_agent.adapters.transforms import (
    AngularJsDirectiveExtractor,
    AngularStandaloneComponentRenderer,
)
from migration_agent.config import Settings
from migration_agent.domain.changeset import compute_worktree_fingerprint
from migration_agent.domain.inspection_access import (
    InspectionCapability,
    InspectionContext,
    authorize_inspection,
)
from migration_agent.domain.planning import AssuranceLevel, MigrationPlan, MigrationStep
from migration_agent.domain.run_state import RunRecord
from migration_agent.ports import InspectionPolicy

TOKEN = "sk-review-fixture-not-a-real-credential-123456"
FIXTURE = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"


@pytest.fixture
def project(tmp_path: Path) -> tuple[ProjectBinding, MigrationPlan, SqliteCheckpointStore]:
    root = tmp_path / "source"
    shutil.copytree(FIXTURE, root)
    binding = ProjectBinding(root)
    plan = MigrationPlan(
        plan_id="plan-one",
        source_root=str(root),
        run_id="run-one",
        steps=[
            MigrationStep(
                step_id="step-one",
                title="Migrate user-card",
                description="review fixture",
                expected_files=["app/components/user-card.js"],
            )
        ],
    )
    store = SqliteCheckpointStore(tmp_path / "state")
    store.save_plan(plan)
    return binding, plan, store


def changeset_count(store: SqliteCheckpointStore) -> int:
    with store._get_connection() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM changesets").fetchone()[0])


@pytest.mark.parametrize("tool", ["plan", "run", "preview"])
def test_foreign_records_are_rejected(project, tmp_path: Path, tool: str) -> None:
    binding, plan, store = project
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    store.save_plan(plan.model_copy(update={"source_root": str(foreign)}))
    store.save_run_record(
        RunRecord(run_id=plan.run_id, plan_id=plan.plan_id, source_root=str(foreign))
    )
    with pytest.raises(ValueError, match="PROJECT_MISMATCH"):
        if tool == "plan":
            handle_plan_show(binding, binding.project_id, plan.plan_id, store)
        elif tool == "run":
            handle_run_status(binding, binding.project_id, plan.run_id, store)
        else:
            handle_step_preview(binding, binding.project_id, plan.plan_id, "step-one", store)
    assert changeset_count(store) == 0


def test_foreign_related_run_is_rejected(project, tmp_path: Path) -> None:
    binding, plan, store = project
    store.save_run_record(
        RunRecord(run_id=plan.run_id, plan_id=plan.plan_id, source_root=str(tmp_path))
    )
    with pytest.raises(ValueError, match="PROJECT_MISMATCH"):
        handle_plan_show(binding, binding.project_id, plan.plan_id, store)


@pytest.mark.parametrize("relative", [".", "inside", ".."])
def test_server_rejects_state_overlap_before_writing(tmp_path: Path, relative: str) -> None:
    root = tmp_path / "source"
    root.mkdir()
    with pytest.raises(ValueError, match="UNSAFE_ROOT_OVERLAP"):
        create_mcp_server(ProjectBinding(root), state_dir=root / relative)
    assert not list(tmp_path.rglob("checkpoints.db"))
    assert not (root / "inside").exists()


def test_environment_state_overlap_and_staging_overlap(project, monkeypatch) -> None:
    binding, _, store = project
    monkeypatch.setenv("AGENT_STATE_DIR", str(binding.project_root / "state"))
    with pytest.raises(ValueError, match="UNSAFE_ROOT_OVERLAP"):
        create_mcp_server(binding)
    with pytest.raises(ValueError, match="UNSAFE_ROOT_OVERLAP"):
        create_mcp_server(
            binding,
            state_dir=store.state_dir,
            settings=Settings(staging_root=store.state_dir / "staging"),
        )


def test_preview_has_no_source_local_store_fallback(project) -> None:
    binding, plan, _ = project
    before = sorted(
        path.relative_to(binding.project_root).as_posix()
        for path in binding.project_root.rglob("*")
    )
    with pytest.raises(ValueError, match="STATE_STORE_REQUIRED"):
        handle_step_preview(binding, binding.project_id, plan.plan_id)
    assert before == sorted(
        path.relative_to(binding.project_root).as_posix()
        for path in binding.project_root.rglob("*")
    )


def test_ids_are_root_bound_and_manifest_claims_cannot_collide(tmp_path: Path) -> None:
    roots = [tmp_path / "one" / "app..name", tmp_path / "two" / "app..name"]
    for root in roots:
        root.mkdir(parents=True)
        GitGovernanceAdapter().ensure_governance_layout(str(root), "same-declared-id")
    first, second = [ProjectBinding(root) for root in roots]
    assert first.project_id != second.project_id
    first.validate_project_id(first.project_id)
    assert ProjectBinding(roots[0]).project_id == first.project_id


def test_invalid_manifest_claim_fails_at_startup(tmp_path: Path) -> None:
    GitGovernanceAdapter().ensure_governance_layout(str(tmp_path), "../invalid")
    with pytest.raises(ValueError, match="INVALID_ID"):
        ProjectBinding(tmp_path)


@pytest.mark.parametrize(
    "relative",
    ["app/components/user-card.js", "app/styles/app.css", "app/templates/components/user-card.hbs"],
)
def test_preview_rejects_outside_links(project, tmp_path: Path, relative: str) -> None:
    binding, plan, store = project
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-fixture-marker", encoding="utf-8")
    target = binding.project_root / relative
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("host does not support symbolic links")
    with pytest.raises(ValueError, match="SOURCE_PATH_REJECTED"):
        handle_step_preview(binding, binding.project_id, plan.plan_id, "step-one", store)
    assert changeset_count(store) == 0


@pytest.mark.parametrize("kind", ["manifest", "plan"])
def test_governance_reads_reject_outside_links(project, tmp_path: Path, kind: str) -> None:
    binding, plan, _ = project
    gov = GitGovernanceAdapter()
    gov.ensure_governance_layout(str(binding.project_root))
    relative = ".agent/manifest.json" if kind == "manifest" else f".agent/plans/{plan.plan_id}.json"
    target = binding.project_root / relative
    if target.exists():
        target.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text(plan.model_dump_json(), encoding="utf-8")
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("host does not support symbolic links")
    with pytest.raises(ValueError, match="SOURCE_PATH_REJECTED"):
        if kind == "manifest":
            ProjectBinding(binding.project_root)
        else:
            gov.load_plan(str(binding.project_root), plan.plan_id)


def test_known_secret_files_are_never_opened(tmp_path: Path, monkeypatch) -> None:
    secret = tmp_path / "credentials.json"
    secret.write_text("synthetic only", encoding="utf-8")
    opening = Mock(side_effect=AssertionError("credential file opened"))
    monkeypatch.setattr("os.open", opening)
    with pytest.raises(ValueError, match="credential file"):
        read_repository_text(tmp_path, secret.name)
    assert compute_worktree_fingerprint(tmp_path).startswith("sha256:")
    opening.assert_not_called()


def test_oversized_companion_rejected_before_open(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "large.html").write_text("x" * 33, encoding="utf-8")
    opening = Mock(side_effect=AssertionError("oversized file opened"))
    monkeypatch.setattr("os.open", opening)
    with pytest.raises(ValueError, match="byte limit"):
        read_repository_text(
            tmp_path, "large.html", policy=InspectionPolicy(max_text_file_bytes=32)
        )
    opening.assert_not_called()


def test_ignored_directive_is_not_discovered(tmp_path: Path) -> None:
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "evil.directive.js").write_text(TOKEN, encoding="utf-8")
    assert AngularJsDirectiveExtractor().discover_components(tmp_path) == ()


@pytest.mark.parametrize("step_id", ["missing", "", "   "])
def test_unknown_or_blank_step_does_not_persist(project, step_id: str) -> None:
    binding, plan, store = project
    with pytest.raises(ValueError, match=r"INVALID_(STEP_)?ID"):
        handle_step_preview(binding, binding.project_id, plan.plan_id, step_id, store)
    assert changeset_count(store) == 0


def test_secret_plan_display_is_redacted_but_preview_rejected(project) -> None:
    binding, plan, store = project
    secret_plan = plan.model_copy(
        update={"steps": [plan.steps[0].model_copy(update={"description": TOKEN})]}
    )
    store.save_plan(secret_plan)
    result = handle_plan_show(binding, binding.project_id, plan.plan_id, store)
    assert TOKEN not in result.model_dump_json()
    assert result.redacted and result.display_only
    with pytest.raises(ValueError, match="SECRET_CONTENT_REJECTED"):
        handle_step_preview(binding, binding.project_id, plan.plan_id, "step-one", store)
    assert changeset_count(store) == 0


def test_secret_source_cannot_enter_diff_or_changeset(project) -> None:
    binding, plan, store = project
    template = binding.project_root / "app/templates/components/user-card.hbs"
    template.write_text(f'<div ng-if="true">{TOKEN}</div>', encoding="utf-8")
    with pytest.raises(ValueError, match="SECRET_CONTENT_REJECTED"):
        handle_step_preview(binding, binding.project_id, plan.plan_id, "step-one", store)
    assert changeset_count(store) == 0
    snapshot = SafeFilesystemInspector().inspect(binding.project_root, InspectionPolicy())
    assert all(TOKEN not in file.content for file in snapshot.files)


@pytest.mark.parametrize(
    "output, error",
    [(TOKEN, "SECRET_CONTENT_REJECTED"), ("x" * 40_000, "PREVIEW_TOO_LARGE")],
    ids=["secret", "oversized"],
)
def test_generated_content_rejected_before_persistence(
    project, monkeypatch, output: str, error: str
) -> None:
    binding, plan, store = project
    monkeypatch.setattr(
        AngularStandaloneComponentRenderer, "render_component_ts", lambda self, component: output
    )
    with pytest.raises(ValueError, match=error):
        handle_step_preview(binding, binding.project_id, plan.plan_id, "step-one", store)
    assert changeset_count(store) == 0


def test_inventory_and_plan_pages_are_bounded_and_complete(project) -> None:
    binding, plan, store = project
    complete_files = handle_inventory(binding).files_total
    paths = []
    for offset in range(complete_files):
        page = handle_inventory(binding, file_offset=offset, file_limit=1)
        paths.extend(file.path for file in page.inventory.files)
        assert page.has_more_files == (offset + 1 < complete_files)
    assert len(set(paths)) == complete_files
    steps = [plan.steps[0].model_copy(update={"step_id": f"step-{index}"}) for index in range(105)]
    store.save_plan(plan.model_copy(update={"steps": steps}))
    first = handle_plan_show(binding, binding.project_id, plan.plan_id, store, step_limit=100)
    second = handle_plan_show(binding, binding.project_id, plan.plan_id, store, step_offset=100)
    assert first.steps_total == 105 and first.has_more_steps
    assert len(second.plan.steps) == 5 and not second.has_more_steps
    assert first.plan_digest == second.plan_digest


def test_single_oversized_plan_view_fails_closed(project) -> None:
    binding, plan, store = project
    store.save_plan(
        plan.model_copy(
            update={"steps": [plan.steps[0].model_copy(update={"description": "x" * 70_000})]}
        )
    )
    with pytest.raises(ValueError, match="RESPONSE_TOO_LARGE"):
        handle_plan_show(binding, binding.project_id, plan.plan_id, store)


@pytest.mark.parametrize(
    "policy", [InspectionPolicy(max_total_text_bytes=15), InspectionPolicy(max_text_files=1)]
)
def test_total_inspection_budget(tmp_path: Path, policy: InspectionPolicy) -> None:
    for name in ("one.js", "two.js"):
        (tmp_path / name).write_text("x" * 10, encoding="utf-8")
    with pytest.raises(ValueError, match="INSPECTION_TOO_LARGE"):
        SafeFilesystemInspector().inspect(tmp_path, policy)


def test_read_policy_denies_missing_capability_and_insufficient_assurance() -> None:
    context = InspectionContext(
        actor="local-review-user",
        assurance=AssuranceLevel.MODE_C,
        capabilities=frozenset(InspectionCapability),
    )
    authorize_inspection(context, InspectionCapability.PROJECT_READ)
    with pytest.raises(ValueError, match="ASSURANCE_REQUIRED"):
        authorize_inspection(context, InspectionCapability.PLAN_READ)
    denied = context.model_copy(update={"capabilities": frozenset()})
    with pytest.raises(ValueError, match="CAPABILITY_DENIED"):
        authorize_inspection(denied, InspectionCapability.PROJECT_READ)


@pytest.mark.parametrize(
    "exception", [RuntimeError("synthetic transport failure"), KeyboardInterrupt()]
)
def test_transport_failure_and_interrupt_have_defined_exits(
    project, monkeypatch, exception
) -> None:
    binding, _, store = project
    monkeypatch.setattr(
        "migration_agent.adapters.mcp.server.anyio.run", Mock(side_effect=exception)
    )
    if isinstance(exception, KeyboardInterrupt):
        run_mcp_server(binding.project_root, store.state_dir)
    else:
        with pytest.raises(SystemExit) as exit_info:
            run_mcp_server(binding.project_root, store.state_dir)
        assert exit_info.value.code == 1


def test_log_handler_redacts_deliberately_emitted_secret() -> None:
    record = logging.LogRecord(
        "review", logging.ERROR, __file__, 1, "Synthetic token %s", (TOKEN,), None
    )
    assert TOKEN not in RedactingStreamHandler().format(record)


def test_checkpoint_connections_close(project) -> None:
    _, _, store = project
    with store._get_connection() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_step_scope_does_not_include_another_component(project) -> None:
    binding, plan, store = project
    components = binding.project_root / "app/components"
    shutil.copyfile(components / "user-card.js", components / "other-card.js")
    result = handle_step_preview(binding, binding.project_id, plan.plan_id, "step-one", store)
    assert result.file_count == 4 and "OtherCardComponent" not in result.diff
    other = plan.model_copy(
        update={
            "steps": [
                MigrationStep(
                    step_id="other-step",
                    title="Migrate other-card",
                    description="Migrate the other component",
                    expected_files=["app/components/other-card.js"],
                )
            ]
        }
    )
    store.save_plan(other)
    result = handle_step_preview(binding, binding.project_id, plan.plan_id, "other-step", store)
    assert "OtherCardComponent" in result.diff and "UserCardComponent" not in result.diff


def test_omitted_step_is_explicit_and_multiple_steps_require_selection(project) -> None:
    binding, plan, store = project
    result = handle_step_preview(binding, binding.project_id, plan.plan_id, checkpoint_store=store)
    assert result.step_id == "step-one"
    store.save_plan(
        plan.model_copy(
            update={
                "steps": [plan.steps[0], plan.steps[0].model_copy(update={"step_id": "step-two"})]
            }
        )
    )
    with pytest.raises(ValueError, match="STEP_REQUIRED"):
        handle_step_preview(binding, binding.project_id, plan.plan_id, checkpoint_store=store)


def test_state_link_alias_cannot_overlap_source(project, tmp_path: Path) -> None:
    binding, _, _ = project
    alias = tmp_path / "state-alias"
    try:
        alias.symlink_to(binding.project_root, target_is_directory=True)
    except OSError:
        pytest.skip("host does not support symbolic links")
    with pytest.raises(ValueError, match="UNSAFE_ROOT_OVERLAP"):
        create_mcp_server(binding, state_dir=alias)
    assert not (binding.project_root / "checkpoints.db").exists()


@pytest.mark.parametrize("relative", ["../outside.txt", "/outside.txt", ""])
def test_fingerprint_explicit_paths_cannot_escape(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError, match="SOURCE_PATH_REJECTED"):
        compute_worktree_fingerprint(tmp_path, [relative])


def test_preview_rejects_duplicate_plan_steps(project) -> None:
    binding, plan, store = project
    store.save_plan(plan.model_copy(update={"steps": [plan.steps[0], plan.steps[0]]}))
    with pytest.raises(ValueError, match="INVALID_STEP_ID"):
        handle_step_preview(binding, binding.project_id, plan.plan_id, "step-one", store)
    assert changeset_count(store) == 0


@pytest.mark.parametrize("kind, expected_count", [("component", 4), ("service", 2)])
def test_expected_paths_override_description_mentions(
    tmp_path: Path, kind: str, expected_count: int
) -> None:
    root = tmp_path / "source"
    shutil.copytree(FIXTURE.parent / "angularjs-realworld-dashboard", root)
    binding = ProjectBinding(root)
    expected = (
        "src/user-profile.directive.js" if kind == "component" else "src/user-data.service.js"
    )
    plan = MigrationPlan(
        plan_id="scoped-plan",
        source_root=str(root),
        run_id="scoped-run",
        steps=[
            MigrationStep(
                step_id="selected",
                title="UserProfile and UserDataService",
                description="References both UserProfile and UserDataService",
                expected_files=[expected],
            )
        ],
    )
    store = SqliteCheckpointStore(tmp_path / "state")
    store.save_plan(plan)
    result = handle_step_preview(binding, binding.project_id, plan.plan_id, "selected", store)
    assert result.file_count == expected_count
    changeset = store.get_changeset(result.changeset_id)
    assert changeset is not None
    assert all(
        ("/components/" in change.path) == (kind == "component") for change in changeset.changes
    )
