"""Standalone CLI access to the same staged validation and human approval core as MCP."""

import json
import uuid
from pathlib import Path
from typing import Annotated

import typer

from migration_agent.adapters.human_review import ConsoleHumanReview
from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.workflow_runtime import WorkflowRuntime
from migration_agent.config import Settings
from migration_agent.domain.host_workflow import OperationStatus
from migration_agent.domain.redaction import RedactionPolicy


def runtime_for(
    root: Path, state: Path | None = None, staging: Path | None = None, trust: Path | None = None
) -> WorkflowRuntime:
    settings = Settings()
    updates: dict[str, object] = {}
    if staging:
        updates["staging_root"] = staging
    if trust:
        updates["trust_root"] = trust
    settings = settings.model_copy(update=updates)
    return WorkflowRuntime(ProjectBinding(root), settings, state)


def selected_step(runtime: WorkflowRuntime, plan_id: str, step_id: str | None) -> str:
    if step_id:
        return step_id
    plan = runtime.store.get_plan(plan_id)
    if plan is None or len(plan.steps) != 1:
        raise ValueError("STEP_REQUIRED: select one existing plan step.")
    return plan.steps[0].step_id


def emit_error(error: Exception) -> None:
    typer.echo(
        json.dumps({"status": "error", "error": RedactionPolicy().redact_text(str(error))[:512]}),
        err=True,
    )


def stage_cli(
    root: Path, plan_id: str, step_id: str | None, state: Path | None, staging: Path | None
) -> None:
    runtime = runtime_for(root, state, staging)
    try:
        selected = selected_step(runtime, plan_id, step_id)
        operation = runtime.dispatch(
            "stage", plan_id, selected, f"cli-{uuid.uuid4().hex}", background=False
        )
        if operation.status != OperationStatus.SUCCEEDED:
            raise ValueError(operation.message)
        record = runtime.store.get_workflow(runtime.binding.project_id, plan_id, selected)
        changeset = runtime.store.get_changeset(record.changeset_id or "")
        typer.echo(
            json.dumps(
                {
                    "status": "ok",
                    "operation_id": operation.operation_id,
                    "plan_id": plan_id,
                    "step_id": selected,
                    "changeset_id": record.changeset_id,
                    "changeset_digest": record.changeset_digest,
                    "staging_path": record.staging_path,
                    "file_count": len(changeset.changes) if changeset else 0,
                }
            )
        )
    finally:
        runtime.close()


def apply_cli(
    root: Path,
    plan_id: str,
    changeset_id: str | None,
    state: Path | None,
    staging: Path | None = None,
) -> None:
    runtime = runtime_for(root, state, staging)
    try:
        if not changeset_id:
            raise ValueError("CHANGESET_REQUIRED: select the exact staged and reviewed artifact.")
        changeset = runtime.store.get_changeset(changeset_id)
        if changeset is None or changeset.plan_id != plan_id:
            raise ValueError("CHANGESET_INVALID: selected artifact does not belong to this plan.")
        operation = runtime.dispatch(
            "apply",
            plan_id,
            changeset.step_id,
            f"cli-{uuid.uuid4().hex}",
            changeset_id,
            background=False,
        )
        if operation.status != OperationStatus.SUCCEEDED:
            raise ValueError(operation.message)
        typer.echo(
            json.dumps(
                {
                    "status": "APPLIED",
                    "operation_id": operation.operation_id,
                    "changeset_id": changeset_id,
                    "applied_paths": [change.path for change in changeset.changes],
                }
            )
        )
    finally:
        runtime.close()


