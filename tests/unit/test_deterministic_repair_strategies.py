"""Unit tests for deterministic surgical repair strategies (Phase 14)."""

from pathlib import Path

from migration_agent.adapters.command_runner import FakeCommandRunner
from migration_agent.adapters.workspace import LocalWorkspaceAdapter
from migration_agent.application.diagnostics import DiagnosticCategory, StructuredDiagnostic
from migration_agent.application.repair_strategies import (
    AutoImportRepairStrategy,
    DeterministicRepairEngine,
    SignalCallRepairStrategy,
    SpecTestBedRepairStrategy,
    SyntaxLintRepairStrategy,
)
from migration_agent.application.validation import BoundedRepairService, ValidationService
from migration_agent.domain import (
    ChangeSet,
    FileChange,
    FileMode,
    FileOperation,
    MigrationPlan,
    MigrationStep,
    PlanStatus,
    ValidationCommand,
    ValidationProfile,
    ValidationResult,
    ValidationStatus,
    compute_changeset_digest,
    compute_file_sha256,
)


def _make_file_change(path: str, content: str) -> FileChange:
    b = content.encode("utf-8")
    return FileChange(
        path=path,
        operation=FileOperation.CREATE,
        file_mode=FileMode.STANDARD,
        content_digest=compute_file_sha256(b),
        content_bytes=b,
    )


def test_auto_import_standard_library_symbol() -> None:
    comp_code = (
        "import { Component } from '@angular/core';\n\n"
        "@Component({ selector: 'app-foo', standalone: true })\n"
        "export class FooComponent {\n"
        "  private readonly http = inject(HttpClient);\n"
        "}\n"
    )
    change = _make_file_change("src/app/foo.component.ts", comp_code)
    cs = ChangeSet(
        changeset_id="cs-test",
        plan_id="p-1",
        step_id="s-1",
        base_revision="head",
        worktree_fingerprint="fp",
        changes=(change,),
    )
    diag = StructuredDiagnostic(
        file_path="src/app/foo.component.ts",
        line=4,
        column=27,
        error_code="TS2304",
        category=DiagnosticCategory.MISSING_IMPORT,
        message="Cannot find name 'inject'.",
        symbol="inject",
    )

    strategy = AutoImportRepairStrategy()
    assert strategy.can_repair(diag, cs, ("src/app/foo.component.ts",))

    repaired = strategy.repair(diag, cs, ("src/app/foo.component.ts",))
    assert repaired is not None
    repaired_code = repaired.changes[0].content_bytes.decode("utf-8")
    assert "import { Component, inject } from '@angular/core';" in repaired_code


def test_auto_import_workspace_service_relative_path() -> None:
    svc_code = (
        "import { Injectable } from '@angular/core';\n\n"
        "@Injectable({ providedIn: 'root' })\n"
        "export class UserDataService {}\n"
    )
    comp_code = (
        "import { Component, inject } from '@angular/core';\n\n"
        "@Component({ selector: 'app-user-profile', standalone: true })\n"
        "export class UserProfileComponent {\n"
        "  private readonly svc = inject(UserDataService);\n"
        "}\n"
    )
    c_svc = _make_file_change("src/app/services/user-data-service.service.ts", svc_code)
    c_comp = _make_file_change(
        "src/app/components/user-profile/user-profile.component.ts", comp_code
    )
    cs = ChangeSet(
        changeset_id="cs-test",
        plan_id="p-1",
        step_id="s-1",
        base_revision="head",
        worktree_fingerprint="fp",
        changes=(c_svc, c_comp),
    )
    diag = StructuredDiagnostic(
        file_path="src/app/components/user-profile/user-profile.component.ts",
        line=4,
        column=32,
        error_code="TS2304",
        category=DiagnosticCategory.MISSING_IMPORT,
        message="Cannot find name 'UserDataService'.",
        symbol="UserDataService",
    )

    strategy = AutoImportRepairStrategy()
    scope = (
        "src/app/services/user-data-service.service.ts",
        "src/app/components/user-profile/user-profile.component.ts",
    )
    repaired = strategy.repair(diag, cs, scope)
    target_comp_path = "src/app/components/user-profile/user-profile.component.ts"
    comp_repaired = next(c for c in repaired.changes if c.path == target_comp_path)
    comp_text = comp_repaired.content_bytes.decode("utf-8")
    expected_import = "import { UserDataService } from '../../services/user-data-service.service';"
    assert expected_import in comp_text


