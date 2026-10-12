"""Production Settings UI acceptance against genuine signed loopback governance."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_configuration import activate, project_configuration
from test_configuration import configured as configuration_fixture

from migration_agent.adapters.control_api.server import LoopbackControlServer
from migration_agent.adapters.workbench import CanonicalWorkbench
from migration_agent.application.control_service import ControlApiService
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.workflow_access import WorkflowCapability, WorkflowContext


def test_settings_production_browser(tmp_path):
    browser = Path(
        os.environ.get(
            "CHROME_BIN",
            "C:/Program Files/Google/Chrome/Application/chrome.exe"
            if os.name == "nt"
            else "/usr/bin/chromium",
        )
    )
    node = shutil.which("node")
    if node is None or not browser.is_file():
        pytest.skip("Installed Node and Chromium required for offline production GUI acceptance.")
    facade, access, key = configuration_fixture.__wrapped__(tmp_path)
    activate(facade, access, key, project_configuration())
    source = facade.repository.source
    before = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    workbench = CanonicalWorkbench(
        source,
        facade.repository.settings,
        WorkflowContext(
            actor="owner",
            assurance=AssuranceLevel.MODE_B,
            capabilities=frozenset(WorkflowCapability),
        ),
        authorization=facade.authorization,
    )
    server = LoopbackControlServer(
        ControlApiService(),
        source,
        authorization=facade.authorization,
        settings=facade.repository.settings,
        workbench=workbench,
    )
    server.start("127.0.0.1", 0, "offline-configuration-browser")
    try:
        result = subprocess.run(
            [node, "tests/live-settings.cjs"],
            cwd="ui/control-center",
            env={
                **os.environ,
                "GUI_TEST_ORIGIN": server.get_url(),
                "CHROME_BIN": str(browser),
                "CONFIGURATION_SCREENSHOTS": str(
                    Path("reports/configuration-verification").resolve()
                ),
            },
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert facade.repository.local().model == "alternate-model"
        assert access.view().revision == 2, "GUI handoff must not sign or activate"
        after = {
            p.relative_to(source).as_posix(): p.read_bytes()
            for p in source.rglob("*")
            if p.is_file() and ".git" not in p.parts
        }
        assert after == before
    finally:
        server.stop()
        workbench.close()
