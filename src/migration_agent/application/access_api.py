"""Typed user-management read models and proposals shared by CLI and Control Center."""

from typing import Literal

from pydantic import Field

from migration_agent.application.access import AccessService
from migration_agent.domain.access import (
    AccessMember,
    AccessModel,
    AccessPolicy,
    AccessProposal,
    AccessRole,
    GitRepositoryBinding,
)
from migration_agent.domain.git_directory import GitDirectoryRequest, GitDirectoryResult
from migration_agent.ports.git_directory import GitDirectoryPort


class AccessMutation(AccessModel):
    kind: Literal[
        "member.set", "member.remove", "role.set", "role.remove", "owners.set", "repository.set"
    ]
    member: AccessMember | None = None
    role: AccessRole | None = None
    entity_id: str | None = Field(default=None, min_length=1, max_length=64)
    owners: tuple[str, ...] | None = Field(default=None, max_length=32)
    repository: GitRepositoryBinding | None = None


class AccessChangeRequest(AccessModel):
    base_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    mutations: tuple[AccessMutation, ...] = Field(min_length=1, max_length=100)


class GitImportRequest(AccessModel):
    directory: GitDirectoryRequest
    account_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    roles: tuple[str, ...] = Field(min_length=1, max_length=128)
    base_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AccessReviewView(AccessModel):
    proposal: AccessProposal
    before: AccessPolicy | None
    signing_digest: str
    review_command: tuple[str, ...] = ()
    approval_channel: Literal["trusted-terminal"] = "trusted-terminal"
    message: str = (
        "Review this exact proposal in a trusted terminal with agent access approve. "
        "The browser cannot sign owner changes."
    )


class OnboardingPacket(AccessModel):
    schema_version: Literal[1] = 1
    project_id: str
    access_digest: str
    source_root: str
    source_root_commit: str = Field(description="Source repository genesis; not the current HEAD.")
    governance_root: str
    git_repository: GitRepositoryBinding | None
    principal_id: str
    status: str
    roles: tuple[str, ...]
    assigned_capabilities: tuple[str, ...]
    key_fingerprint: str | None
    steps: tuple[str, ...]


