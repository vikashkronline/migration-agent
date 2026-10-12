"""Preview-first, credential-free local client configuration with atomic backups."""

import hashlib
import json
import os
import sys
import tomllib
import uuid
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel, ConfigDict

from migration_agent.adapters.mcp.binding import ProjectBinding
from migration_agent.config import Settings
from migration_agent.domain.redaction import RedactionPolicy


class SetupPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    client: str
    config_path: str
    server_name: str
    entry: dict[str, object]
    status: str = "PREVIEW"
    backup_path: str | None = None


def default_config(client: str) -> Path:
    if client == "codex":
        return Path.home() / ".codex" / "config.toml"
    if client == "antigravity":
        return Path.home() / ".gemini" / "config" / "mcp_config.json"
    if client == "cursor":
        return Path.home() / ".cursor" / "mcp.json"
    raise ValueError("CONFIG_REQUIRED: supply the installed Claude client's configuration path.")


def setup_client(
    client: str,
    project_root: Path,
    settings: Settings,
    config_path: Path | None = None,
    write: bool = False,
) -> SetupPreview:
    if client not in {"codex", "antigravity", "cursor", "claude"}:
        raise ValueError("CLIENT_UNSUPPORTED: choose a supported configuration format.")
    binding = ProjectBinding(project_root)
    target = (config_path or default_config(client)).expanduser().absolute()
    binding.validate_storage_roots(settings.resolve_state_dir(), settings.resolve_staging_root())
    binding.validate_storage_roots(target.parent)
    cursor = target
    while cursor != cursor.parent:
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError("CONFIG_PATH_UNSAFE: configuration cannot follow links.")
        cursor = cursor.parent
    name = f"migration_agent_{binding.project_id[-16:]}"
    args = ([] if getattr(sys, "frozen", False) else ["-m", "migration_agent.cli"]) + [
        "mcp",
        "serve",
        "--project-root",
        str(binding.project_root),
        "--state-dir",
        str(settings.resolve_state_dir().resolve()),
    ]
    env = {
        "AGENT_VALIDATION_MODE": settings.effective_validation_mode.value,
        "AGENT_STAGING_ROOT": str(settings.resolve_staging_root().resolve()),
        "AGENT_APPLY_MINIMUM_ASSURANCE": settings.apply_minimum_assurance.value,
        "AGENT_MCP_TRUSTED_LOCAL_READS": str(settings.mcp_trusted_local_reads).lower(),
        "AGENT_TRUST_ROOT": str(
            (settings.trust_root or Path.home() / ".agent-platform" / "trust").resolve()
        ),
    }
    if settings.validation_image:
        env["AGENT_VALIDATION_IMAGE"] = settings.validation_image
    if settings.native_toolchain_root:
        env["AGENT_NATIVE_TOOLCHAIN_ROOT"] = str(settings.native_toolchain_root.resolve())
    if settings.native_dependencies_root:
        env["AGENT_NATIVE_DEPENDENCIES_ROOT"] = str(settings.native_dependencies_root.resolve())
    if settings.native_browser_path:
        env["AGENT_NATIVE_BROWSER_PATH"] = str(settings.native_browser_path.resolve())
    if settings.browser_validation_plan:
        env["AGENT_BROWSER_VALIDATION_PLAN"] = str(settings.browser_validation_plan.resolve())
    env["AGENT_BROWSER_REVIEW_MODE"] = settings.browser_review_mode
    env["AGENT_BROWSER_PROVIDER_EXPORT"] = str(settings.browser_provider_export).lower()
    from migration_agent.adapters.visual_specialist import provider_disclosure

    disclosure = provider_disclosure(settings)
    if disclosure is not None:
        env["AGENT_RUNTIME_PROVIDER"] = disclosure.provider
        env["AGENT_RUNTIME_MODEL"] = disclosure.model
    entry: dict[str, object] = {
        "command": str(Path(sys.executable).absolute()),
        "args": args,
        "env": env,
    }
    if client == "codex":
        entry["startup_timeout_sec"] = 30
        entry["tool_timeout_sec"] = 60
    preview = SetupPreview(client=client, config_path=str(target), server_name=name, entry=entry)
    if not write:
        return preview
    if target.exists() and target.stat().st_size > 1048576:
        raise ValueError("CONFIG_TOO_LARGE: configuration exceeds safe update budget.")
    before = target.read_bytes() if target.exists() else None
    text = (before or b"").decode("utf-8")
    if RedactionPolicy().contains_secret(text):
        raise ValueError(
            "CONFIG_PROTECTED: use a separate credential-free config or edit manually."
        )
    if client == "codex":
        parsed = tomllib.loads(text)
        existing = parsed.get("mcp_servers", {}).get(name)
        if existing is not None:
            if existing == entry:
                return preview.model_copy(update={"status": "UNCHANGED"})
            raise ValueError(
                "ENTRY_EXISTS: review the existing entry before replacing it manually."
            )
        rendered = f"\n[mcp_servers.{name}]\n"
        rendered += f"command = {json.dumps(entry['command'])}\n"
        rendered += f"args = {json.dumps(args)}\nstartup_timeout_sec = 30\ntool_timeout_sec = 60\n"
        rendered += f"[mcp_servers.{name}.env]\n"
        for key, value in sorted(env.items()):
            rendered += f"{key} = {json.dumps(value)}\n"
        after = (text + rendered).encode()
        tomllib.loads(after.decode())
    else:
        parsed = json.loads(text) if text.strip() else {}
        if not isinstance(parsed, dict) or not isinstance(parsed.get("mcpServers", {}), dict):
            raise ValueError("CONFIG_INVALID: expected an object containing mcpServers.")
        servers = parsed.setdefault("mcpServers", {})
        if servers.get(name) == entry:
            return preview.model_copy(update={"status": "UNCHANGED"})
        servers[name] = entry
        after = (json.dumps(parsed, indent=2, ensure_ascii=False) + "\n").encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    from migration_agent.adapters.apply_lock import ExclusiveApplyLock

    lock_id = hashlib.sha256(str(target).encode()).hexdigest()
    backup = None
    with ExclusiveApplyLock(target.parent / ".migration-agent-config-locks").acquire(lock_id):
        current = target.read_bytes() if target.exists() else None
        if current != before:
            raise ValueError("CONFIG_CHANGED: preview again after the concurrent update.")
        if before is not None:
            backup = target.with_name(f"{target.name}.backup-{uuid.uuid4().hex}")
            with backup.open("xb") as handle:
                handle.write(before)
                handle.flush()
                os.fsync(handle.fileno())
            backup.chmod(target.stat().st_mode & 0o777)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(after)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(target.stat().st_mode & 0o777 if target.exists() else 0o600)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return preview.model_copy(
        update={"status": "WRITTEN", "backup_path": str(backup) if backup else None}
    )


def register_setup_cli(app: typer.Typer) -> None:
    @app.command("setup")
    def setup(
        client: Annotated[str, typer.Option("--client")],
        project_root: Annotated[Path, typer.Option("--project-root")],
        config_path: Annotated[Path | None, typer.Option("--config")] = None,
        state_dir: Annotated[Path | None, typer.Option("--state-dir")] = None,
        staging_root: Annotated[Path | None, typer.Option("--staging-root")] = None,
        write: Annotated[bool, typer.Option("--write")] = False,
    ) -> None:
        """Preview a local client entry; --write performs an atomic update with backup."""
        settings = Settings()
        settings = settings.model_copy(
            update={
                "state_dir": settings.resolve_state_dir(state_dir),
                "staging_root": settings.resolve_staging_root(staging_root),
            }
        )
        try:
            result = setup_client(client, project_root, settings, config_path, write)
            typer.echo(result.model_dump_json(indent=2))
        except (ValueError, OSError) as error:
            from migration_agent.adapters.workflow_cli import emit_error

            emit_error(error)
            raise typer.Exit(2) from error
