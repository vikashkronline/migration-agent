"""Client setup is deterministic, preview-first, and preserves unrelated configuration."""

import json
import sys
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migration_agent.adapters.mcp.setup import setup_client
from migration_agent.cli import app
from migration_agent.config import Settings


@pytest.mark.parametrize("client", ["codex", "antigravity", "cursor", "claude"])
def test_setup_preview_write_backup_and_idempotency(tmp_path: Path, client: str):
    source = tmp_path / "source space"
    source.mkdir()
    config = tmp_path / "config" / ("config.toml" if client == "codex" else "mcp.json")
    config.parent.mkdir()
    original = (
        b'# preserve comment\nmodel = "chosen"\n'
        if client == "codex"
        else b'{"preference": "keep", "mcpServers": {"other": {"command": "keep"}}}\n'
    )
    config.write_bytes(original)
    settings = Settings(state_dir=tmp_path / "state", staging_root=tmp_path / "staging")
    preview = setup_client(client, source, settings, config)
    assert preview.status == "PREVIEW" and config.read_bytes() == original
    assert preview.entry["command"] == str(Path(sys.executable).absolute())
    assert not (tmp_path / "state").exists()
    result = setup_client(client, source, settings, config, write=True)
    assert result.status == "WRITTEN" and Path(result.backup_path).read_bytes() == original
    if client == "codex":
        parsed = tomllib.loads(config.read_text())
        assert parsed["model"] == "chosen" and "preserve comment" in config.read_text()
        assert parsed["mcp_servers"][result.server_name] == result.entry
    else:
        parsed = json.loads(config.read_text())
        assert parsed["preference"] == "keep" and parsed["mcpServers"]["other"] == {
            "command": "keep"
        }
        assert parsed["mcpServers"][result.server_name] == result.entry
    before = config.read_bytes()
    assert setup_client(client, source, settings, config, write=True).status == "UNCHANGED"
    assert config.read_bytes() == before
    assert not (source / ".agent").exists()


def test_setup_rejects_invalid_and_secret_config_without_printing(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    config = tmp_path / "config" / "mcp.json"
    config.parent.mkdir()
    config.write_text('{"mcpServers": [], "API_KEY": "sk-synthetic-fixture-123456789"}')
    settings = Settings(state_dir=tmp_path / "state", staging_root=tmp_path / "staging")
    before = config.read_bytes()
    with pytest.raises(ValueError, match="CONFIG_PROTECTED"):
        setup_client("antigravity", source, settings, config, write=True)
    assert config.read_bytes() == before and not list(config.parent.glob("*.backup-*"))
    with pytest.raises(ValueError, match="UNSAFE_ROOT_OVERLAP"):
        setup_client("codex", source, settings, source / "config.toml", write=True)


def test_cli_setup_defaults_to_preview(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "config" / "config.toml"
    result = CliRunner().invoke(
        app,
        [
            "mcp",
            "setup",
            "--client",
            "codex",
            "--project-root",
            str(source),
            "--config",
            str(target),
            "--state-dir",
            str(tmp_path / "state"),
            "--staging-root",
            str(tmp_path / "staging"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "PREVIEW" and not target.exists()
