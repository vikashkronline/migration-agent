"""Deterministic constrained settings resolution, independent of host and provider SDKs."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from migration_agent.application.access import AccessService
from migration_agent.domain.access import AccessDenied, AccessRevision, GovernanceFileChange
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.configuration import (
    ConfigurationDiagnostic,
    ConfigurationFieldDescriptor,
    ConfigurationProposal,
    ConfigurationReceipt,
    ConfigurationReview,
    ConfigurationSnapshot,
    ConfigurationView,
    EffectiveField,
    LauncherConfiguration,
    LocalConfiguration,
    LocalConfigurationRequest,
    ProjectConfiguration,
    ProjectConfigurationRequest,
)
from migration_agent.domain.execution import ValidationMode
from migration_agent.ports.access import AuthorizationPort
from migration_agent.ports.configuration import ConfigurationRepositoryPort


def resolve_configuration(
    project: ProjectConfiguration, local: LocalConfiguration, launcher: LauncherConfiguration
) -> ConfigurationSnapshot:
    diagnostics: list[ConfigurationDiagnostic] = []
    fields: list[EffectiveField] = []

    def error(field: str, code: str, message: str) -> None:
        diagnostics.append(
            ConfigurationDiagnostic(
                field=field,
                code=code,
                severity="error",
                message=message,
                action="Review the field against the owner's approved configuration.",
            )
        )

    profiles = {profile.profile_id: profile for profile in project.profiles}
    profile = profiles.get(local.profile_id or project.default_profile or "")
    if local.profile_id and local.profile_id not in profiles:
        error("profile_id", "PROFILE_NOT_ALLOWED", "The selected runtime profile is not approved.")
    if launcher.provider:
        compatible = sorted(
            (
                p
                for p in project.profiles
                if p.provider == launcher.provider
                and (not launcher.model or launcher.model in p.models)
            ),
            key=lambda p: p.profile_id,
        )
        if not profile or profile.provider != launcher.provider:
            profile = compatible[0] if compatible else None
        if not compatible:
            error(
                "provider",
                "PROVIDER_NOT_ALLOWED",
                "The launcher provider/model is outside approved profiles.",
            )
    if not profile:
        diagnostics.append(
            ConfigurationDiagnostic(
                field="profile_id",
                code="PROFILE_SELECTION_REQUIRED" if profiles else "OWNER_SETUP_REQUIRED",
                severity="prerequisite",
                message="No approved runtime profile is selected.",
                action="Select an approved profile in Models; no owner signature is needed."
                if profiles
                else "Ask an owner to review and activate a runtime profile.",
            )
        )
    model = launcher.model or local.model or (profile.default_model if profile else None)
    if profile and model not in profile.models:
        error(
            "model",
            "MODEL_NOT_ALLOWED",
            "The selected model is outside the approved runtime profile.",
        )
    model_origin: Literal["launcher", "local", "project"] = (
        "launcher" if launcher.model else "local" if local.model else "project"
    )
    provider_origin: Literal["launcher", "local", "project"] = (
        "launcher" if launcher.provider else "local" if local.profile_id else "project"
    )
    fields.extend(
        (
            EffectiveField(
                name="provider",
                value=profile.provider if profile else None,
                origin=provider_origin,
                scope="session",
            ),
            EffectiveField(name="model", value=model, origin=model_origin, scope="session"),
            EffectiveField(
                name="profile_id",
                value=profile.profile_id if profile else None,
                origin="local" if local.profile_id else "project",
                scope="session",
            ),
        )
    )
    turns = launcher.max_turns or local.max_turns or project.max_turns
    if turns > project.max_turns or turns < 1:
        error("max_turns", "LIMIT_EXCEEDED", "The requested turn budget exceeds project bounds.")
    fields.append(
        EffectiveField(
            name="max_turns",
            value=turns,
            origin="launcher" if launcher.max_turns else "local" if local.max_turns else "project",
            scope="session",
        )
    )
    files = (
        launcher.max_step_files if launcher.max_step_files is not None else project.max_step_files
    )
    if not 1 <= files <= project.max_step_files:
        error("max_step_files", "LIMIT_EXCEEDED", "The requested task size exceeds project bounds.")
    fields.append(
        EffectiveField(
            name="max_step_files",
            value=files,
            origin="launcher" if launcher.max_step_files is not None else "project",
            scope="project",
        )
    )
    mode = launcher.validation_mode or local.validation_mode or ValidationMode.RESTRICTED
    if mode not in project.allowed_validation_modes:
        error(
            "validation_mode", "MODE_NOT_ALLOWED", "The requested execution mode is not approved."
        )
    fields.append(
        EffectiveField(
            name="validation_mode",
            value=mode.value,
            origin="launcher"
            if launcher.validation_mode
            else "local"
            if local.validation_mode
            else "platform",
            scope="workstation",
        )
    )
    export = (
        launcher.browser_provider_export
        if launcher.browser_provider_export is not None
        else project.browser_provider_export
    )
    if export and not project.browser_provider_export:
        error(
            "browser_provider_export",
            "EXPORT_NOT_ALLOWED",
            "Browser provider export is not approved by the owner.",
        )
    fields.append(
        EffectiveField(
            name="browser_provider_export",
            value=export,
            origin="launcher" if launcher.browser_provider_export is not None else "project",
            scope="project",
        )
    )
    for name in (
        "native_toolchain_root",
        "native_dependencies_root",
        "native_browser_path",
        "browser_validation_plan",
        "validation_image",
        "final_target_root",
        "next_state_dir",
        "next_staging_root",
    ):
        local_value = getattr(local, name)
        value = launcher.paths.get(name, local_value)
        fields.append(
            EffectiveField(
                name=name,
                value=value,
                origin="launcher" if name in launcher.paths else "local",
                scope="workstation",
                update_mode="restart" if name.startswith("next_") else "next_operation",
            )
        )
    return ConfigurationSnapshot(
        project_digest=project.digest,
        local_digest=local.digest,
        fields=tuple(fields),
        diagnostics=tuple(diagnostics),
    )


def configuration_schema() -> tuple[ConfigurationFieldDescriptor, ...]:
    return (
        ConfigurationFieldDescriptor(
            name="profiles",
            label="Approved runtime profiles",
            section="models",
            scope="project",
            kind="profiles",
            help=(
                "Owners approve provider destinations and allowed model "
                "identifiers. No credentials are stored."
            ),
        ),
        ConfigurationFieldDescriptor(
            name="default_profile",
            label="Default runtime profile",
            section="models",
            scope="project",
            kind="text",
            help="Must name an approved profile.",
        ),
        ConfigurationFieldDescriptor(
            name="profile_id",
            label="My runtime profile",
            section="models",
            scope="local",
            kind="text",
            help="Select an owner-approved profile for future model operations.",
        ),
        ConfigurationFieldDescriptor(
            name="model",
            label="My model",
            section="models",
            scope="local",
            kind="text",
            help="Select a model allowed by the approved profile.",
        ),
        ConfigurationFieldDescriptor(
            name="max_turns",
            label="Turn budget",
            section="workflow",
            scope="project",
            kind="number",
            minimum=1,
            maximum=30,
            help="Local/run choices may lower this limit; they cannot raise it.",
        ),
        ConfigurationFieldDescriptor(
            name="max_step_files",
            label="Maximum files per task",
            section="workflow",
            scope="project",
            kind="number",
            minimum=1,
            maximum=100,
            help="A proposal size limit; saving it does not start a workflow.",
        ),
        ConfigurationFieldDescriptor(
            name="allowed_validation_modes",
            label="Allowed execution modes",
            section="environment",
            scope="project",
            kind="modes",
            options=("restricted", "native", "container"),
            help="Execution still requires its separate policy, prerequisites and consent.",
        ),
        ConfigurationFieldDescriptor(
            name="validation_mode",
            label="My execution mode",
            section="environment",
            scope="local",
            kind="mode",
            options=("restricted", "native", "container"),
            help="Native supervision is not filesystem isolation. Saving is not execution consent.",
        ),
        ConfigurationFieldDescriptor(
            name="browser_provider_export",
            label="Allow browser evidence export",
            section="validation",
            scope="project",
            kind="boolean",
            help=(
                "Owner-controlled destination/disclosure setting; fresh consent "
                "and review remain required."
            ),
        ),
        ConfigurationFieldDescriptor(
            name="target_preset_id",
            label="Target architecture preset",
            section="architecture",
            scope="project",
            kind="text",
            help="Must agree with accepted architecture. Edit mappings in the Foundation Wizard.",
        ),
        *(
            ConfigurationFieldDescriptor(
                name=name, label=label, section=section, scope="local", kind="path", help=help_text
            )
            for name, label, section, help_text in (
                (
                    "native_toolchain_root",
                    "External toolchain",
                    "environment",
                    "Installed tools outside source, staging and governance.",
                ),
                (
                    "native_dependencies_root",
                    "External offline dependencies",
                    "environment",
                    "Dependencies must match the project's actual package/lock inputs.",
                ),
                (
                    "native_browser_path",
                    "Installed browser",
                    "validation",
                    "A trusted installed binary; this field does not launch it.",
                ),
                (
                    "browser_validation_plan",
                    "Browser coverage plan",
                    "validation",
                    (
                        "An existing bounded route/state/viewport plan, checked against "
                        "the shared schema."
                    ),
                ),
                (
                    "final_target_root",
                    "Separate migration target directory",
                    "directories",
                    (
                        "Cumulative target for staged, validated and exactly approved publication. "
                        "Source stays read-only; changing target requires new bound artifacts."
                    ),
                ),
                (
                    "next_state_dir",
                    "State directory for next launch",
                    "directories",
                    "Restart required; old history is preserved and never moved or deleted.",
                ),
                (
                    "next_staging_root",
                    "Staging directory for next launch",
                    "directories",
                    "Restart required; existing artifacts retain their original roots.",
                ),
            )
        ),
        ConfigurationFieldDescriptor(
            name="validation_image",
            label="Pinned installed container image",
            section="environment",
            scope="local",
            kind="text",
            help="Require a digest-pinned locally installed image; no automatic download.",
        ),
    )


class ConfigurationService:
    def __init__(
        self,
        repository: ConfigurationRepositoryPort,
        authorization: AuthorizationPort,
        access: AccessService,
    ) -> None:
        self.repository = repository
        self.authorization = authorization
        self.access = access

    def view(self) -> ConfigurationView:
        decision = self.authorization.require("configuration.read")
        if decision.principal_id != self.repository.principal_id:
            raise AccessDenied("CONFIGURATION_PRINCIPAL_CHANGED: open a new bound session.")
        self.authorization.require("project.read", decision.access_digest)
        project, local = self.repository.project(), self.repository.local()
        resolved = resolve_configuration(project, local, self.repository.launcher())
        resolved = resolved.model_copy(
            update={
                "diagnostics": (*resolved.diagnostics, *self.repository.diagnostics(project, local))
            }
        )
        bindings = self.repository.bindings()
        revision = compute_canonical_digest(
            {
                "configuration": resolved,
                "access": decision.access_digest,
                "bindings": bindings,
                "source_revision": self.repository.source_revision(),
                "file_digest": self.repository.file_digest(),
            }
        )
        policy = self.access.store.read()
        return ConfigurationView(
            project_id=self.repository.project_id,
            revision=revision,
            access_digest=decision.access_digest or "",
            principal_id=decision.principal_id or "",
            capabilities=decision.capabilities,
            is_owner=decision.principal_id in policy.owners,
            project=project,
            local=local,
            effective=resolved,
            bindings=bindings,
            field_descriptors=configuration_schema(),
            restart_arguments=(
                "agent",
                "ui",
                bindings["source_root"],
                "--state-dir",
                local.next_state_dir or bindings["state_dir"],
                "--staging-root",
                local.next_staging_root or bindings["staging_root"],
                "--trust-root",
                bindings["trust_root"],
                "--local-config-root",
                bindings["local_config_root"],
            ),
        )

    def propose(self, request: ProjectConfigurationRequest) -> ConfigurationReceipt:
        decision = self.authorization.require("configuration.propose")
        payload = compute_canonical_digest(request)
        with self.repository.guard():
            prior = self.repository.receipt(request.request_id, payload)
            if prior:
                self.authorization.require("configuration.propose", prior.access_digest)
                return prior
            view = self.view()
            if request.expected_revision != view.revision:
                raise ValueError("CONFIGURATION_STALE: refresh configuration before proposing.")
            diagnostics = self.repository.diagnostics(request.configuration, LocalConfiguration())
            if any(d.severity == "error" for d in diagnostics):
                raise ValueError(
                    "CONFIGURATION_INVALID: candidate has blocking checks; inspect diagnostics."
                )
            proposal = ConfigurationProposal(
                proposal_id=uuid.uuid4().hex,
                project_id=view.project_id,
                principal_id=decision.principal_id or "",
                base_access_digest=view.access_digest,
                base_file_digest=self.repository.file_digest(),
                configuration=request.configuration,
                source_revision=self.repository.source_revision(),
                created_at=datetime.now(UTC).isoformat(),
                request_id=request.request_id,
            )
            self.authorization.require("configuration.propose", view.access_digest)
            receipt = ConfigurationReceipt(
                request_id=request.request_id,
                status="PROPOSED",
                revision=view.revision,
                proposal_id=proposal.proposal_id,
                message="Draft saved; active settings are unchanged. Owner review is required.",
                access_digest=view.access_digest,
            )
            self.repository.save_proposal(proposal, receipt, payload)
            return receipt

    def save_local(self, request: LocalConfigurationRequest) -> ConfigurationReceipt:
        decision = self.authorization.require("configuration.local.write")
        payload = compute_canonical_digest(request)
        with self.repository.guard():
            prior = self.repository.receipt(request.request_id, payload)
            if prior:
                self.authorization.require("configuration.local.write", prior.access_digest)
                return prior
            view = self.view()
            recovered = (
                self.repository.local_request_id() == request.request_id
                and view.local == request.configuration
                and self.repository.local_access_digest() == view.access_digest
            )
            if request.expected_revision != view.revision and not recovered:
                raise ValueError("CONFIGURATION_STALE: refresh configuration before saving.")
            before = view.local
            operational = (
                "validation_mode",
                "native_toolchain_root",
                "native_dependencies_root",
                "native_browser_path",
                "browser_validation_plan",
                "validation_image",
                "next_state_dir",
                "next_staging_root",
                "final_target_root",
            )
            if any(
                getattr(before, field) != getattr(request.configuration, field)
                for field in operational
            ):
                self.authorization.require("validation.run", view.access_digest)
                self.authorization.require("execution.consent", view.access_digest)
            if (
                before.profile_id != request.configuration.profile_id
                or before.model != request.configuration.model
            ):
                self.authorization.require("provider.use", view.access_digest)
            resolved = resolve_configuration(
                view.project, request.configuration, self.repository.launcher()
            )
            checks = (
                *resolved.diagnostics,
                *self.repository.diagnostics(view.project, request.configuration),
            )
            if any(d.severity == "error" for d in checks):
                raise ValueError("CONFIGURATION_INVALID: local choices violate active constraints.")
            self.authorization.require("configuration.local.write", decision.access_digest)
            self.repository.save_local(
                request.configuration, request.request_id, view.access_digest
            )
            receipt = ConfigurationReceipt(
                request_id=request.request_id,
                status="SAVED",
                revision=self.view().revision,
                message=(
                    "Local selection saved for the next operation; "
                    "launcher-controlled and root changes require restart."
                ),
                access_digest=view.access_digest,
            )
            self.repository.save_receipt(receipt, payload)
            return receipt

    def review(self, proposal_id: str, *, prepare_signature: bool = False) -> ConfigurationReview:
        self.authorization.require("configuration.read")
        proposal = self.repository.proposal(proposal_id)
        view = self.view()
        stale = (
            proposal.base_access_digest != view.access_digest
            or proposal.base_file_digest != self.repository.file_digest()
            or proposal.source_revision != self.repository.source_revision()
        )
        if stale and prepare_signature:
            raise ValueError(
                "CONFIGURATION_STALE: configuration proposal is based on stale context."
            )
        checks = self.repository.diagnostics(proposal.configuration, LocalConfiguration())
        access_proposal = None
        if prepare_signature:
            self.authorization.require("rules.manage", view.access_digest)
            self.authorization.require("access.commit", view.access_digest)
            if not view.is_owner:
                raise AccessDenied(
                    "OWNER_REQUIRED: project configuration activation requires an owner."
                )
            if any(d.severity == "error" for d in checks):
                raise ValueError(
                    "CONFIGURATION_INVALID: fix blocking checks before owner approval."
                )
            with self.repository.guard():
                access_proposal = self.repository.approved_proposal(proposal_id)
                if access_proposal is None or access_proposal.expires_at <= int(
                    datetime.now(UTC).timestamp()
                ):
                    current = self.access.store.read()
                    content = proposal.configuration.model_dump_json(indent=2) + "\n"
                    rules = {**current.rules, ".agent/config.json": proposal.configuration.digest}
                    candidate = current.model_copy(
                        update={
                            "revision": current.revision + 1,
                            "previous_digest": current.digest,
                            "rules": rules,
                        }
                    )
                    access_proposal = self.access.propose(
                        candidate,
                        (
                            GovernanceFileChange(
                                previous_digest=proposal.base_file_digest, content=content
                            ),
                        ),
                    )
                    self.repository.save_approved_proposal(proposal_id, access_proposal)
        return ConfigurationReview(
            proposal=proposal,
            active=view.project,
            diagnostics=checks,
            impact=(
                *(
                    ("Historical proposal: restore as a new draft before signing.",)
                    if stale
                    else ()
                ),
                (
                    "Activates shared settings only; no workflow, installation or "
                    "model request is started."
                ),
                "The signed access revision invalidates prior pending authority contexts.",
                "Environment/architecture changes require fresh applicable consent and validation.",
                "No source, state, staging or trust directory is moved or rebound.",
            ),
            signing_digest=access_proposal.signing_digest if access_proposal else None,
            access_proposal_id=access_proposal.proposal_id if access_proposal else None,
            review_command=(
                "agent",
                "config",
                "approve",
                view.bindings["source_root"],
                proposal_id,
                "--state-dir",
                view.bindings["state_dir"],
                "--trust-root",
                view.bindings["trust_root"],
                "--staging-root",
                view.bindings["staging_root"],
                "--local-config-root",
                view.bindings["local_config_root"],
            ),
        )

    def activate(self, proposal_id: str, revision: AccessRevision) -> ConfigurationView:
        review = self.review(proposal_id, prepare_signature=True)
        if revision.proposal.proposal_id != review.access_proposal_id:
            raise ValueError(
                "CONFIGURATION_CONFLICT: proof must match the exact prepared proposal."
            )
        self.access.commit(revision)
        return self.view()

    def history(self, offset: int = 0, limit: int = 25) -> tuple[ConfigurationProposal, ...]:
        self.authorization.require("configuration.read")
        if not 0 <= offset <= 10000 or not 1 <= limit <= 100:
            raise ValueError("CONFIGURATION_QUERY_INVALID: use bounded history paging.")
        return self.repository.history(offset, limit)
