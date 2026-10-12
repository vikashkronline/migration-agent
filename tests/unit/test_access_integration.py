"""Owner administration, real runtime enforcement, API and Git membership regressions."""

import base64
import getpass
import shutil
from pathlib import Path

import pytest
from security_project import security_project
from test_access import signed
from test_host_workflow import plan_proposal
from typer.testing import CliRunner

from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.adapters.workflow_runtime import WorkflowRuntime
from migration_agent.application.access import AccessService
from migration_agent.application.access_api import (
    AccessAdministration,
    AccessChangeRequest,
    AccessMutation,
    GitImportRequest,
)
from migration_agent.cli import app
from migration_agent.config import Settings
from migration_agent.domain.access import (
    AccessActor,
    AccessDenied,
    AccessMember,
    GitAccount,
    GitRepositoryBinding,
)
from migration_agent.domain.git_directory import (
    GitDirectoryMember,
    GitDirectoryRequest,
    GitDirectoryResult,
)


class DirectoryFixture:
    def members(self, request):
        return GitDirectoryResult(
            request=request,
            repository_id="123",
            members=(
                GitDirectoryMember(
                    account=GitAccount(
                        provider=request.provider,
                        host=request.host,
                        account_id="42",
                        login="existing-maintainer",
                    ),
                    git_role="maintainer",
                ),
            ),
        )


@pytest.mark.parametrize("provider,host", [("github", "github.com"), ("gitlab", "gitlab.com")])
def test_git_maintainer_import_is_explicit_pending_membership(tmp_path, provider, host):
    _, service, key = security_project(tmp_path)
    policy = service.view()
    connection = GitRepositoryBinding(
        provider=provider, host=host, repository="org/governance", repository_id="123"
    )
    configured = policy.model_copy(
        update={"revision": 2, "previous_digest": policy.digest, "git_repository": connection}
    )
    service.commit(signed(service.propose(configured), key, policy.members[0]))
    policy = service.view()
    admin = AccessAdministration(service, DirectoryFixture())
    request = GitImportRequest(
        directory=GitDirectoryRequest(provider=provider, host=host, repository="org/governance"),
        account_ids=("42",),
        roles=("reviewer",),
        base_digest=policy.digest,
    )
    view = admin.import_members(request)
    imported = next(m for m in view.proposal.candidate.members if m.git_account)
    assert imported.roles == ("reviewer",) and imported.status == "pending"
    assert (
        imported.os_identity is None and imported.principal_id not in view.proposal.candidate.owners
    )
    service.commit(signed(view.proposal, key, policy.members[0]))
    assert service.view().revision == 3
    assert (
        not AccessService(
            service.store, AccessActor(os_identity="42", client="human"), service.signatures
        )
        .explain("approval.sign")
        .allowed
    )


def test_foreign_directory_id_and_unknown_role_fail_closed(tmp_path):
    _, service, key = security_project(tmp_path)
    policy = service.view()
    connection = GitRepositoryBinding(
        provider="github", host="github.com", repository="org/repo", repository_id="123"
    )
    service.commit(
        signed(
            service.propose(
                policy.model_copy(
                    update={
                        "revision": 2,
                        "previous_digest": policy.digest,
                        "git_repository": connection,
                    }
                )
            ),
            key,
            policy.members[0],
        )
    )
    admin = AccessAdministration(service, DirectoryFixture())
    request = GitImportRequest(
        directory=GitDirectoryRequest(provider="github", host="github.com", repository="org/repo"),
        account_ids=("999",),
        roles=("developer",),
        base_digest=service.view().digest,
    )
    with pytest.raises(ValueError, match="GIT_MEMBER_UNAVAILABLE"):
        admin.import_members(request)
    with pytest.raises(ValueError, match="unknown member role"):
        admin.import_members(
            request.model_copy(update={"account_ids": ("42",), "roles": ("superuser",)})
        )


