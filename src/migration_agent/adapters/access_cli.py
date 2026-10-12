"""Owner user-management CLI with exact trusted-terminal signing handoff."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from migration_agent.adapters.access_rules import governance_rule_digests
from migration_agent.adapters.access_runtime import ProjectAuthorization, binding_name, root_commit
from migration_agent.adapters.access_signatures import AccessSignatures
from migration_agent.adapters.access_store import SignedAccessStore
from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.adapters.git_directory import ProviderGitDirectory
from migration_agent.adapters.os_identity import current_os_identity
from migration_agent.application.access import AccessService
from migration_agent.config import Settings
from migration_agent.domain.access import (
    AccessActor,
    AccessMember,
    AccessPolicy,
    AccessProof,
    AccessRole,
    GitRepositoryBinding,
    ProjectAccessBinding,
    default_roles,
)
from migration_agent.domain.git_directory import GitDirectoryRequest
from migration_agent.ports.filesystem import InspectionPolicy

Source = Annotated[Path, typer.Argument(help="Read-only source repository.")]
State = Annotated[Path | None, typer.Option("--state-dir")]
Trust = Annotated[Path | None, typer.Option("--trust-root")]


def _settings(state: Path | None, trust: Path | None) -> Settings:
    values: dict[str, object] = {}
    if state is not None:
        values["state_dir"] = state
    if trust is not None:
        values["trust_root"] = trust
    return Settings(**values)  # type: ignore[arg-type]


def _service(source: Path, state: Path | None, trust: Path | None) -> AccessService:
    return ProjectAuthorization(source, _settings(state, trust)).service()


def read_public_key(path: Path) -> str:
    if (
        path.suffix != ".pub"
        or not path.is_file()
        or path.is_symlink()
        or path.stat().st_size > 1024
    ):
        raise ValueError(
            "PUBLIC_KEY_REQUIRED: select a bounded OpenSSH .pub file; never a private key."
        )
    text = path.read_text(encoding="ascii").strip()
    AccessSignatures(path.parent).fingerprint(text)
    return " ".join(text.split()[:2])


def _emit(value: object) -> None:
    from pydantic import BaseModel

    typer.echo(
        value.model_dump_json(indent=2)
        if isinstance(value, BaseModel)
        else json.dumps(value, indent=2)
    )


def _confirm(digest: str) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError("HUMAN_REQUIRED: review and sign in an interactive trusted terminal.")
    if (
        input(f"Type APPROVE {digest} to sign this exact access change: ").strip()
        != f"APPROVE {digest}"
    ):
        raise ValueError("APPROVAL_DECLINED: exact access proposal was not confirmed.")


def _next(policy: AccessPolicy, **updates: object) -> AccessPolicy:
    candidate = policy.model_copy(
        update={"revision": policy.revision + 1, "previous_digest": policy.digest, **updates}
    )
    return AccessPolicy.model_validate_json(candidate.model_dump_json())


def register_access_cli(app: typer.Typer) -> None:
    access = typer.Typer(
        help="Project users, finite roles and signed owner administration.",
        pretty_exceptions_enable=False,
    )
    app.add_typer(access, name="access")

    @access.command("identity")
    def identity() -> None:
        _emit(
            {
                "os_identity": current_os_identity(),
                "message": "Git usernames and --actor labels confer no authority.",
            }
        )

    @access.command("capabilities")
    def capabilities() -> None:
        _emit({"schema_version": 1, "capabilities": AccessService.catalog()})

    @access.command("onboarding")
    def onboarding(
        source: Source,
        principal: Annotated[str, typer.Option("--principal")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        """Print a public onboarding packet; no trust anchors, private keys or session tokens."""
        from migration_agent.application.access_api import AccessAdministration

        service = _service(source, state_dir, trust_root)
        _emit(AccessAdministration(service, ProviderGitDirectory((source,))).onboarding(principal))

    @access.command("bootstrap")
    def bootstrap(
        governance: Annotated[
            Path, typer.Argument(help="Separate committed governance Git repository.")
        ],
        source: Annotated[Path, typer.Option("--source")],
        public_key: Annotated[Path, typer.Option("--owner-key")],
        project_id: Annotated[str, typer.Option("--id")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        settings = _settings(state_dir, trust_root)
        authority = ProjectAuthorization(source, settings)
        binding = ProjectAccessBinding(
            project_id=project_id,
            source_root=str(source.resolve()),
            governance_root=str(governance.resolve()),
            source_root_commit=root_commit(source),
            governance_root_commit=root_commit(governance),
        )
        signatures = AccessSignatures(authority.state)
        store = SignedAccessStore(binding, authority.trust, authority.state, signatures)
        if store.initialized():
            raise ValueError(
                "ACCESS_EXISTS: use an owner-signed proposal to change existing access."
            )
        public = read_public_key(public_key)
        actor = AccessActor(os_identity=current_os_identity(), client="human")
        service = AccessService(store, actor, signatures)
        owner = AccessMember(
            principal_id="owner",
            label="Project owner",
            roles=("owner",),
            status="active",
            os_identity=actor.os_identity,
            public_key=public,
            key_fingerprint=signatures.fingerprint(public),
        )
        policy = AccessPolicy(
            binding=binding,
            revision=1,
            roles=default_roles(),
            members=(owner,),
            owners=(owner.principal_id,),
            rules=governance_rule_digests(governance.resolve()),
        )
        proposal = service.bootstrap(policy)
        paths = [
            validate_repository_path(authority.trust, binding_name(root))
            for root in (source, governance)
        ]
        for path in paths:
            if (
                path.exists()
                and ProjectAccessBinding.model_validate_json(path.read_text()) != binding
            ):
                raise ValueError(
                    "ACCESS_BINDING_CONFLICT: existing external binding cannot be overwritten."
                )
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                with path.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(binding.model_dump_json(indent=2) + "\n")
        _emit(proposal)

    @access.command("status")
    def status(source: Source, state_dir: State = None, trust_root: Trust = None) -> None:
        service = _service(source, state_dir, trust_root)
        _emit(service.explain("project.read"))

    @access.command("show")
    def show(source: Source, state_dir: State = None, trust_root: Trust = None) -> None:
        _emit(_service(source, state_dir, trust_root).view())

    @access.command("explain")
    def explain(
        source: Source, capability: str, state_dir: State = None, trust_root: Trust = None
    ) -> None:
        _emit(_service(source, state_dir, trust_root).explain(capability))

    @access.command("propose")
    def propose(
        source: Source,
        candidate: Annotated[Path, typer.Option("--candidate")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        service = _service(source, state_dir, trust_root)
        service.require("access.propose")
        if candidate.stat().st_size > 2_000_000:
            raise ValueError("ACCESS_TOO_LARGE: candidate exceeds the policy budget.")
        _emit(
            service.propose(
                AccessPolicy.model_validate_json(
                    read_repository_text(
                        candidate.parent,
                        candidate.name,
                        policy=InspectionPolicy(max_text_file_bytes=2_000_000),
                    )
                )
            )
        )

    @access.command("member-set")
    def member_set(
        source: Source,
        principal: Annotated[str, typer.Option("--principal")],
        label: Annotated[str, typer.Option("--label")],
        roles: Annotated[list[str], typer.Option("--role")],
        os_identity: Annotated[str | None, typer.Option("--os-identity")] = None,
        public_key: Annotated[Path | None, typer.Option("--public-key")] = None,
        member_status: Annotated[str, typer.Option("--status")] = "pending",
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        service = _service(source, state_dir, trust_root)
        policy = service.view()
        existing = next((m for m in policy.members if m.principal_id == principal), None)
        data = existing.model_dump() if existing else {}
        data.update(principal_id=principal, label=label, roles=tuple(roles), status=member_status)
        if os_identity is not None:
            data["os_identity"] = os_identity
        if public_key is not None:
            public = read_public_key(public_key)
            data.update(public_key=public, key_fingerprint=service.signatures.fingerprint(public))
        member = AccessMember.model_validate(data)
        members = tuple(
            sorted(
                (*[m for m in policy.members if m.principal_id != principal], member),
                key=lambda m: m.principal_id,
            )
        )
        _emit(service.propose(_next(policy, members=members)))

    @access.command("member-remove")
    def member_remove(
        source: Source, principal: str, state_dir: State = None, trust_root: Trust = None
    ) -> None:
        service = _service(source, state_dir, trust_root)
        policy = service.view()
        _emit(
            service.propose(
                _next(
                    policy, members=tuple(m for m in policy.members if m.principal_id != principal)
                )
            )
        )

    @access.command("role-set")
    def role_set(
        source: Source,
        role_id: Annotated[str, typer.Option("--role-id")],
        label: Annotated[str, typer.Option("--label")],
        capabilities: Annotated[list[str], typer.Option("--capability")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        service = _service(source, state_dir, trust_root)
        policy = service.view()
        role = AccessRole(role_id=role_id, label=label, capabilities=tuple(sorted(capabilities)))
        roles = tuple(
            sorted(
                (*[r for r in policy.roles if r.role_id != role_id], role), key=lambda r: r.role_id
            )
        )
        _emit(service.propose(_next(policy, roles=roles)))

    @access.command("role-remove")
    def role_remove(
        source: Source, role_id: str, state_dir: State = None, trust_root: Trust = None
    ) -> None:
        service = _service(source, state_dir, trust_root)
        policy = service.view()
        _emit(
            service.propose(
                _next(policy, roles=tuple(r for r in policy.roles if r.role_id != role_id))
            )
        )

    @access.command("owners-set")
    def owners_set(
        source: Source,
        owners: Annotated[list[str], typer.Option("--owner")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        service = _service(source, state_dir, trust_root)
        policy = service.view()
        _emit(service.propose(_next(policy, owners=tuple(sorted(owners)))))

    @access.command("review")
    def review(
        source: Source, proposal: str, state_dir: State = None, trust_root: Trust = None
    ) -> None:
        service = _service(source, state_dir, trust_root)
        candidate = service.review(proposal)
        _emit(
            {
                "proposal": candidate.model_dump(mode="json"),
                "signing_digest": candidate.signing_digest,
                "before": service.view().model_dump(mode="json") if candidate.base_digest else None,
            }
        )

    @access.command("approve")
    def approve(
        source: Source,
        proposal: str,
        proofs: Annotated[list[Path] | None, typer.Option("--enrollment-proof")] = None,
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        service = _service(source, state_dir, trust_root)
        candidate = service.review(proposal)
        _emit(candidate)
        _confirm(candidate.signing_digest)
        revision = service.sign(proposal)
        additional = tuple(AccessProof.model_validate_json(p.read_text()) for p in (proofs or ()))
        _emit(
            service.commit(revision.model_copy(update={"proofs": (*revision.proofs, *additional)}))
        )

    @access.command("enroll-sign")
    def enroll(
        source: Source,
        proposal: str,
        public_key: Annotated[Path, typer.Option("--public-key")],
        output: Annotated[Path, typer.Option("--output")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        service = _service(source, state_dir, trust_root)
        state_root = _settings(state_dir, trust_root).resolve_state_dir().resolve()
        if not output.resolve().is_relative_to(state_root) or output.suffix != ".json":
            raise ValueError(
                "UNSAFE_OUTPUT: enrollment proofs must stay in the configured state root."
            )
        candidate = service.store.proposal(proposal)
        public = read_public_key(public_key)
        fingerprint = service.signatures.fingerprint(public)
        member = next(
            (m for m in candidate.candidate.members if m.key_fingerprint == fingerprint), None
        )
        if not member or member.os_identity != current_os_identity():
            raise ValueError(
                "IDENTITY_MISMATCH: enrollment must bind the current OS user and public key."
            )
        _emit(candidate)
        _confirm(candidate.signing_digest)
        proof = AccessProof(
            principal_id=member.principal_id,
            key_fingerprint=fingerprint,
            signature=service.signatures.sign(public, candidate.signing_digest),
        )
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(proof.model_dump_json(indent=2) + "\n")
        _emit(proof)

    @access.command("recover")
    def recover(source: Source, state_dir: State = None, trust_root: Trust = None) -> None:
        service = _service(source, state_dir, trust_root)
        store = service.store
        if not isinstance(store, SignedAccessStore):
            raise ValueError("ACCESS_STORE_INVALID")
        store.recover()
        _emit(service.view())

    @access.command("verify-publication")
    def verify_publication_command(
        source: Source,
        commit: Annotated[str, typer.Option("--commit")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        from migration_agent.adapters.governance_publication import GitPublicationReader
        from migration_agent.application.governance_publication import verify_publication

        service = _service(source, state_dir, trust_root)
        trusted = service.store.read()
        candidate = GitPublicationReader(Path(trusted.binding.governance_root)).read(commit)
        _emit(verify_publication(trusted, candidate, service.signatures))

    @access.command("gate-status")
    def gate_status(source: Source, state_dir: State = None, trust_root: Trust = None) -> None:
        service = _service(source, state_dir, trust_root)
        service.require("access.read")
        _emit(
            {
                "status": "REMOTE_ENFORCEMENT_UNVERIFIED",
                "project_id": service.store.binding.project_id,
                "requirements": [
                    "Protect the authoritative governance branch against direct and force pushes.",
                    "Pin the verifier and external trust outside the proposed commit.",
                    "Require the signed governance check from a trusted runner "
                    "without developer bypass.",
                    "Verify rejection of an unauthorized push on the server "
                    "before claiming enforcement.",
                ],
            }
        )

    @access.command("rules-propose")
    def rules_propose(source: Source, state_dir: State = None, trust_root: Trust = None) -> None:
        service = _service(source, state_dir, trust_root)
        service.require("rules.manage")
        policy = service.view()
        candidate = _next(
            policy, rules=governance_rule_digests(Path(policy.binding.governance_root))
        )
        _emit(service.propose(candidate))

    @access.command("repository-propose")
    def repository_propose(
        source: Source,
        provider: Annotated[str, typer.Option("--provider")],
        host: Annotated[str, typer.Option("--host")],
        repository: Annotated[str, typer.Option("--repository")],
        repository_id: Annotated[str, typer.Option("--repository-id")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        service = _service(source, state_dir, trust_root)
        policy = service.view()
        connection = GitRepositoryBinding.model_validate_json(
            json.dumps(
                {
                    "provider": provider,
                    "host": host,
                    "repository": repository,
                    "repository_id": repository_id,
                }
            )
        )
        _emit(service.propose(_next(policy, git_repository=connection)))

    @access.command("git-import")
    def git_import(
        source: Source,
        provider: Annotated[str, typer.Option("--provider")],
        host: Annotated[str, typer.Option("--host")],
        repository: Annotated[str, typer.Option("--repository")],
        account_ids: Annotated[list[str], typer.Option("--account-id")],
        roles: Annotated[list[str], typer.Option("--role")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        from migration_agent.application.access_api import AccessAdministration, GitImportRequest

        service = _service(source, state_dir, trust_root)
        before = service.view()
        directory = ProviderGitDirectory((source, Path(service.store.binding.governance_root)))
        request = GitImportRequest.model_validate_json(
            json.dumps(
                {
                    "directory": {"provider": provider, "host": host, "repository": repository},
                    "account_ids": account_ids,
                    "roles": roles,
                    "base_digest": before.digest,
                }
            )
        )
        _emit(AccessAdministration(service, directory).import_members(request))

    @access.command("git-members")
    def git_members(
        source: Source,
        provider: Annotated[str, typer.Option("--provider")],
        host: Annotated[str, typer.Option("--host")],
        repository: Annotated[str, typer.Option("--repository")],
        state_dir: State = None,
        trust_root: Trust = None,
    ) -> None:
        service = _service(source, state_dir, trust_root)
        service.require("directory.read")
        request = GitDirectoryRequest.model_validate(
            {"provider": provider, "host": host, "repository": repository}
        )
        from migration_agent.application.access_api import AccessAdministration

        _emit(
            AccessAdministration(
                service,
                ProviderGitDirectory(
                    (
                        source,
                        Path(service.store.binding.governance_root),
                        _settings(state_dir, trust_root).resolve_state_dir(),
                    )
                ),
            ).git_members(request)
        )
