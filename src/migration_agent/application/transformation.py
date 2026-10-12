"""Application service orchestrating staging workspaces and ADR-8 controlled apply protocol."""

import contextlib
import difflib
import json
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path

from migration_agent.domain import (
    ApplyResult,
    ApplyStatus,
    ChangeSet,
    FileChange,
    FileMode,
    FileOperation,
    MigrationPlan,
    PlanStatus,
    RedactionPolicy,
    SourceComponentBundle,
    SourceServiceBundle,
    compute_changeset_digest,
    compute_file_sha256,
    compute_worktree_fingerprint,
    verify_approval,
)
from migration_agent.domain.stack import StackRecommendationDraft
from migration_agent.ports import (
    AuditEvent,
    AuditLogPort,
    CheckpointPort,
    ComponentExtractorPort,
    ComponentRendererPort,
    FilesystemInspectorPort,
    FoundationTransformationPort,
    FrameworkAdapterRegistry,
    InspectionPolicy,
    OperationalCheckpoint,
    ServiceExtractorPort,
    ServiceRendererPort,
    WorkspacePort,
)
from migration_agent.ports.apply_approval import SourceApplyPort


def _to_kebab_case(value: str) -> str:
    """Convert PascalCase or camelCase or snake_case to kebab-case."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    s = s.replace("_", "-").strip("-").lower()
    return re.sub(r"-+", "-", s)


class TransformationService:
    """Manages ChangeSet preview, staging materialization, and controlled patch application."""

    def __init__(
        self,
        workspace_adapter: WorkspacePort,
        extractor: ComponentExtractorPort | None = None,
        renderer: ComponentRendererPort | None = None,
        registry: FrameworkAdapterRegistry | None = None,
        filesystem: FilesystemInspectorPort | None = None,
        audit_logger: AuditLogPort | None = None,
        checkpoint_store: CheckpointPort | None = None,
        service_extractor: ServiceExtractorPort | None = None,
        service_renderer: ServiceRendererPort | None = None,
        max_preview_files: int | None = None,
        max_preview_bytes: int | None = None,
        apply_gateway: Callable[[Path], SourceApplyPort] | None = None,
        foundation_adapter: FoundationTransformationPort | None = None,
    ) -> None:
        self.workspace_adapter = workspace_adapter
        self.extractor = extractor
        self.renderer = renderer
        self.registry = registry
        self.filesystem = filesystem
        self.audit_logger = audit_logger
        self.checkpoint_store = checkpoint_store
        self.service_extractor = service_extractor
        self.service_renderer = service_renderer
        self.max_preview_files = max_preview_files
        self.max_preview_bytes = max_preview_bytes
        self.apply_gateway = apply_gateway
        self.foundation_adapter = foundation_adapter

    def _resolve_pair(self, root: Path) -> tuple[ComponentExtractorPort, ComponentRendererPort]:
        """Resolve extractor and renderer via explicit injection or capability negotiation."""
        if self.extractor is not None and self.renderer is not None:
            return self.extractor, self.renderer

        if self.registry is not None and self.filesystem is not None:
            snapshot = self.filesystem.inspect(root, InspectionPolicy())
            fingerprints = self.registry.detect(snapshot)
            if not fingerprints:
                raise ValueError(f"No recognizable framework detected in source root '{root}'.")
            source_framework = fingerprints[0].framework_id
            target_framework = "angular"
            negotiation = self.registry.negotiate_pair(source_framework, target_framework)
            if not negotiation.supported:
                raise ValueError(
                    f"Capability negotiation failed between '{source_framework}' "
                    f"and '{target_framework}': {negotiation.reason}"
                )
            src_adapter = self.registry.get_adapter(source_framework)
            tgt_adapter = self.registry.get_adapter(target_framework)
            if src_adapter is not None and tgt_adapter is not None:
                ext = src_adapter.get_extractor()
                rnd = tgt_adapter.get_renderer()
                if hasattr(src_adapter, "get_service_extractor"):
                    self.service_extractor = src_adapter.get_service_extractor()
                if hasattr(tgt_adapter, "get_service_renderer"):
                    self.service_renderer = tgt_adapter.get_service_renderer()
                if ext is not None and rnd is not None:
                    return ext, rnd

        raise ValueError(
            "TransformationService requires either explicit extractor/renderer "
            "or a FrameworkAdapterRegistry with FilesystemInspectorPort."
        )

    def preview(
        self,
        source_root: Path | str,
        plan: MigrationPlan,
        step_id: str | None = None,
        draft: StackRecommendationDraft | None = None,
    ) -> tuple[ChangeSet, str]:
        """Generate proposed ChangeSet and unified diff without modifying staging or source."""
        root = Path(source_root).resolve()
        if Path(plan.source_root).resolve() != root:
            raise ValueError("PROJECT_MISMATCH: plan does not belong to the source repository.")
        ids = [step.step_id for step in plan.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("INVALID_STEP_ID: plan contains duplicate steps.")
        if step_id is not None and (not step_id.strip() or step_id not in ids):
            raise ValueError("INVALID_STEP_ID: requested step is not in the plan.")
        if RedactionPolicy().contains_secret(plan.model_dump_json()):
            raise ValueError("SECRET_CONTENT_REJECTED: credential-shaped plan content.")
        fingerprint = compute_worktree_fingerprint(root)

        changes: list[FileChange] = []
        diff_chunks: list[str] = []
        generated_bytes = 0

        def add_change(change: FileChange) -> None:
            nonlocal generated_bytes
            content = change.content_bytes or b""
            if RedactionPolicy().contains_secret(content.decode("utf-8")):
                raise ValueError("SECRET_CONTENT_REJECTED: generated content contains credentials.")
            generated_bytes += len(content)
            if self.max_preview_files is not None and len(changes) >= self.max_preview_files:
                raise ValueError("PREVIEW_TOO_LARGE: request a smaller step scope.")
            if self.max_preview_bytes is not None and generated_bytes > self.max_preview_bytes:
                raise ValueError("PREVIEW_TOO_LARGE: generated content exceeds the byte limit.")
            if any(previous.path.casefold() == change.path.casefold() for previous in changes):
                raise ValueError("INVALID_SCOPE: generated paths collide.")
            changes.append(change)

        target_step_id = step_id or (plan.steps[0].step_id if plan.steps else "step-001")
        target_step = None
        if step_id is not None and plan.steps:
            target_step = next((s for s in plan.steps if s.step_id == step_id), None)

        is_foundation = (
            draft is not None
            or (target_step is not None and target_step.scope == "foundation")
            or (step_id is None and plan.steps and all(s.scope == "foundation" for s in plan.steps))
        )

        if is_foundation:
            if self.foundation_adapter is None:
                raise ValueError(
                    "UNSUPPORTED_PREVIEW: Foundation transformation adapter is required "
                    "for foundation scope."
                )
            project_name = root.name
            pkg_file = root / "package.json"
            if pkg_file.is_file():
                with contextlib.suppress(Exception):
                    pkg_raw = json.loads(pkg_file.read_text(encoding="utf-8"))
                    if isinstance(pkg_raw, dict) and "name" in pkg_raw:
                        project_name = str(pkg_raw["name"])

            foundation_files = self.foundation_adapter.render_foundation_files(
                project_name, draft=draft
            )
            for rel_path, content_str in sorted(foundation_files.items()):
                content_bytes = content_str.encode("utf-8")
                digest = compute_file_sha256(content_bytes)
                existing_file = root / rel_path
                orig_lines: list[str] = []
                operation = FileOperation.CREATE
                if existing_file.is_file():
                    try:
                        orig_lines = existing_file.read_text(encoding="utf-8").splitlines(
                            keepends=True
                        )
                        operation = FileOperation.MODIFY
                    except Exception:
                        orig_lines = []

                change = FileChange(
                    path=rel_path,
                    operation=operation,
                    file_mode=FileMode.STANDARD,
                    content_digest=digest,
                    content_bytes=content_bytes,
                )
                add_change(change)
                new_lines = content_str.splitlines(keepends=True)
                diff = difflib.unified_diff(
                    orig_lines,
                    new_lines,
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                )
                diff_chunks.append("".join(diff))

            changeset_id = f"cs-{uuid.uuid4().hex[:8]}"
            preliminary_changeset = ChangeSet(
                changeset_id=changeset_id,
                plan_id=plan.plan_id,
                step_id=target_step_id,
                base_revision="head-revision",
                worktree_fingerprint=fingerprint,
                changes=tuple(changes),
            )
            final_changeset = preliminary_changeset.model_copy(
                update={"changeset_digest": compute_changeset_digest(preliminary_changeset)}
            )
            if self.checkpoint_store:
                self.checkpoint_store.save_changeset(final_changeset)
            return final_changeset, "\n".join(diff_chunks)

        if target_step and "package.json" in target_step.expected_files:
            raise ValueError(
                "FOUNDATION_SCOPE_REQUIRED: dependency/configuration changes use "
                "the accepted foundation contract."
            )
        extractor, renderer = self._resolve_pair(root)
        bundles = extractor.discover_components(root)

        def matches_step_component(
            b: SourceComponentBundle, comp_kebab: str, inter_name: str
        ) -> bool:
            if target_step is None:
                return True
            if not target_step.expected_files and not target_step.title:
                return True
            expected = [f.lower() for f in target_step.expected_files]
            if expected:
                namespace = b.component_namespace or comp_kebab
                output_paths = renderer.output_paths(b.component_name, namespace)
                return bool(
                    set(expected) & {path.lower() for path in (*b.source_files, *output_paths)}
                )
            title_lower = target_step.title.lower()
            desc_lower = target_step.description.lower()
            return (
                comp_kebab in title_lower
                or b.component_name.lower() in title_lower
                or inter_name.lower() in title_lower
                or b.component_name.lower() in desc_lower
            )

        for bundle in bundles:
            if not matches_step_component(
                bundle, _to_kebab_case(bundle.component_name), bundle.component_name
            ):
                continue
            intermediate = extractor.extract(
                bundle.component_source,
                bundle.template_source,
                bundle.style_source,
                component_name=bundle.component_name,
            )
            kebab_name = _to_kebab_case(intermediate.name or bundle.component_name)
            if not matches_step_component(bundle, kebab_name, intermediate.name):
                continue

            namespace = bundle.component_namespace or kebab_name
            if not all(re.fullmatch(r"[a-zA-Z0-9_-]+", part) for part in namespace.split("/")):
                raise ValueError("INVALID_SCOPE: unsupported component namespace.")
            intermediate = intermediate.model_copy(
                update={
                    "tag_name": "app-" + namespace.replace("/", "-"),
                    "metadata": {
                        **intermediate.metadata,
                        "service_import_root": "../" * (len(namespace.split("/")) + 1) + "services",
                    },
                }
            )

            ts_code = renderer.render_component_ts(intermediate)
            html_code = renderer.render_template_html(intermediate)
            spec_code = renderer.render_spec_ts(intermediate)
            scss_code = renderer.render_style_scss(intermediate)

            generated_files = zip(
                renderer.output_paths(intermediate.name, namespace),
                (code.encode("utf-8") for code in (ts_code, html_code, scss_code, spec_code)),
                strict=True,
            )

            for rel_path, content_bytes in generated_files:
                digest = compute_file_sha256(content_bytes)
                change = FileChange(
                    path=rel_path,
                    operation=FileOperation.CREATE,
                    file_mode=FileMode.STANDARD,
                    content_digest=digest,
                    content_bytes=content_bytes,
                )
                add_change(change)

                new_lines = content_bytes.decode("utf-8", errors="replace").splitlines(
                    keepends=True
                )
                diff = difflib.unified_diff(
                    [],
                    new_lines,
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                )
                diff_chunks.append("".join(diff))

        def matches_step_service(sb: SourceServiceBundle, svc_kebab: str, inter_name: str) -> bool:
            if target_step is None:
                return True
            if not target_step.expected_files and not target_step.title:
                return True
            expected = [f.lower() for f in target_step.expected_files]
            if expected:
                output_paths = (
                    self.service_renderer.output_paths(sb.service_name)
                    if self.service_renderer
                    else ()
                )
                return bool(
                    set(expected) & {path.lower() for path in (*sb.source_files, *output_paths)}
                )
            title_lower = target_step.title.lower()
            desc_lower = target_step.description.lower()
            return (
                svc_kebab in title_lower
                or sb.service_name.lower() in title_lower
                or inter_name.lower() in title_lower
                or sb.service_name.lower() in desc_lower
            )

        if self.service_extractor is not None and self.service_renderer is not None:
            service_bundles = self.service_extractor.discover_services(root)
            for s_bundle in service_bundles:
                inter_svc = self.service_extractor.extract_service(s_bundle.service_source)
                kebab_svc = _to_kebab_case(inter_svc.name or s_bundle.service_name)
                if not matches_step_service(s_bundle, kebab_svc, inter_svc.name):
                    continue
                svc_ts = self.service_renderer.render_service_ts(inter_svc)
                svc_spec = self.service_renderer.render_spec_ts(inter_svc)
                svc_files = zip(
                    self.service_renderer.output_paths(inter_svc.name),
                    (svc_ts.encode("utf-8"), svc_spec.encode("utf-8")),
                    strict=True,
                )
                for rel_path, content_bytes in svc_files:
                    digest = compute_file_sha256(content_bytes)
                    change = FileChange(
                        path=rel_path,
                        operation=FileOperation.CREATE,
                        file_mode=FileMode.STANDARD,
                        content_digest=digest,
                        content_bytes=content_bytes,
                    )
                    add_change(change)
                    new_lines = content_bytes.decode("utf-8", errors="replace").splitlines(
                        keepends=True
                    )
                    diff = difflib.unified_diff(
                        [],
                        new_lines,
                        fromfile=f"a/{rel_path}",
                        tofile=f"b/{rel_path}",
                    )
                    diff_chunks.append("".join(diff))

        changeset_id = f"cs-{uuid.uuid4().hex[:8]}"

        if not changes:
            raise ValueError("UNSUPPORTED_PREVIEW: no eligible changes for the requested scope.")

        preliminary_changeset = ChangeSet(
            changeset_id=changeset_id,
            plan_id=plan.plan_id,
            step_id=target_step_id,
            base_revision="head-revision",
            worktree_fingerprint=fingerprint,
            changes=tuple(changes),
        )

        final_changeset = preliminary_changeset.model_copy(
            update={"changeset_digest": compute_changeset_digest(preliminary_changeset)}
        )

        if self.checkpoint_store:
            self.checkpoint_store.save_changeset(final_changeset)

        return final_changeset, "\n".join(diff_chunks)

    def stage(
        self,
        staging_root: Path | str,
        run_id: str,
        source_root: Path | str,
        plan: MigrationPlan,
        step_id: str | None = None,
        draft: StackRecommendationDraft | None = None,
    ) -> tuple[Path, ChangeSet]:
        """Materialize proposed ChangeSet in an isolated staging workspace."""
        if plan.status != PlanStatus.APPROVED or not verify_approval(plan):
            raise ValueError(
                f"Cannot stage unapproved plan '{plan.plan_id}' (status: {plan.status.value})."
            )

        changeset, _ = self.preview(source_root, plan, step_id=step_id, draft=draft)

        staging_dir = self.workspace_adapter.create_staging(
            run_id=run_id,
            source_root=Path(source_root),
            staging_root=Path(staging_root),
        )

        self.workspace_adapter.apply_changeset(staging_dir, changeset)

        if self.checkpoint_store:
            self.checkpoint_store.save_changeset(changeset)
            self.checkpoint_store.save_checkpoint(
                OperationalCheckpoint(
                    checkpoint_id=f"chk-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    checkpoint_type="CHANGESET_STAGED",
                    step_id=changeset.step_id,
                    state_data={
                        "changeset_id": changeset.changeset_id,
                        "plan_id": plan.plan_id,
                        "staging_path": str(staging_dir),
                    },
                )
            )

        if self.audit_logger:
            self.audit_logger.record_event(
                AuditEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    run_id=run_id,
                    event_type="CHANGESET_STAGED",
                    actor="agent",
                    payload={
                        "changeset_id": changeset.changeset_id,
                        "plan_id": plan.plan_id,
                        "staging_path": str(staging_dir),
                        "file_count": len(changeset.changes),
                        "changeset_digest": changeset.changeset_digest,
                    },
                )
            )

        return staging_dir, changeset

    def apply(
        self,
        source_root: Path | str,
        changeset: ChangeSet,
        plan: MigrationPlan,
        actor: str,
        backup_root: Path | str | None = None,
        simulate_apply_failure: bool = False,
        simulate_rollback_failure: bool = False,
        target_root: Path | str | None = None,
    ) -> ApplyResult:
        """Route every source or target mutation through the shared exact approval gate."""
        destination = Path(target_root or source_root).resolve()
        if target_root is not None:
            src = Path(source_root).resolve()
            if (
                destination == src
                or str(destination).startswith(str(src) + os.sep)
                or str(src).startswith(str(destination) + os.sep)
            ):
                raise ValueError(
                    "OVERLAPPING_ROOTS_REJECTED: target_root and source_root must be distinct."
                )
        if self.apply_gateway is None:
            return ApplyResult(
                status=ApplyStatus.BASE_CHANGED,
                changeset_id=changeset.changeset_id,
                diagnostics=("APPROVAL_REQUIRED: shared apply gate and human review required.",),
            )
        if simulate_apply_failure or simulate_rollback_failure:
            raise ValueError("TEST_FLAG_REJECTED: failure injection is not a source apply option.")
        return self.apply_gateway(destination).apply(
            plan.plan_id, changeset.step_id, changeset.changeset_id
        )
