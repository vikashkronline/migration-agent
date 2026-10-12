"""Project access contracts and deterministic authorization, independent of transports."""

from enum import StrEnum
from typing import Any, Literal, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.inspection_access import InspectionCapability
from migration_agent.domain.workflow_access import WorkflowCapability


class AccessModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AdminCapability(StrEnum):
    ACCESS_READ = "access.read"
    ACCESS_PROPOSE = "access.propose"
    ACCESS_COMMIT = "access.commit"
    RULES_MANAGE = "rules.manage"
    KNOWLEDGE_WRITE = "knowledge.write"
    KNOWLEDGE_APPROVE = "knowledge.approve"
    APPROVAL_SIGN = "approval.sign"
    NATIVE_CONSENT = "execution.consent"
    PROVIDER_USE = "provider.use"
    DIRECTORY_READ = "directory.read"
    CONFIGURATION_READ = "configuration.read"
    CONFIGURATION_PROPOSE = "configuration.propose"
    CONFIGURATION_LOCAL_WRITE = "configuration.local.write"


CAPABILITIES = frozenset(
    str(item)
    for group in (AdminCapability, InspectionCapability, WorkflowCapability)
    for item in group
)
HUMAN_ONLY = frozenset(
    {"access.commit", "rules.manage", "approval.sign", "execution.consent", "knowledge.approve"}
)
Id = str


class GitAccount(AccessModel):
    provider: Literal["github", "gitlab"]
    host: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,252}$")
    account_id: str = Field(pattern=r"^[0-9]{1,24}$")
    login: str = Field(min_length=1, max_length=128)

    @property
    def identity(self) -> str:
        return f"{self.provider}:{self.host}:{self.account_id}"


class GitRepositoryBinding(AccessModel):
    provider: Literal["github", "gitlab"]
    host: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,252}$")
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+){1,8}$", max_length=256)
    repository_id: str = Field(pattern=r"^[0-9]{1,24}$")


class AccessRole(AccessModel):
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    label: str = Field(min_length=1, max_length=80)
    capabilities: tuple[str, ...] = Field(max_length=128)

    @model_validator(mode="after")
    def valid_capabilities(self) -> Self:
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("ACCESS_INVALID: duplicate capabilities.")
        if set(self.capabilities) - CAPABILITIES:
            raise ValueError("ACCESS_INVALID: unregistered capability; wildcards are forbidden.")
        return self


class AccessMember(AccessModel):
    principal_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
    label: str = Field(min_length=1, max_length=128)
    roles: tuple[str, ...] = Field(max_length=128)
    status: Literal["pending", "active", "suspended"] = "pending"
    os_identity: str | None = Field(default=None, min_length=1, max_length=256)
    public_key: str | None = Field(default=None, min_length=1, max_length=1024)
    key_fingerprint: str | None = Field(default=None, min_length=1, max_length=100)
    git_account: GitAccount | None = None
    expires_at: int | None = Field(default=None, ge=1)


class ProjectAccessBinding(AccessModel):
    project_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")
    source_root: str = Field(min_length=1, max_length=4096)
    governance_root: str = Field(min_length=1, max_length=4096)
    source_root_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    governance_root_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")


class AccessPolicy(AccessModel):
    schema_version: Literal[2] = 2
    catalog_version: Literal[1] = 1
    binding: ProjectAccessBinding
    revision: int = Field(ge=1, le=10000)
    revision_nonce: str = Field(default="0" * 32, pattern=r"^[a-f0-9]{32}$")
    previous_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    roles: tuple[AccessRole, ...] = Field(min_length=1, max_length=128)
    members: tuple[AccessMember, ...] = Field(min_length=1, max_length=1000)
    owners: tuple[str, ...] = Field(min_length=1, max_length=32)
    rules: dict[str, str] = Field(default_factory=dict, max_length=512)
    git_repository: GitRepositoryBinding | None = None

    @model_validator(mode="after")
    def valid_graph(self) -> Self:
        roles = {r.role_id: r for r in self.roles}
        members = {m.principal_id: m for m in self.members}
        if len(roles) != len(self.roles) or len(members) != len(self.members):
            raise ValueError("ACCESS_INVALID: duplicate role or member ID.")
        if len(set(self.owners)) != len(self.owners) or set(self.owners) - members.keys():
            raise ValueError("ACCESS_INVALID: duplicate or unknown owner.")
        bindings: set[str] = set()
        for member in self.members:
            if len(set(member.roles)) != len(member.roles) or set(member.roles) - roles.keys():
                raise ValueError("ACCESS_INVALID: duplicate or unknown member role.")
            if bool(member.public_key) != bool(member.key_fingerprint):
                raise ValueError("ACCESS_INVALID: public key and fingerprint must be paired.")
            if member.status == "active" and not (member.os_identity or member.public_key):
                raise ValueError("ACCESS_INVALID: active membership needs verified identity.")
            for identity in (
                member.os_identity,
                member.key_fingerprint,
                member.git_account.identity if member.git_account else None,
            ):
                if identity and identity in bindings:
                    raise ValueError("ACCESS_INVALID: identity is bound to multiple principals.")
                if identity:
                    bindings.add(identity)
        for owner in self.owners:
            member = members[owner]
            grants = {c for role in member.roles for c in roles[role].capabilities}
            if (
                member.status != "active"
                or not member.os_identity
                or not member.public_key
                or member.expires_at is not None
                or not {"access.read", "access.propose", "access.commit"} <= grants
            ):
                raise ValueError(
                    "LAST_OWNER: owners require active, non-expiring identity and authority."
                )
        for path, digest in self.rules.items():
            if (
                not path.startswith(".agent/")
                or "\\" in path
                or any(p in {"", ".", ".."} for p in path.split("/"))
                or path.startswith(".agent/access/")
                or not digest.startswith("sha256:")
                or len(digest) != 71
            ):
                raise ValueError("ACCESS_INVALID: rules need safe POSIX paths and full digests.")
        return self

    @property
    def digest(self) -> str:
        return compute_canonical_digest(self)