def register_workflow_cli(app: typer.Typer) -> None:
    @app.command("implementation-context")
    def implementation_context(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    ) -> None:
        """Return bounded current source/target context for an authorized generation host."""
        runtime = runtime_for(project_root, state_dir, staging_root)
        lease = None
        try:
            runtime.require_current_configuration()
            lease = runtime.store.acquire_lease(
                runtime.binding.project_id, "context-" + uuid.uuid4().hex
            )
            result = runtime.apply_service.implementation_context(plan_id, step_id, lease)
            typer.echo(result.model_dump_json(indent=2))
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            if lease:
                runtime.store.release_lease(lease)
            runtime.close()

    @app.command("submit-implementation")
    def submit_implementation(
        proposal_file: Path,
        project_root: Annotated[Path, typer.Option("--project-root")],
        request_id: Annotated[str, typer.Option("--request-id")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    ) -> None:
        """Submit bounded generated files; validation and human approval remain separate."""
        from migration_agent.adapters.validation_backend import safe_path
        from migration_agent.domain.host_workflow import ImplementationProposal

        runtime = runtime_for(project_root, state_dir, staging_root)
        try:
            runtime.require_current_configuration()
            path = safe_path(proposal_file)
            if path.is_relative_to(runtime.binding.project_root) or path.is_relative_to(
                runtime.files.write_root
            ):
                raise ValueError(
                    "PROPOSAL_PATH_INVALID: generated proposals belong in external state/artifacts."
                )
            if not path.is_file() or path.stat().st_size > 65536:
                raise ValueError("PROPOSAL_TOO_LARGE: use a bounded regular JSON proposal file.")
            proposal = ImplementationProposal.model_validate_json(path.read_text(encoding="utf-8"))
            result = runtime.apply_service.submit_implementation(request_id, proposal)
            typer.echo(result.model_dump_json(indent=2))
            if result.status != OperationStatus.SUCCEEDED:
                raise typer.Exit(2)
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            runtime.close()

    validation_app = typer.Typer(help="Human native execution consent and backend diagnostics.")
    app.add_typer(validation_app, name="validation")

    @validation_app.command("standards")
    def review_standards(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
        registry_file: Annotated[Path | None, typer.Option("--registry")] = None,
    ) -> None:
        """Report exact staged rule coverage; no command execution or source approval."""
        from migration_agent.adapters.rules import AngularRuleEvaluator, load_rule_registry

        runtime = None
        try:
            registry = load_rule_registry(registry_file)
            runtime = runtime_for(project_root, state_dir, staging_root)
            report = runtime.apply_service.review_standards(
                plan_id, step_id, registry, AngularRuleEvaluator()
            )
            typer.echo(report.model_dump_json())
            if report.status != "PASS":
                raise typer.Exit(1)
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            if runtime is not None:
                runtime.close()

    @validation_app.command("browser-request")
    def browser_request(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    ) -> None:
        """Get mandatory visual-specialist instructions and local captured image paths."""
        runtime = runtime_for(project_root, state_dir, staging_root)
        try:
            record = runtime.store.get_workflow(runtime.binding.project_id, plan_id, step_id)
            typer.echo(runtime.browser_gate.request(record).model_dump_json())
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            runtime.close()

    @validation_app.command("browser-submit")
    def browser_submit(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        review_file: Annotated[Path, typer.Option("--review")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    ) -> None:
        """Record a structured visual review; this does not grant execution or source approval."""
        from migration_agent.adapters.validation_backend import safe_path
        from migration_agent.domain.browser_validation import BrowserReview

        runtime = runtime_for(project_root, state_dir, staging_root)
        try:
            path = safe_path(review_file)
            if (
                not path.is_file()
                or RedactionPolicy.is_sensitive_path(path)
                or path.stat().st_size > 1048576
            ):
                raise ValueError(
                    "BROWSER_REVIEW_INVALID: select a bounded regular non-secret JSON review."
                )
            review = BrowserReview.model_validate_json(path.read_text(encoding="utf-8"))
            operation = runtime.submit_browser_review(plan_id, step_id, uuid.uuid4().hex, review)
            typer.echo(operation.model_dump_json())
            if operation.status != OperationStatus.SUCCEEDED:
                raise typer.Exit(2)
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            runtime.close()

    @validation_app.command("authorize")
    def authorize_native(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
        trust_root: Annotated[Path | None, typer.Option("--trust-root")] = None,
        key_fingerprint: Annotated[str | None, typer.Option("--key-fingerprint")] = None,
        repair_budget: Annotated[int, typer.Option("--repair-budget", min=0, max=10)] = 0,
        profile: Annotated[str, typer.Option("--profile")] = "ALL",
    ) -> None:
        "Review fixed templates and staged code; authorize at most one hour of native execution."
        from migration_agent.adapters.fenced_validation import validation_commands
        from migration_agent.domain.planning import AssuranceLevel

        runtime = runtime_for(project_root, state_dir, staging_root, trust_root)
        lease = None
        try:
            lease = runtime.store.acquire_lease(
                runtime.binding.project_id, uuid.uuid4().hex, ttl=900
            )
            record = runtime.apply_service._record(plan_id, step_id, lease)
            changeset = runtime.apply_service._changeset(record)
            if (
                runtime.files.verify_staging(record.staging_path or "", changeset)
                != record.staging_fingerprint
            ):
                raise ValueError("STAGING_CHANGED: restage a fresh plan before execution consent.")
            from migration_agent.domain.validation import ValidationProfile

            profiles = (
                tuple(ValidationProfile)
                if profile.upper() == "ALL"
                else (ValidationProfile(profile.upper()),)
            )
            commands = tuple(
                command
                for selected in profiles
                for command in validation_commands(runtime.settings.validation_catalog)[selected]
            )
            access = runtime.authorization.require("execution.consent")

            def fence() -> None:
                runtime.authorization.require("execution.consent", access.access_digest)
                runtime.store.renew_lease(lease, 900)

            request = runtime.runner.consent_request(record, commands, repair_budget, fence)
            templates = tuple(command.rendered_command for command in commands)
            if runtime.settings.browser_validation_plan is not None:
                from migration_agent.adapters.browser_config import load_browser_plan

                browser_plan = load_browser_plan(runtime.settings)
                templates += ("browser-v1: " + browser_plan.model_dump_json(),)
                disclosure = runtime.runner.policy().browser_provider_disclosure
                if disclosure is not None:
                    templates += (
                        "External AI disclosure: target/source PNG screenshots, DOM/ARIA facts, "
                        "project UI rules and editable staged code; "
                        + disclosure.model_dump_json(),
                    )
            decision = ConsoleHumanReview(key_fingerprint).confirm_native(
                request,
                runtime.files.review_diff(changeset),
                templates,
            )
            if not decision.confirmed or decision.assurance == AssuranceLevel.MODE_C:
                raise ValueError("APPROVAL_DECLINED: native execution was not authorized.")
            if (
                request.assurance_level == AssuranceLevel.MODE_A
                and decision.assurance != AssuranceLevel.MODE_A
            ):
                raise ValueError("ASSURANCE_REQUIRED: Mode A native consent required.")
            consent = request.model_copy(
                update={
                    "actor": decision.actor,
                    "assurance_level": decision.assurance,
                    "key_fingerprint": decision.key_fingerprint,
                }
            )
            runtime.authorization.require_signature("execution.consent", decision.key_fingerprint)
            runtime.authorization.require("execution.consent", request.access_digest)
            consent = consent.model_copy(update={"signature": runtime.runner.proof.sign(consent)})
            if not runtime.runner.proof.verify(consent, record.root_commit):
                raise ValueError("NATIVE_CONSENT_INVALID: consent signature failed.")
            # Recheck bindings after the operator spends time reviewing.
            runtime.apply_service._record(plan_id, step_id, lease)
            refreshed = runtime.runner.consent_request(record, commands, repair_budget, fence)
            if (
                refreshed.policy_digest,
                refreshed.toolchain,
                refreshed.dependency_digest,
                refreshed.immutable_input_digest,
            ) != (
                consent.policy_digest,
                consent.toolchain,
                consent.dependency_digest,
                consent.immutable_input_digest,
            ):
                raise ValueError("NATIVE_CONSENT_INPUT_CHANGED: preview changed during review.")
            runtime.store.save_native_consent(consent, lease)
            typer.echo(
                json.dumps(
                    {
                        "status": "NATIVE_EXECUTION_AUTHORIZED",
                        "consent_id": consent.consent_id,
                        "expires_at": consent.expires_at.isoformat(),
                    }
                )
            )
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            if lease:
                runtime.store.release_lease(lease)
            runtime.close()

    @validation_app.command("revoke")
    def revoke_native(
        consent_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    ) -> None:
        """Revoke consent immediately, including while a worker holds a validation lease."""
        runtime = runtime_for(project_root, state_dir, staging_root)
        try:
            runtime.store.revoke_native_consent(runtime.binding.project_id, consent_id)
            typer.echo(json.dumps({"status": "NATIVE_EXECUTION_REVOKED", "consent_id": consent_id}))
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            runtime.close()

    @validation_app.command("repair")
    def repair_native(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
        max_repairs: Annotated[int, typer.Option("--max-repairs", min=0, max=10)] = 3,
        provider_guidance: Annotated[bool, typer.Option("--provider-guidance")] = False,
    ) -> None:
        """Resume a saved step's guarded validation/repair; execution consent is still required."""
        from migration_agent.adapters.workspace import LocalWorkspaceAdapter
        from migration_agent.application.validation import BoundedRepairService
        from migration_agent.ports import SpecialistRuntimePort

        runtime = runtime_for(project_root, state_dir, staging_root)
        try:
            plan = runtime.store.get_plan(plan_id)
            if plan is None:
                raise ValueError("PLAN_REQUIRED: select a saved plan.")
            specialist = None
            if provider_guidance:
                from migration_agent.cli import _resolve_runtime

                selected_runtime, _, _ = _resolve_runtime(None, None, False, runtime.settings)
                if isinstance(selected_runtime, SpecialistRuntimePort):
                    specialist = selected_runtime
            service = BoundedRepairService(
                None,
                LocalWorkspaceAdapter(),
                audit_logger=runtime.store,
                checkpoint_store=runtime.store,
                max_budget=max_repairs,
                specialist_runtime=specialist,
            )
            record, attempts = service.prepare_workflow(runtime, plan, step_id, False, max_repairs)
            typer.echo(
                json.dumps(
                    {
                        "state": record.state.value,
                        "changeset_id": record.changeset_id,
                        "validation_digest": record.validation_digest,
                        "repair_attempts": len(attempts),
                    }
                )
            )
            if record.state.value != "VALIDATION_PASSED":
                raise typer.Exit(2)
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            runtime.close()

    @validation_app.command("status")
    def validation_status(
        project_root: Annotated[Path, typer.Option("--project-root")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    ) -> None:
        """Report selected backend and prerequisites without executing repository code."""
        from migration_agent.application.doctor import validation_setup_diagnostics

        runtime = runtime_for(project_root, state_dir, staging_root)
        try:
            typer.echo(
                json.dumps(
                    {
                        "mode": runtime.settings.effective_validation_mode.value,
                        "setup": validation_setup_diagnostics(runtime.settings).model_dump(
                            mode="json"
                        ),
                        "consents": [
                            {
                                "plan_id": record.plan_id,
                                "step_id": record.step_id,
                                "status": runtime.runner.consent_status(record),
                            }
                            for record in runtime.store.list_workflows(runtime.binding.project_id)
                        ],
                    }
                )
            )
        finally:
            runtime.close()

    @app.command("submit-repair")
    def submit_repair(
        proposal_file: Path,
        project_root: Annotated[Path, typer.Option("--project-root")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
        request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    ) -> None:
        """Submit a bounded typed repair and invalidate prior validation/approval."""
        from migration_agent.adapters.filesystem import read_repository_text
        from migration_agent.domain.host_workflow import RepairProposal

        runtime = runtime_for(project_root, state_dir, staging_root)
        try:
            if proposal_file.resolve().is_relative_to(runtime.binding.project_root):
                raise ValueError("SOURCE_READ_ONLY: repair proposals belong outside the source.")
            if proposal_file.stat().st_size > 65536:
                raise ValueError("PROPOSAL_TOO_LARGE: repair proposal budget exceeded.")
            proposal = RepairProposal.model_validate_json(
                read_repository_text(proposal_file.parent, proposal_file.name)
            )
            operation = runtime.proposals.submit_repair(request_id or uuid.uuid4().hex, proposal)
            typer.echo(operation.model_dump_json(indent=2))
            if operation.status != OperationStatus.SUCCEEDED:
                raise typer.Exit(2)
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            runtime.close()

    @app.command("recover")
    def recover(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    ) -> None:
        """Reconcile manually restored base or complete target; never replay source writes."""
        from migration_agent.adapters.recovery_probe import LocalRecoveryProbe
        from migration_agent.domain.host_workflow import Lifecycle

        runtime = runtime_for(project_root, state_dir, staging_root)
        lease = None
        try:
            with runtime.lock.acquire(runtime.files.lock_identity(runtime.binding.project_id)):
                lease = runtime.store.acquire_lease(runtime.binding.project_id, uuid.uuid4().hex)
                record = runtime.store.get_workflow(runtime.binding.project_id, plan_id, step_id)
                if record.state != Lifecycle.RECOVERY_REQUIRED:
                    raise ValueError(
                        "RECOVERY_STATE_INVALID: explicit recovery checkpoint required."
                    )
                changeset = runtime.store.get_changeset(record.changeset_id or "")
                if changeset is None:
                    raise ValueError("RECOVERY_REQUIRED: ChangeSet unavailable; inspect backups.")
                result = LocalRecoveryProbe(
                    runtime.binding.project_root, runtime.settings.final_target_root
                ).classify(record, changeset)
                if result == "ambiguous":
                    raise ValueError(
                        "RECOVERY_REQUIRED: manually restore base from verified backups."
                    )
                if result == "base" and (
                    not runtime.proposals.evidence.repository_state().clean
                    or runtime.proposals.evidence.repository_state().fingerprint
                    != record.worktree_fingerprint
                ):
                    raise ValueError("RECOVERY_REQUIRED: complete clean base restoration required.")
                record = runtime.store.save_workflow(
                    record.model_copy(
                        update={
                            "state": Lifecycle.APPLY_COMPLETED
                            if result == "target"
                            else Lifecycle.BASE_CHANGED,
                            "approval_nonce": None,
                            "recovery_note": f"Explicit recovery verified {result}",
                        }
                    ),
                    lease,
                )
                typer.echo(json.dumps({"status": record.state.value, "plan_id": plan_id}))
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
        finally:
            if lease:
                runtime.store.release_lease(lease)
            runtime.close()

    @app.command("review")
    def review(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
    ) -> None:
        """Display the exact validated ChangeSet review without minting approval."""
        try:
            runtime = runtime_for(project_root, state_dir, staging_root)
            lease = runtime.store.acquire_lease(
                runtime.binding.project_id, f"review-{uuid.uuid4().hex}"
            )
            try:
                record = runtime.store.get_workflow(runtime.binding.project_id, plan_id, step_id)
                payload = runtime.apply_service.request_review(
                    plan_id, step_id, record.changeset_id or "", lease
                )
                typer.echo(payload.model_dump_json(indent=2))
            finally:
                runtime.store.release_lease(lease)
                runtime.close()
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error

    @app.command("approve")
    def approve(
        step_id: str,
        project_root: Annotated[Path, typer.Option("--project-root")],
        plan_id: Annotated[str, typer.Option("--plan")],
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
        trust_root: Annotated[Path | None, typer.Option("--trust-root")] = None,
        key_fingerprint: Annotated[str | None, typer.Option("--key-fingerprint")] = None,
    ) -> None:
        """Human-only exact ChangeSet approval; no --yes, token, or automatic signing option."""
        try:
            runtime = runtime_for(project_root, state_dir, staging_root, trust_root)
            try:
                record = runtime.apply_service.approve(
                    plan_id, step_id, ConsoleHumanReview(key_fingerprint)
                )
                typer.echo(
                    json.dumps(
                        {
                            "status": "APPROVAL_RECORDED",
                            "changeset_id": record.changeset_id,
                            "changeset_digest": record.changeset_digest,
                            "expires_at": record.expires_at.isoformat(),
                        }
                    )
                )
            finally:
                runtime.close()
        except (ValueError, OSError) as error:
            emit_error(error)
            raise typer.Exit(2) from error
