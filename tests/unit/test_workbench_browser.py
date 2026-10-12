"""Offline browser integration uses the real server and canonical projection."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_workbench import make_source, save_plan, service

from migration_agent.adapters.control_api.server import LoopbackControlServer
from migration_agent.application.control_service import ControlApiService


def test_production_client_with_real_loopback_and_canonical_state(tmp_path: Path) -> None:
    node = shutil.which("node")
    browser = Path(
        os.environ.get(
            "CHROME_BIN",
            "C:/Program Files/Google/Chrome/Application/chrome.exe"
            if os.name == "nt"
            else "/usr/bin/chromium",
        )
    )
    client = Path("ui/control-center")
    if (
        node is None
        or not browser.is_file()
        or not (client / "node_modules/playwright-core").is_dir()
    ):
        pytest.skip("Offline GUI browser gate requires installed Node, Chromium and npm ci.")
    source = make_source(tmp_path)
    save_plan(source, title="Document generic interfaces")
    before = list(source.binding.project_root.rglob("*"))
    server = LoopbackControlServer(
        ControlApiService(),
        source.binding.project_root,
        workbench=service(source),
        authorization=source.authorization,
    )
    server.start("127.0.0.1", 0, "offline-live-fixture")
    try:
        result = subprocess.run(
            [node, "tests/live-workbench.cjs"],
            cwd=client,
            env={**os.environ, "GUI_TEST_ORIGIN": server.get_url(), "CHROME_BIN": str(browser)},
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert list(source.binding.project_root.rglob("*")) == before
    finally:
        server.stop()
        source.close()
