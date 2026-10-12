"""Public Git membership projections; provider roles never grant agent authority."""

from typing import Literal

from pydantic import Field

from migration_agent.domain.access import AccessModel, GitAccount


class GitDirectoryRequest(AccessModel):
    provider: Literal["github", "gitlab"]
    host: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,252}$")
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+){1,8}$", max_length=256)


class GitDirectoryMember(AccessModel):
    account: GitAccount
    git_role: str = Field(min_length=1, max_length=128)
    membership_source: Literal["effective", "direct"] = "effective"
    state: Literal["active", "blocked"] = "active"
    expires_at: str | None = Field(default=None, max_length=64)


class GitDirectoryResult(AccessModel):
    request: GitDirectoryRequest
    repository_id: str = Field(pattern=r"^[0-9]{1,24}$")
    members: tuple[GitDirectoryMember, ...] = Field(max_length=1000)
    complete: Literal[True] = True
    message: str = (
        "Git roles are informational. Select explicit agent roles; "
        "imported users remain pending enrollment."
    )