def test_unsigned_security_rule_change_blocks_workflow_not_owner_repair(tmp_path):
    authorization, service, key = security_project(tmp_path)
    policy = service.view()
    assert authorization.require("changeset.stage").allowed
    governance = Path(policy.binding.governance_root)
    (governance / ".agent/policy.json").write_text('{"execution_mode":"trusted"}')
    with pytest.raises(AccessDenied, match="RULES_CHANGED"):
        authorization.require("changeset.stage")
    assert service.require("access.propose").allowed
    from migration_agent.adapters.access_rules import governance_rule_digests

    candidate = policy.model_copy(
        update={
            "revision": 2,
            "previous_digest": policy.digest,
            "rules": governance_rule_digests(governance),
        }
    )
    service.commit(signed(service.propose(candidate), key, policy.members[0]))
    assert authorization.project_policy().execution_mode == "trusted"


def test_governance_json_line_endings_do_not_require_role_approval(tmp_path):
    authorization, service, _ = security_project(tmp_path)
    governance = Path(service.view().binding.governance_root)
    (governance / ".agent/policy.json").write_bytes(
        b'{\r\n  "execution_mode": "container"\r\n}\r\n'
    )
    assert authorization.require("changeset.stage").allowed
    (governance / ".agent/policy.json").write_text(
        '{"execution_mode":"container","execution_mode":"trusted"}'
    )
    with pytest.raises(ValueError, match="RULES_JSON_INVALID"):
        authorization.require("changeset.stage")


def test_real_runtime_denies_uninitialized_mutation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    runtime = WorkflowRuntime(
        ProjectBinding(source),
        Settings(
            state_dir=tmp_path / "state",
            staging_root=tmp_path / "stage",
            trust_root=tmp_path / "trust",
        ),
    )
    try:
        with pytest.raises(AccessDenied, match="BOOTSTRAP_REQUIRED"):
            runtime.dispatch("stage", "plan", "step", "request")
        assert runtime.authorization.require("project.read").allowed
    finally:
        runtime.close()


def test_real_runtime_and_revoked_request_cannot_replay(tmp_path):
    source = tmp_path / "source"
    shutil.copytree("tests/fixtures/ember-classic-mini", source)
    authorization, owner, key = security_project(tmp_path, source)
    policy = owner.view()
    dev = AccessMember(
        principal_id="developer",
        label="Developer",
        roles=("developer",),
        status="active",
        os_identity="test:developer",
    )
    candidate = policy.model_copy(
        update={"revision": 2, "previous_digest": policy.digest, "members": (*policy.members, dev)}
    )
    owner.commit(signed(owner.propose(candidate), key, policy.members[0]))
    service = AccessService(
        owner.store, AccessActor(os_identity="test:developer", client="agent"), owner.signatures
    )
    runtime = WorkflowRuntime(ProjectBinding(source), authorization.settings, authorization=service)
    try:
        proposal = plan_proposal(runtime.proposals)
        saved = runtime.proposals.submit_plan("plan-request", proposal)
        policy = owner.view()
        candidate = policy.model_copy(
            update={
                "revision": 3,
                "previous_digest": policy.digest,
                "members": tuple(
                    m.model_copy(update={"status": "suspended"})
                    if m.principal_id == "developer"
                    else m
                    for m in policy.members
                ),
            }
        )
        owner.commit(signed(owner.propose(candidate), key, policy.members[0]))
        with pytest.raises(AccessDenied, match="CAPABILITY_DENIED"):
            runtime.proposals.submit_plan("plan-request", proposal)
        assert (
            runtime.store.get_operation(runtime.binding.project_id, saved.operation_id).status
            == saved.status
        )
    finally:
        runtime.close()