def test_signal_call_repair_strategy() -> None:
    code = (
        "export class UserBadgeComponent {\n"
        "  readonly isExpanded = signal<boolean>(false);\n"
        "  toggle() {\n"
        "    if (this.isExpanded) {\n"
        "      console.log('expanded');\n"
        "    }\n"
        "  }\n"
        "}\n"
    )
    change = _make_file_change("src/app/user-badge.component.ts", code)
    cs = ChangeSet(
        changeset_id="cs-test",
        plan_id="p-1",
        step_id="s-1",
        base_revision="head",
        worktree_fingerprint="fp",
        changes=(change,),
    )
    diag = StructuredDiagnostic(
        file_path="src/app/user-badge.component.ts",
        error_code="TS2551",
        category=DiagnosticCategory.SIGNAL_CALL_MISSING,
        message=(
            "Property 'isExpanded' does not exist on type 'UserBadgeComponent'. "
            "Did you mean 'isExpanded()'?"
        ),
        symbol="isExpanded",
    )

    strategy = SignalCallRepairStrategy()
    repaired = strategy.repair(diag, cs, ("src/app/user-badge.component.ts",))
    assert repaired is not None
    text = repaired.changes[0].content_bytes.decode("utf-8")
    assert "if (this.isExpanded()) {" in text


def test_spec_testbed_repair_http_client() -> None:
    spec_code = (
        "import { TestBed } from '@angular/core/testing';\n"
        "import { UserDataService } from './user-data.service';\n\n"
        "describe('UserDataService', () => {\n"
        "  beforeEach(() => {\n"
        "    TestBed.configureTestingModule({\n"
        "      providers: [UserDataService],\n"
        "    });\n"
        "  });\n"
        "});\n"
    )
    change = _make_file_change("src/app/services/user-data.service.spec.ts", spec_code)
    cs = ChangeSet(
        changeset_id="cs-spec",
        plan_id="p-1",
        step_id="s-1",
        base_revision="head",
        worktree_fingerprint="fp",
        changes=(change,),
    )
    diag = StructuredDiagnostic(
        file_path="src/app/services/user-data.service.spec.ts",
        error_code="NullInjectorError",
        category=DiagnosticCategory.SPEC_MOCK_MISSING,
        message="NullInjectorError: No provider for HttpClient!",
        symbol="HttpClient",
    )

    strategy = SpecTestBedRepairStrategy()
    repaired = strategy.repair(diag, cs, ("src/app/services/user-data.service.spec.ts",))
    assert repaired is not None
    text = repaired.changes[0].content_bytes.decode("utf-8")
    assert "import { provideHttpClient } from '@angular/common/http';" in text
    assert "import { provideHttpClientTesting } from '@angular/common/http/testing';" in text
    assert "provideHttpClient(), provideHttpClientTesting()" in text


def test_syntax_lint_repair_missing_semicolon() -> None:
    code = "export const answer = 42\n"
    change = _make_file_change("src/app/constants.ts", code)
    cs = ChangeSet(
        changeset_id="cs-syntax",
        plan_id="p-1",
        step_id="s-1",
        base_revision="head",
        worktree_fingerprint="fp",
        changes=(change,),
    )
    diag = StructuredDiagnostic(
        file_path="src/app/constants.ts",
        line=1,
        error_code="TS1005",
        category=DiagnosticCategory.SYNTAX_ERROR,
        message="error TS1005: ';' expected.",
    )

    strategy = SyntaxLintRepairStrategy()
    repaired = strategy.repair(diag, cs, ("src/app/constants.ts",))
    assert repaired is not None
    text = repaired.changes[0].content_bytes.decode("utf-8")
    assert "export const answer = 42;" in text


