"""Explicit opt-in fixtures for legacy non-RBAC CLI mechanics regressions."""

import pytest
from access_fixture import WorkflowAuthorizationFixture


@pytest.fixture
def cli_workflow_authorization(monkeypatch):
    from migration_agent.adapters.workflow_runtime import WorkflowRuntime

    authorization = WorkflowAuthorizationFixture()
    monkeypatch.setattr(
        "migration_agent.adapters.cli_access.ProjectAuthorization",
        lambda *args, **kwargs: authorization,
    )
    monkeypatch.setattr(
        "migration_agent.adapters.workflow_cli.WorkflowRuntime",
        lambda binding, settings, state=None: WorkflowRuntime(
            binding, settings, state, authorization
        ),
    )
    return authorization
