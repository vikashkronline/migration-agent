"""Read-only provider directory boundary."""

from typing import Protocol

from migration_agent.domain.git_directory import GitDirectoryRequest, GitDirectoryResult


class GitDirectoryPort(Protocol):
    def members(self, request: GitDirectoryRequest) -> GitDirectoryResult: ...