def test_bounded_repair_loop_auto_import_integration(tmp_path: Path) -> None:
    # Setup files in staging
    svc_code = (
        "import { Injectable } from '@angular/core';\n\n"
        "@Injectable({ providedIn: 'root' })\n"
        "export class UserDataService {}\n"
    )
    comp_code = (
        "import { Component, inject } from '@angular/core';\n\n"
        "@Component({ selector: 'app-user-profile', standalone: true })\n"
        "export class UserProfileComponent {\n"
        "  private readonly svc = inject(UserDataService);\n"
        "}\n"
    )
    c_svc = _make_file_change("src/app/services/user-data-service.service.ts", svc_code)
    c_comp = _make_file_change(
        "src/app/components/user-profile/user-profile.component.ts", comp_code
    )

    cs = ChangeSet(
        changeset_id="cs-init",
        plan_id="p-1",
        step_id="s-1",
        base_revision="head",
        worktree_fingerprint="fp",
        changes=(c_svc, c_comp),
    )
    cs = cs.model_copy(update={"changeset_digest": compute_changeset_digest(cs)})

    step = MigrationStep(
        step_id="s-1",
        title="Migrate components",
        description="Migrate components",
        expected_files=[
            "src/app/services/user-data-service.service.ts",
            "src/app/components/user-profile/user-profile.component.ts",
        ],
    )
    plan = MigrationPlan(
        plan_id="p-1",
        source_root=str(tmp_path),
        run_id="run-auto-import",
        status=PlanStatus.APPROVED,
        steps=[step],
        policy_digest="pol-digest",
    )

    # Command runner that fails on attempt 1 with TS2304 and passes on attempt 2
    class TscRunner(FakeCommandRunner):
        def __init__(self) -> None:
            super().__init__(default_status=ValidationStatus.PASSED, diagnostics=())
            self.call_count = 0

        def run_command(self, command: ValidationCommand, working_dir: Path) -> ValidationResult:
            self.call_count += 1
            if self.call_count == 1:
                return ValidationResult(
                    command=command.rendered_command,
                    profile=command.profile,
                    status=ValidationStatus.FAILED,
                    exit_code=1,
                    sanitized_output=(
                        "src/app/components/user-profile/user-profile.component.ts(4,32): "
                        "error TS2304: Cannot find name 'UserDataService'."
                    ),
                    diagnostics=(
                        "src/app/components/user-profile/user-profile.component.ts(4,32): "
                        "error TS2304: Cannot find name 'UserDataService'.",
                    ),
                )
            return super().run_command(command, working_dir)

    runner = TscRunner()
    workspace = LocalWorkspaceAdapter()
    engine = DeterministicRepairEngine()
    repair_service = BoundedRepairService(
        command_runner=runner,
        workspace_adapter=workspace,
        validation_service=ValidationService(command_runner=runner),
        repair_engine=engine,
        max_budget=3,
    )

    cmd = ValidationCommand(
        executable="tsc", args=("--noEmit",), profile=ValidationProfile.TYPECHECK
    )

    success, latest_cs, attempts, _ = repair_service.run_repair_loop(
        staging_dir=tmp_path,
        initial_changeset=cs,
        plan=plan,
        step_id="s-1",
        commands=[cmd],
    )

    assert success is True
    assert len(attempts) == 1
    assert attempts[0].status == ValidationStatus.PASSED

    # Verify that the relative import was successfully added
    target_comp_path = "src/app/components/user-profile/user-profile.component.ts"
    comp_res = next(c for c in latest_cs.changes if c.path == target_comp_path)
    comp_text = comp_res.content_bytes.decode("utf-8")
    expected_import = "import { UserDataService } from '../../services/user-data-service.service';"
    assert expected_import in comp_text
