"""Offline owner management against the real Control API and packaged Angular client."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from security_project import security_project

from migration_agent.adapters.control_api.server import LoopbackControlServer
from migration_agent.adapters.workbench import CanonicalWorkbench
from migration_agent.application.control_service import ControlApiService
from migration_agent.application.workbench import WorkbenchService
from migration_agent.domain.inspection_access import InspectionCapability, InspectionContext
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.workflow_access import WorkflowCapability, WorkflowContext


def test_real_owner_user_management_browser(tmp_path):
    node = shutil.which("node")
    browser = Path(
        os.environ.get(
            "CHROME_BIN",
            "C:/Program Files/Google/Chrome/Application/chrome.exe"
            if os.name == "nt"
            else "/usr/bin/chromium",
        )
    )
    if (
        not node
        or not browser.is_file()
        or not Path("ui/control-center/node_modules/playwright-core").is_dir()
    ):
        pytest.skip(
            "Offline GUI acceptance requires installed Node, Chromium and npm dependencies."
        )
    authorization, owner, _ = security_project(tmp_path)
    source = CanonicalWorkbench(
        authorization.source,
        authorization.settings,
        WorkflowContext(
            actor="owner",
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(WorkflowCapability),
        ),
    )
    workbench = WorkbenchService(
        source,
        InspectionContext(
            actor="owner",
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(InspectionCapability),
        ),
    )
    server = LoopbackControlServer(
        ControlApiService(), authorization.source, workbench=workbench, authorization=authorization
    )
    server.start("127.0.0.1", 0, "offline-rbac-browser-fixture")
    try:
        result = subprocess.run(
            [node, "tests/rbac.cjs"],
            cwd="ui/control-center",
            env={**os.environ, "GUI_TEST_ORIGIN": server.get_url(), "CHROME_BIN": str(browser)},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert owner.view().revision == 1
        assert len(tuple((authorization.state / "access-proposals").glob("*.json"))) == 2
    finally:
        server.stop()
        source.close()