class AccessAdministration:
    def onboarding(self, principal_id: str) -> OnboardingPacket:
        self.service.require("project.read")
        policy = self.service.view()
        member = next(
            (member for member in policy.members if member.principal_id == principal_id), None
        )
        if member is None:
            raise ValueError("MEMBER_NOT_FOUND: select an existing agent principal.")
        roles = {role.role_id: role for role in policy.roles}
        return OnboardingPacket(
            project_id=policy.binding.project_id,
            access_digest=policy.digest,
            source_root=policy.binding.source_root,
            source_root_commit=policy.binding.source_root_commit,
            governance_root=policy.binding.governance_root,
            git_repository=policy.git_repository,
            principal_id=member.principal_id,
            status=member.status,
            roles=member.roles,
            assigned_capabilities=tuple(
                sorted(
                    {capability for role in member.roles for capability in roles[role].capabilities}
                )
            ),
            key_fingerprint=member.key_fingerprint,
            steps=(
                "Install the approved agent version and run agent doctor in your "
                "managed OS session.",
                "Run agent access identity; the owner binds that identity and exp"
                "licitly activates your membership.",
                "For team execution/review, enroll your public key with possessio"
                "n proof. Private keys remain with you.",
                "Provision source, governance, state, staging, target and externa"
                "l trust through the trusted administrator; do not copy another u"
                "ser's anchors, state or session token.",
                "Launch your own local CLI/GUI/MCP session under your enrolled id"
                "entity using the agreed roots and installed toolchain.",
                "Check effective permissions and configuration; inspect accepted "
                "ADRs, actual task IDs, dependencies and business acceptance crit"
                "eria.",
                "Use the published foundation. Generate via supported transforms "
                "or a source-grounded implementation proposal; stage and validate"
                " the exact target artifact.",
                "An operator provides Mode A native consent for independent devel"
                "oper validation. A reviewer signs exact approval; an operator pu"
                "blishes to the target.",
                "Git access does not grant agent roles. Offboarding needs both up"
                "stream Git removal and signed agent suspension/removal.",
                "Role grants shown here are declarations; effective rights also d"
                "epend on active enrollment, expiry and trusted client ceilings.",
            ),
        )

    def __init__(
        self,
        service: AccessService,
        directory: GitDirectoryPort,
        review_options: tuple[str, ...] = (),
    ) -> None:
        self.service = service
        self.directory = directory
        self.review_options = review_options

    def propose(self, request: AccessChangeRequest) -> AccessReviewView:
        self.service.require("access.propose", request.base_digest)
        before = self.service.view()
        members = {m.principal_id: m for m in before.members}
        roles = {r.role_id: r for r in before.roles}
        owners = before.owners
        repository = before.git_repository
        for change in request.mutations:
            supplied = {
                name
                for name in ("member", "role", "entity_id", "owners", "repository")
                if getattr(change, name) is not None
            }
            expected = (
                {"member"}
                if change.kind == "member.set"
                else {"role"}
                if change.kind == "role.set"
                else {"owners"}
                if change.kind == "owners.set"
                else {"repository"}
                if change.kind == "repository.set"
                else {"entity_id"}
            )
            if supplied != expected:
                raise ValueError(
                    "ACCESS_MUTATION_INVALID: supply exactly the fields for this mutation."
                )
            if change.kind == "member.set" and change.member:
                members[change.member.principal_id] = change.member
            elif change.kind == "role.set" and change.role:
                roles[change.role.role_id] = change.role
            elif change.kind == "member.remove":
                if change.entity_id not in members:
                    raise ValueError("ACCESS_MEMBER_NOT_FOUND")
                del members[change.entity_id]
            elif change.kind == "role.remove":
                if change.entity_id not in roles:
                    raise ValueError("ACCESS_ROLE_NOT_FOUND")
                del roles[change.entity_id]
            elif change.kind == "owners.set" and change.owners is not None:
                owners = change.owners
            elif change.kind == "repository.set" and change.repository:
                repository = change.repository
        candidate = before.model_copy(
            update={
                "revision": before.revision + 1,
                "previous_digest": before.digest,
                "members": tuple(members[key] for key in sorted(members)),
                "roles": tuple(roles[key] for key in sorted(roles)),
                "owners": owners,
                "git_repository": repository,
            }
        )
        proposal = self.service.propose(candidate)
        return AccessReviewView(
            proposal=proposal,
            before=before,
            signing_digest=proposal.signing_digest,
            review_command=(
                "agent",
                "access",
                "approve",
                proposal.candidate.binding.source_root,
                proposal.proposal_id,
                *self.review_options,
            ),
        )

    def git_members(self, request: GitDirectoryRequest) -> GitDirectoryResult:
        self.service.require("directory.read")
        binding = self.service.view().git_repository
        if binding is None:
            raise ValueError(
                "GIT_REPOSITORY_BIND_REQUIRED: approve the repository connection first."
            )
        if (request.provider, request.host, request.repository) != (
            binding.provider,
            binding.host,
            binding.repository,
        ):
            raise ValueError("GIT_REPOSITORY_MISMATCH: select the signed governance connection.")
        result = self.directory.members(request)
        if result.repository_id != binding.repository_id:
            raise ValueError("GIT_REPOSITORY_MISMATCH: provider repository identity changed.")
        self.service.require("directory.read")
        return result

    def preview_repository(self, request: GitDirectoryRequest) -> GitDirectoryResult:
        decision = self.service.require("access.propose")
        self.service.require("directory.read")
        result = self.directory.members(request)
        self.service.require("access.propose", decision.access_digest)
        return result

    def import_members(self, request: GitImportRequest) -> AccessReviewView:
        self.service.require("access.propose", request.base_digest)
        result = self.git_members(request.directory)
        existing = self.service.view()
        accounts = {m.account.account_id: m for m in result.members}
        if len(set(request.account_ids)) != len(request.account_ids):
            raise ValueError("GIT_IMPORT_INVALID: select each stable account ID once.")
        mutations = []
        for account_id in request.account_ids:
            entry = accounts.get(account_id)
            if not entry or entry.state != "active":
                raise ValueError(
                    "GIT_MEMBER_UNAVAILABLE: member absent or blocked; refresh the directory."
                )
            prior = next(
                (
                    m
                    for m in existing.members
                    if m.git_account and m.git_account.identity == entry.account.identity
                ),
                None,
            )
            member = (
                prior.model_copy(update={"roles": request.roles, "git_account": entry.account})
                if prior
                else AccessMember(
                    principal_id=f"{entry.account.provider}-{account_id}",
                    label=entry.account.login,
                    roles=request.roles,
                    git_account=entry.account,
                    status="pending",
                )
            )
            mutations.append(AccessMutation(kind="member.set", member=member))
        return self.propose(
            AccessChangeRequest(base_digest=request.base_digest, mutations=tuple(mutations))
        )

    def review(self, proposal_id: str) -> AccessReviewView:
        proposal = self.service.review(proposal_id)
        before = self.service.view() if proposal.base_digest else None
        return AccessReviewView(
            proposal=proposal,
            before=before,
            signing_digest=proposal.signing_digest,
            review_command=(
                "agent",
                "access",
                "approve",
                proposal.candidate.binding.source_root,
                proposal.proposal_id,
                *self.review_options,
            ),
        )