class AccessActor(AccessModel):
    os_identity: str = Field(min_length=1, max_length=256)
    client: Literal["human", "agent"]
    ceiling: frozenset[str] = Field(default_factory=lambda: CAPABILITIES)


class AccessDecision(AccessModel):
    allowed: bool
    reason: str
    principal_id: str | None = None
    roles: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    access_digest: str | None = None
    key_fingerprint: str | None = None


def decide_access(
    policy: AccessPolicy, actor: AccessActor, capability: str, now: int
) -> AccessDecision:
    member = next((m for m in policy.members if m.os_identity == actor.os_identity), None)
    grants: set[str] = set()
    if (
        member
        and member.status == "active"
        and (member.expires_at is None or member.expires_at > now)
    ):
        roles = {r.role_id: r for r in policy.roles}
        grants = {c for role in member.roles for c in roles[role].capabilities}
    grants &= actor.ceiling
    if actor.client == "agent":
        grants -= HUMAN_ONLY
    allowed = capability in CAPABILITIES and capability in grants
    return AccessDecision(
        allowed=allowed,
        reason="ALLOWED" if allowed else "CAPABILITY_DENIED",
        principal_id=member.principal_id if member else None,
        roles=member.roles if member and grants else (),
        capabilities=tuple(sorted(grants)),
        access_digest=policy.digest,
        key_fingerprint=member.key_fingerprint if member and grants else None,
    )


class GovernanceFileChange(AccessModel):
    path: Literal[".agent/config.json", ".agent/architecture.json"] = ".agent/config.json"
    previous_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    content: str = Field(max_length=65536)


class AccessProposal(AccessModel):
    proposal_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    candidate: AccessPolicy
    snapshot_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    revision_locator: str = Field(pattern=r"^rev-[0-9a-f]{16}(?:[0-9a-f]{8}){0,2}$")
    base_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    proposer: str = Field(min_length=1, max_length=256)
    created_at: int = Field(ge=1)
    expires_at: int = Field(ge=1)
    nonce: str = Field(pattern=r"^[a-f0-9]{32}$")
    governance_changes: tuple[GovernanceFileChange, ...] = Field(default=(), max_length=1)

    @model_serializer(mode="wrap")
    def compatible_serialization(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = cast(dict[str, Any], handler(self))
        if not self.governance_changes:
            data.pop("governance_changes", None)
        return data

    @property
    def signing_digest(self) -> str:
        return compute_canonical_digest({"purpose": "migration-agent-access-v2", "proposal": self})


class AccessProof(AccessModel):
    principal_id: str = Field(min_length=1, max_length=64)
    key_fingerprint: str = Field(min_length=1, max_length=100)
    signature: str = Field(min_length=1, max_length=8192)


class AccessRevision(AccessModel):
    proposal: AccessProposal
    proofs: tuple[AccessProof, ...] = Field(min_length=1, max_length=32)


class AccessDenied(ValueError):
    """Authorization denial with a stable public reason."""


def default_roles() -> tuple[AccessRole, ...]:
    reads = {str(c) for c in InspectionCapability} | {
        "evidence.read",
        "operation.read",
        "access.read",
        "configuration.read",
    }
    developer = reads | {
        "analysis.submit",
        "plan.submit",
        "repair.submit",
        "changeset.stage",
        "validation.run",
        "approval.request",
        "operation.cancel",
        "knowledge.write",
        "provider.use",
        "configuration.propose",
        "configuration.local.write",
    }
    reviewer = reads | {"approval.request", "approval.sign", "knowledge.approve"}
    return tuple(
        AccessRole(role_id=role, label=role.title(), capabilities=tuple(sorted(caps)))
        for role, caps in (
            ("owner", CAPABILITIES),
            ("developer", developer),
            ("reviewer", reviewer),
            ("operator", developer | {"changeset.apply", "execution.consent"}),
            ("viewer", reads),
        )
    )


class ConfigurationActivationRequest(AccessModel):
    proposal_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    revision: AccessRevision
