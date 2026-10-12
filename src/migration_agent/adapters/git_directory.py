"""Bounded read-only provider APIs through installed authenticated gh/glab clients."""

import json
import os
import shutil
import subprocess
import time
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import quote

from migration_agent.domain.access import GitAccount
from migration_agent.domain.git_directory import (
    GitDirectoryMember,
    GitDirectoryRequest,
    GitDirectoryResult,
)

_deadline: ContextVar[float | None] = ContextVar("git_directory_deadline", default=None)


class ProviderGitDirectory:
    def __init__(self, excluded_roots: tuple[Path, ...]) -> None:
        self.excluded_roots = tuple(p.resolve() for p in excluded_roots)

    def _response(self, request: GitDirectoryRequest, page: int | None) -> object:
        name = "gh" if request.provider == "github" else "glab"
        executable = shutil.which(name)
        if not executable:
            raise ValueError("GIT_PROVIDER_CLIENT_REQUIRED: install and authenticate gh/glab.")
        path = Path(executable).resolve()
        if any(path.is_relative_to(root) for root in self.excluded_roots):
            raise ValueError(
                "EXECUTABLE_UNTRUSTED: provider clients cannot come from project directories."
            )
        if request.provider == "github":
            if len(request.repository.split("/")) != 2:
                raise ValueError("GIT_REPOSITORY_INVALID: GitHub requires owner/repository.")
            endpoint = (
                f"repos/{request.repository}/collaborators?affiliation=all&per_page=100&page={page}"
            )
            if page is None:
                endpoint = f"repos/{request.repository}"
        else:
            endpoint = (
                f"projects/{quote(request.repository, safe='')}/members/all"
                f"?per_page=100&page={page}"
            )
            if page is None:
                endpoint = f"projects/{quote(request.repository, safe='')}"
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "HOME",
                "USERPROFILE",
                "APPDATA",
                "XDG_CONFIG_HOME",
                "LOCALAPPDATA",
            }
        }
        env.update(GH_PROMPT_DISABLED="1", GLAB_PROMPT_DISABLED="1", NO_COLOR="1")
        try:
            deadline = _deadline.get()
            remaining = 20.0 if deadline is None else deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError(
                    "GIT_DIRECTORY_TIMEOUT: total directory deadline exceeded; refresh and retry."
                )
            result = subprocess.run(
                [str(path), "api", "--hostname", request.host, "--method", "GET", endpoint],
                cwd=path.parent,
                capture_output=True,
                shell=False,
                env=env,
                timeout=min(20.0, remaining),
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError(
                "GIT_DIRECTORY_UNAVAILABLE: provider client failed or exceeded th"
                "e total deadline; retry the directory fetch."
            ) from None
        if result.returncode:
            raise ValueError("GIT_DIRECTORY_DENIED: check login, membership and read permissions.")
        if len(result.stdout) > 1_000_000:
            raise ValueError(
                "GIT_DIRECTORY_TOO_LARGE: provider response exceeds the directory budget."
            )
        return json.loads(result.stdout)

    def _page(self, request: GitDirectoryRequest, page: int) -> list[dict[str, object]]:
        data = self._response(request, page)
        if (
            not isinstance(data, list)
            or len(data) > 100
            or any(not isinstance(item, dict) for item in data)
        ):
            raise ValueError(
                "GIT_DIRECTORY_INVALID: provider returned an incompatible member page."
            )
        return data

    def members(self, request: GitDirectoryRequest) -> GitDirectoryResult:
        token = _deadline.set(time.monotonic() + 20)
        try:
            result = self._members(request)
            if time.monotonic() >= (_deadline.get() or 0):
                raise ValueError(
                    "GIT_DIRECTORY_TIMEOUT: refresh and retry the bounded directory fetch."
                )
            return result
        finally:
            _deadline.reset(token)

    def _members(self, request: GitDirectoryRequest) -> GitDirectoryResult:
        request = GitDirectoryRequest.model_validate_json(request.model_dump_json())
        project = self._response(request, None)
        if not isinstance(project, dict) or type(project.get("id")) is not int:
            raise ValueError("GIT_REPOSITORY_INVALID: stable repository identity is required.")
        repository_id = str(project["id"])
        members: dict[str, GitDirectoryMember] = {}
        for page in range(1, 12):
            rows = self._page(request, page)
            for row in rows:
                account_id = row.get("id")
                login = row.get("login" if request.provider == "github" else "username")
                if type(account_id) is not int or not isinstance(login, str):
                    raise ValueError(
                        "GIT_DIRECTORY_INVALID: stable account ID and login are required."
                    )
                role = (
                    row.get("role_name")
                    if request.provider == "github"
                    else row.get("access_level")
                )
                if not isinstance(role, (str, int)) or isinstance(role, bool):
                    raise ValueError(
                        "GIT_DIRECTORY_INVALID: effective provider role is unavailable."
                    )
                if request.provider == "gitlab":
                    if not isinstance(role, int):
                        raise ValueError(
                            "GIT_DIRECTORY_INVALID: GitLab access level must be an integer."
                        )
                    role = {
                        0: "No access",
                        5: "Minimal access",
                        10: "Guest",
                        15: "Planner",
                        20: "Reporter",
                        25: "Security Manager",
                        30: "Developer",
                        40: "Maintainer",
                        50: "Owner",
                    }.get(role, f"Access level {role}")
                account = GitAccount(
                    provider=request.provider,
                    host=request.host,
                    account_id=str(account_id),
                    login=login,
                )
                member = GitDirectoryMember(
                    account=account,
                    git_role=str(role),
                    state="active" if row.get("state", "active") == "active" else "blocked",
                    expires_at=str(row["expires_at"]) if row.get("expires_at") else None,
                )
                if account.identity in members and members[account.identity] != member:
                    raise ValueError(
                        "GIT_DIRECTORY_CHANGED: refresh the inconsistent membership page."
                    )
                members[account.identity] = member
                if len(members) > 1000:
                    raise ValueError(
                        "GIT_DIRECTORY_TOO_LARGE: import is limited to 1000 effective members."
                    )
            if len(rows) < 100:
                return GitDirectoryResult(
                    request=request,
                    repository_id=repository_id,
                    members=tuple(members[key] for key in sorted(members)),
                )
        raise ValueError("GIT_DIRECTORY_INCOMPLETE: membership pagination exceeded its bound.")
