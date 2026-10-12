"""Unit tests for the 'migration-agent ui' command."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from migration_agent.cli import app

runner = CliRunner()


def test_cli_ui_help() -> None:
    result = runner.invoke(app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "Launch the Local Control Center web GUI" in result.stdout
    assert "--port" in result.stdout
    assert "--host" in result.stdout


def test_cli_ui_rejects_non_loopback_host(tmp_path: Path) -> None:
    result = runner.invoke(app, ["ui", str(tmp_path), "--host", "0.0.0.0"])
    assert result.exit_code == 2
    assert "must bind strictly to loopback" in result.stderr


def test_cli_ui_rejects_nonexistent_path() -> None:
    result = runner.invoke(app, ["ui", "nonexistent/directory/path/12345"])
    assert result.exit_code == 2
    assert "does not exist" in result.stderr


def test_cli_ui_starts_and_stops_cleanly(tmp_path: Path) -> None:
    with (
        patch("migration_agent.cli.webbrowser.open") as mock_open,
        patch("migration_agent.cli.time.sleep", side_effect=KeyboardInterrupt),
    ):
        result = runner.invoke(
            app,
            [
                "ui",
                str(tmp_path),
                "--port",
                "8999",
                "--token",
                "custom-secret-token-1234567890",
                "--no-open",
                "--state-dir",
                str(tmp_path.parent / "ui-state"),
                "--staging-root",
                str(tmp_path.parent / "ui-staging"),
            ],
        )
        assert result.exit_code == 0
        assert "http://127.0.0.1:8999" in result.stdout
        assert "custom-secret-token-1234567890" not in result.stdout
        assert "stopped" in result.stdout
        mock_open.assert_not_called()


def test_cli_ui_rejects_overlapping_state_root(tmp_path: Path) -> None:
    result = runner.invoke(app, ["ui", str(tmp_path), "--state-dir", str(tmp_path / "state")])
    assert result.exit_code == 2
    assert "STATE" in result.stderr or "ROOT" in result.stderr
