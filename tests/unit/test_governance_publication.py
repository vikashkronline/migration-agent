"""Trusted publication verifier rejects unsigned Git governance edits and rollback."""

import subprocess
from pathlib import Path

import pytest
from security_project import commit_fixture, security_project
from test_access import signed

from migration_agent.adapters.governance_publication import GitPublicationReader
from migration_agent.application.governance_publication import verify_publication
from migration_agent.domain.access import AccessDenied


def head(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_signed_publication_and_unsigned_rule_edits(tmp_path):
    _, service, _ = security_project(tmp_path)
    policy = service.view()
    root = Path(policy.binding.governance_root)
    commit_fixture(root)
    reader = GitPublicationReader(root)
    assert verify_publication(policy, reader.read(head(root)), service.signatures).accepted
    (root / ".agent/policy.json").write_text('{"execution_mode":"trusted"}')
    commit_fixture(root)
    with pytest.raises(AccessDenied, match="PUBLICATION_RULES_INVALID"):
        verify_publication(policy, reader.read(head(root)), service.signatures)


def test_git_history_rollback_cannot_replace_trusted_head(tmp_path):
    _, service, key = security_project(tmp_path)
    before = service.view()
    root = Path(before.binding.governance_root)
    commit_fixture(root)
    old_commit = head(root)
    candidate = before.model_copy(update={"revision": 2, "previous_digest": before.digest})
    service.commit(signed(service.propose(candidate), key, before.members[0]))
    commit_fixture(root)
    reader = GitPublicationReader(root)
    assert verify_publication(service.view(), reader.read(head(root)), service.signatures).accepted
    with pytest.raises(AccessDenied, match="PUBLICATION_ROLLBACK"):
        verify_publication(service.view(), reader.read(old_commit), service.signatures)
