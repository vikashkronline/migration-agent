"""Genuine signed project fixture; no production authorization bypass or network."""

import subprocess
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from ssh_signature_fixture import ssh_signature

from migration_agent.adapters.access_rules import governance_rule_digests
from migration_agent.adapters.access_runtime import ProjectAuthorization, binding_name, root_commit
from migration_agent.adapters.access_signatures import AccessSignatures
from migration_agent.adapters.access_store import SignedAccessStore
from migration_agent.adapters.os_identity import current_os_identity
from migration_agent.application.access import AccessService
from migration_agent.config import Settings
from migration_agent.domain.access import (
    AccessActor,
    AccessMember,
    AccessPolicy,
    AccessProof,
    AccessRevision,
    ProjectAccessBinding,
    default_roles,
)


def commit_fixture(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for args in (
        ("init",),
        ("add", "."),
        (
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-m",
            "Fixture",
        ),
    ):
        subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)


def security_project(directory: Path, source: Path | None = None):
    source = source or directory / "source"
    if not (source / ".git").exists():
        commit_fixture(source)
    governance = directory / "governance"
    (governance / ".agent").mkdir(parents=True, exist_ok=True)
    (governance / ".agent/policy.json").write_text(
        '{"execution_mode":"container"}', encoding="utf-8"
    )
    commit_fixture(governance)
    settings = Settings(
        state_dir=directory / "state",
        staging_root=directory / "staging",
        trust_root=directory / "trust",
    )
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
    binding = ProjectAccessBinding(
        project_id="fixture-project",
        source_root=str(source.resolve()),
        governance_root=str(governance.resolve()),
        source_root_commit=root_commit(source),
        governance_root_commit=root_commit(governance),
    )
    signatures = AccessSignatures(settings.state_dir)
    store = SignedAccessStore(binding, settings.trust_root, settings.state_dir, signatures)
    service = AccessService(
        store, AccessActor(os_identity=current_os_identity(), client="human"), signatures
    )
    owner = AccessMember(
        principal_id="owner",
        label="Owner",
        roles=("owner",),
        status="active",
        os_identity=current_os_identity(),
        public_key=public,
        key_fingerprint=signatures.fingerprint(public),
    )
    policy = AccessPolicy(
        binding=binding,
        revision=1,
        members=(owner,),
        owners=("owner",),
        roles=default_roles(),
        rules=governance_rule_digests(governance),
    )
    proposal = service.bootstrap(policy)
    proof = AccessProof(
        principal_id="owner",
        key_fingerprint=owner.key_fingerprint,
        signature=ssh_signature(key, proposal.signing_digest),
    )
    service.commit(AccessRevision(proposal=proposal, proofs=(proof,)))
    for root in (source, governance):
        store._write(settings.trust_root, binding_name(root), binding)
    return ProjectAuthorization(source, settings), service, key