def test_cli_actor_labels_and_public_catalog_cannot_elevate(tmp_path, monkeypatch):
    authorization, owner, key = security_project(tmp_path)
    policy = owner.view()
    dev = AccessMember(
        principal_id="viewer",
        label="Viewer",
        roles=("viewer",),
        status="active",
        os_identity="test:viewer",
    )
    candidate = policy.model_copy(
        update={"revision": 2, "previous_digest": policy.digest, "members": (*policy.members, dev)}
    )
    owner.commit(signed(owner.propose(candidate), key, policy.members[0]))
    monkeypatch.setattr(
        "migration_agent.adapters.access_runtime.current_os_identity", lambda: "test:viewer"
    )
    result = CliRunner().invoke(
        app,
        [
            "plan",
            "approve",
            "plan",
            "--actor",
            "owner",
            "--project-root",
            str(authorization.source),
            "--state-dir",
            str(authorization.state),
            "--trust-dir",
            str(authorization.trust),
        ],
    )
    assert result.exit_code == 2
    assert "CAPABILITY_DENIED" in result.output
    assert CliRunner().invoke(app, ["access", "capabilities"]).exit_code == 0


def test_enrolled_owner_key_is_workflow_authority_without_legacy_trust_file(tmp_path, monkeypatch):
    from test_shared_apply import ValidationFixture

    from migration_agent.domain.apply_approval import HumanDecision
    from migration_agent.domain.planning import AssuranceLevel
    from migration_agent.domain.validation import ValidationCommand, ValidationProfile

    source = tmp_path / "source"
    shutil.copytree("tests/fixtures/ember-classic-mini", source)
    authorization, owner, private = security_project(tmp_path, source)
    authorization.settings = authorization.settings.model_copy(
        update={"final_target_root": tmp_path / "target"}
    )
    runtime = WorkflowRuntime(ProjectBinding(source), authorization.settings)
    # Signature authority fixture; foundation readiness has separate acceptance tests.
    runtime.apply_service.foundation_contract = None
    try:
        proposal = plan_proposal(runtime.proposals)
        submitted = runtime.proposals.submit_plan("workflow-authority", proposal)
        lease = runtime.store.acquire_lease(runtime.binding.project_id, "fixture")
        runtime.apply_service.execution_gate = ValidationFixture()
        runtime.apply_service.browser_gate = None
        try:
            runtime.apply_service.stage(submitted.plan_id, proposal.steps[0].step_id, lease)
            runtime.apply_service.validate(
                submitted.plan_id,
                proposal.steps[0].step_id,
                (
                    ValidationCommand(
                        executable="tsc", args=("--noEmit",), profile=ValidationProfile.TYPECHECK
                    ),
                ),
                runtime.apply_service.execution_gate,
                lease,
            )
        finally:
            runtime.store.release_lease(lease)
        fingerprint = owner.view().members[0].key_fingerprint

        class HumanReview:
            def confirm(self, payload):
                return HumanDecision(
                    confirmed=True,
                    actor=getpass.getuser(),
                    assurance=AssuranceLevel.MODE_A,
                    key_fingerprint=fingerprint,
                )

        monkeypatch.setattr(
            runtime.apply_service.proof,
            "sign",
            lambda record: (
                "ed25519-base64:"
                + base64.b64encode(private.sign(record.signing_digest.encode())).decode()
            ),
        )
        approval = runtime.apply_service.approve(
            submitted.plan_id, proposal.steps[0].step_id, HumanReview()
        )
        assert approval.principal_id == "owner" and approval.access_digest == owner.view().digest
        assert not (authorization.trust / f"{runtime.binding.project_id}.json").exists()
        assert runtime.apply_service.proof.verify(approval, owner.view().binding.source_root_commit)
    finally:
        runtime.close()


def test_cli_proposal_mutations_stale_policy_and_last_owner(tmp_path):
    _, service, _ = security_project(tmp_path)
    admin = AccessAdministration(service, DirectoryFixture())
    with pytest.raises(ValueError, match="owners"):
        admin.propose(
            AccessChangeRequest(
                base_digest=service.view().digest,
                mutations=(AccessMutation(kind="owners.set", owners=()),),
            )
        )
    with pytest.raises(AccessDenied, match="ACCESS_CHANGED"):
        admin.propose(
            AccessChangeRequest(
                base_digest="sha256:" + "0" * 64,
                mutations=(AccessMutation(kind="member.remove", entity_id="owner"),),
            )
        )
