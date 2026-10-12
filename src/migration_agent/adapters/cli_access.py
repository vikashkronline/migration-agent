"""Executable CLI capability coverage, independent of actor labels."""

import json
from pathlib import Path
from typing import Any

import typer
from typer._click.core import Context
from typer.core import TyperCommand

from migration_agent.adapters.access_runtime import ProjectAuthorization
from migration_agent.config import Settings
from migration_agent.domain.redaction import RedactionPolicy

CLI_ACTIONS: dict[str, tuple[str, ...]] = {
    "inventory": ("project.read",),
    "graph": ("project.read",),
    "fullstack": ("project.read",),
    "analyze": ("analysis.submit", "provider.use"),
    "plan create": ("plan.submit", "provider.use"),
    "plan show": ("plan.read",),
    "plan approve": ("approval.sign",),
    "plan reject": ("approval.sign",),
    "preview": ("changeset.read",),
    "stage": ("changeset.stage",),
    "apply": ("changeset.apply",),
    "migrate": (
        "plan.submit",
        "changeset.stage",
        "validation.run",
        "changeset.apply",
        "provider.use",
    ),
    "validate": ("validation.run",),
    "run start": ("plan.submit", "validation.run", "changeset.apply", "provider.use"),
    "run list": ("run.read",),
    "run show": ("run.read",),
    "run resume": ("changeset.apply", "validation.run", "provider.use"),
    "ui": ("project.read",),
    "ask": ("project.read", "provider.use"),
    "challenge record": ("knowledge.write",),
    "challenge list": ("project.read",),
    "solution record": ("knowledge.write",),
    "solution list": ("project.read",),
    "learning approve": ("knowledge.approve",),
    "learning list": ("project.read",),
    "decision record": ("knowledge.write",),
    "decision list": ("project.read",),
    "validation standards": ("evidence.read",),
    "validation browser-request": ("evidence.read",),
    "validation browser-submit": ("validation.run",),
    "validation authorize": ("execution.consent",),
    "validation revoke": ("execution.consent",),
    "validation repair": ("repair.submit",),
    "validation status": ("project.read",),
    "submit-repair": ("repair.submit",),
    "recover": ("changeset.apply",),
    "review": ("approval.request",),
    "approve": ("approval.sign",),
}
PLATFORM_ACTIONS = frozenset({"doctor", "eval", "init", "adopt"})
PLATFORM_GROUPS = frozenset({"package", "mcp", "access", "config"})


class AuthorizedCommand(TyperCommand):
    def invoke(self, ctx: Context) -> Any:
        names = []
        parent: Context | None = ctx
        while parent and parent.parent:
            names.append(parent.info_name or "")
            parent = parent.parent
        action = " ".join(reversed(names))
        try:
            if action not in PLATFORM_ACTIONS and action.split(" ")[0] not in PLATFORM_GROUPS:
                capabilities = CLI_ACTIONS.get(action)
                if capabilities is None:
                    raise ValueError(
                        "ACCESS_ACTION_UNREGISTERED: command lacks a capability mapping."
                    )
                if action == "migrate" and ctx.params.get("dry_run"):
                    capabilities = tuple(cap for cap in capabilities if cap != "changeset.apply")
                root = next(
                    (
                        Path(ctx.params[name])
                        for name in (
                            "path",
                            "project_root",
                            "source_root",
                            "target_root",
                            "source",
                            "root",
                        )
                        if isinstance(ctx.params.get(name), (str, Path))
                    ),
                    Path.cwd(),
                )
                values = {
                    name: ctx.params[name]
                    for name in ("state_dir", "trust_root", "staging_root")
                    if ctx.params.get(name) is not None
                }
                if ctx.params.get("trust_dir") is not None:
                    values["trust_root"] = ctx.params["trust_dir"]
                authorization = ProjectAuthorization(root, Settings(**values))
                for capability in capabilities:
                    authorization.require(capability)
            return super().invoke(ctx)
        except (ValueError, OSError) as error:
            typer.echo(
                json.dumps(
                    {"status": "blocked", "error": RedactionPolicy().redact_text(str(error))[:512]}
                ),
                err=True,
            )
            raise typer.Exit(2) from error


def secure_cli(app: typer.Typer) -> None:
    for command in app.registered_commands:
        command.cls = AuthorizedCommand
    for group in app.registered_groups:
        if group.typer_instance is not None:
            secure_cli(group.typer_instance)
