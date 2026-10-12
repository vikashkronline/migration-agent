"""Composition and discovery of externally anchored project access."""

import hashlib
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from migration_agent.adapters.access_rules import governance_rule_digests
from migration_agent.adapters.access_signatures import AccessSignatures
from migration_agent.adapters.access_store import SignedAccessStore
from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.adapters.os_identity import current_os_identity
from migration_agent.application.access import AccessService
from migration_agent.config import Settings
from migration_agent.domain.access import (
    AccessActor,
    AccessDecision,
    AccessDenied,
    ProjectAccessBinding,
)
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.ports.governance import ProjectPolicy

UNINITIALIZED_READS = frozenset(
    {
        "system.diagnostics",
        "project.read",
        "run.read",
        "plan.read",
        "changeset.read",
        "evidence.read",
        "operation.read",
    }
)


def root_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True,
        text=True,
        shell=False,
        timeout=10,
    )
    commits = result.stdout.strip().splitlines()
    if result.returncode or len(commits) != 1:
        raise ValueError(
            "REPOSITORY_BINDING_REQUIRED: commit the source and governance repositories first."
        )
    return commits[0]


def binding_name(source: Path) -> str:
    identity = os.path.normcase(str(source.resolve()))
    return "access-bindings/" + hashlib.sha256(identity.encode()).hexdigest()[:24] + ".json"


class ProjectAuthorization:
    def __init__(
        self, source: Path, settings: Settings, client: Literal["human", "agent"] = "human"
    ) -> None:
        self.source = source.resolve()
        self.settings = settings
        self.client = client
        self.trust = (settings.trust_root or Path.home() / ".agent-platform/trust").resolve()
        self.state = settings.resolve_state_dir().resolve()
        self.actor = AccessActor(os_identity=current_os_identity(), client=client)

    def service(self) -> AccessService:
        if not self.trust.exists():
            raise AccessDenied("ACCESS_BOOTSTRAP_REQUIRED: enroll the governance project owner.")
        path = validate_repository_path(self.trust, binding_name(self.source))
        if not path.exists():
            raise AccessDenied(
                "ACCESS_BOOTSTRAP_REQUIRED: run access bootstrap with external governance."
            )
        binding = ProjectAccessBinding.model_validate_json(
            read_repository_text(self.trust, binding_name(self.source))
        )
        if (
            self.source
            not in {Path(binding.source_root).resolve(), Path(binding.governance_root).resolve()}
            or root_commit(Path(binding.source_root)) != binding.source_root_commit
        ):
            raise AccessDenied(
                "ACCESS_BINDING_INVALID: source identity differs from the external binding."
            )
        if root_commit(Path(binding.governance_root)) != binding.governance_root_commit:
            raise AccessDenied("ACCESS_BINDING_INVALID: governance repository identity changed.")
        signatures = AccessSignatures(self.state)
        return AccessService(
            SignedAccessStore(binding, self.trust, self.state, signatures), self.actor, signatures
        )

    def require(self, capability: str, expected_digest: str | None = None) -> AccessDecision:
        initialized = (
            self.trust.exists()
            and validate_repository_path(self.trust, binding_name(self.source)).exists()
        )
        if not initialized and capability in UNINITIALIZED_READS and expected_digest is None:
            return AccessDecision(
                allowed=True,
                reason="UNINITIALIZED_INSPECTION",
                capabilities=tuple(sorted(UNINITIALIZED_READS)),
            )
        service = self.service()
        decision = service.require(capability, expected_digest)
        if not capability.startswith("access.") and capability != "rules.manage":
            policy = service.store.read()
            if governance_rule_digests(Path(policy.binding.governance_root)) != policy.rules:
                raise AccessDenied(
                    "RULES_CHANGED: security rules differ from the signed owner revision."
                )
        return decision

    def project_policy(self) -> ProjectPolicy:
        self.require("project.read")
        policy = self.service().store.read()
        if ".agent/policy.json" not in policy.rules:
            raise AccessDenied(
                "SIGNED_POLICY_REQUIRED: include governance policy in an owner-signed revision."
            )
        parsed_policy = ProjectPolicy.model_validate_json(
            read_repository_text(Path(policy.binding.governance_root), ".agent/policy.json")
        )
        configuration_path = validate_repository_path(
            Path(policy.binding.governance_root), ".agent/config.json"
        )
        if configuration_path.exists():
            import json

            from migration_agent.domain.configuration import ProjectConfiguration

            text = read_repository_text(configuration_path.parent, configuration_path.name)
            data = json.loads(text)
            if data != {"version": 1, "workflows": {}}:
                configuration = ProjectConfiguration.model_validate_json(text)
                parsed_policy = parsed_policy.model_copy(
                    update={
                        "max_step_files": min(
                            parsed_policy.max_step_files, configuration.max_step_files
                        )
                    }
                )
        return parsed_policy

    def project_policy_digest(self) -> str:
        return compute_canonical_digest(self.project_policy())

    @contextmanager
    def fence(self, capability: str) -> Iterator[None]:
        with self.service().fence(capability):
            yield

    def require_signature(self, capability: str, fingerprint: str | None) -> None:
        self.service().require_signature(capability, fingerprint)
