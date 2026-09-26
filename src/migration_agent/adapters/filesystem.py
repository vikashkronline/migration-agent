"""Cross-platform, read-only repository inspection."""

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from migration_agent.domain import (
    ExclusionSummary,
    FileCategory,
    InspectedTextFile,
    RepositoryDescriptor,
    RepositorySnapshot,
)
from migration_agent.ports import InspectionPolicy

_MANIFEST_NAMES = {"bower.json", "package.json"}
_LOCKFILE_NAMES = {
    "bun.lock",
    "bun.lockb",
    "npm-shrinkwrap.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
_BUILD_CONFIG_NAMES = {
    ".babelrc",
    "angular.json",
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
    "dockerfile",
    "ember-cli-build.js",
    "jsconfig.json",
    "tsconfig.json",
}
_BUILD_CONFIG_PREFIXES = (
    "babel.config.",
    "eslint.config.",
    "rollup.config.",
    "vite.config.",
    "webpack.config.",
)
_SOURCE_SUFFIXES = {".cjs", ".js", ".jsx", ".mjs", ".py", ".sql", ".ts", ".tsx"}
_TEMPLATE_SUFFIXES = {".hbs", ".html"}
_STYLE_SUFFIXES = {".css", ".less", ".sass", ".scss"}
_SECRET_NAMES = {
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}
_SECRET_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}


@dataclass
class _ExclusionCounters:
    binary_files: int = 0
    ignored_entries: int = 0
    outside_root_entries: int = 0
    oversized_files: int = 0
    secret_like_files: int = 0
    symlink_entries: int = 0
    unreadable_entries: int = 0

    def freeze(self) -> ExclusionSummary:
        return ExclusionSummary(
            binary_files=self.binary_files,
            ignored_entries=self.ignored_entries,
            outside_root_entries=self.outside_root_entries,
            oversized_files=self.oversized_files,
            secret_like_files=self.secret_like_files,
            symlink_entries=self.symlink_entries,
            unreadable_entries=self.unreadable_entries,
        )


class SafeFilesystemInspector:
    """Collect eligible text files without following filesystem links."""

    def inspect(self, root: Path, policy: InspectionPolicy) -> RepositorySnapshot:
        root_resolved = root.expanduser().resolve(strict=True)
        if not root_resolved.is_dir():
            raise ValueError("repository root must be a directory")

        counters = _ExclusionCounters()
        files: list[InspectedTextFile] = []
        ignored_names = {name.casefold() for name in policy.ignored_directory_names}
        self._walk(root_resolved, root_resolved, policy, ignored_names, counters, files)

        return RepositorySnapshot(
            repository=RepositoryDescriptor(name=root_resolved.name, root=root_resolved),
            files=tuple(sorted(files, key=lambda item: item.path)),
            exclusions=counters.freeze(),
        )

    def _walk(
        self,
        directory: Path,
        root: Path,
        policy: InspectionPolicy,
        ignored_names: set[str],
        counters: _ExclusionCounters,
        files: list[InspectedTextFile],
    ) -> None:
        try:
            entries = sorted(
                os.scandir(directory), key=lambda entry: (entry.name.casefold(), entry.name)
            )
        except OSError:
            counters.unreadable_entries += 1
            return

        for entry in entries:
            entry_path = Path(entry.path)
            try:
                if self._is_link_like(entry_path, entry):
                    counters.symlink_entries += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name.casefold() in ignored_names:
                        counters.ignored_entries += 1
                        continue
                    if not self._is_contained(root, entry_path):
                        counters.outside_root_entries += 1
                        continue
                    self._walk(entry_path, root, policy, ignored_names, counters, files)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                counters.unreadable_entries += 1
                continue

            relative_path = entry_path.relative_to(root)
            if self._is_secret_like(relative_path):
                counters.secret_like_files += 1
                continue

            category = self._classify(relative_path)
            if category is None:
                continue
            if not self._is_contained(root, entry_path):
                counters.outside_root_entries += 1
                continue

            inspected = self._read_text_file(entry_path, relative_path, category, policy, counters)
            if inspected is not None:
                files.append(inspected)

    @staticmethod
    def _is_link_like(path: Path, entry: os.DirEntry[str]) -> bool:
        if entry.is_symlink():
            return True
        if path.is_junction():
            return True
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        return bool(attributes & reparse_flag)

    @staticmethod
    def _is_contained(root: Path, path: Path) -> bool:
        try:
            path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError):
            return False
        return True

    @staticmethod
    def _is_secret_like(relative_path: Path) -> bool:
        name = relative_path.name.casefold()
        if name == ".env" or name.startswith(".env."):
            return True
        if name in _SECRET_NAMES or relative_path.suffix.casefold() in _SECRET_SUFFIXES:
            return True
        return name.startswith("secrets.")

    @staticmethod
    def _classify(relative_path: Path) -> FileCategory | None:
        name = relative_path.name.casefold()
        suffix = relative_path.suffix.casefold()
        parts = {part.casefold() for part in relative_path.parts}
        stem = relative_path.stem.casefold()

        if name in _MANIFEST_NAMES:
            return FileCategory.MANIFEST
        if name in _LOCKFILE_NAMES:
            return FileCategory.LOCKFILE
        if (
            name in _BUILD_CONFIG_NAMES
            or name.startswith(_BUILD_CONFIG_PREFIXES)
            or name.endswith("dockerfile")
        ):
            return FileCategory.BUILD_CONFIG
        if (
            "tests" in parts or "test" in parts or "__tests__" in parts
        ) and suffix in _SOURCE_SUFFIXES | _TEMPLATE_SUFFIXES:
            return FileCategory.TEST
        if (stem.endswith(".test") or stem.endswith(".spec")) and suffix in _SOURCE_SUFFIXES:
            return FileCategory.TEST
        if suffix in _SOURCE_SUFFIXES:
            return FileCategory.SOURCE
        if suffix in _TEMPLATE_SUFFIXES:
            return FileCategory.TEMPLATE
        if suffix in _STYLE_SUFFIXES:
            return FileCategory.STYLE
        return None

    @staticmethod
    def _read_text_file(
        path: Path,
        relative_path: Path,
        category: FileCategory,
        policy: InspectionPolicy,
        counters: _ExclusionCounters,
    ) -> InspectedTextFile | None:
        try:
            size_bytes = path.stat(follow_symlinks=False).st_size
            if size_bytes > policy.max_text_file_bytes:
                counters.oversized_files += 1
                return None

            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as file_handle:
                data = file_handle.read(policy.max_text_file_bytes + 1)
        except OSError:
            counters.unreadable_entries += 1
            return None

        if len(data) > policy.max_text_file_bytes:
            counters.oversized_files += 1
            return None
        if b"\x00" in data[:8192]:
            counters.binary_files += 1
            return None
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            counters.binary_files += 1
            return None

        return InspectedTextFile(
            path=relative_path.as_posix(),
            category=category,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            content=content,
        )
