"""Deterministic repository inventory application service."""

import fnmatch
import json
from pathlib import Path, PurePosixPath
from typing import cast

from migration_agent.domain import (
    Dependency,
    DependencyScope,
    InventoryFile,
    InventoryIssue,
    PackageBoundary,
    ProjectInventory,
    RepositorySnapshot,
)
from migration_agent.ports import (
    FilesystemInspectorPort,
    FrameworkAdapterRegistry,
    InspectionPolicy,
)

_DEPENDENCY_SECTIONS = {
    "dependencies": DependencyScope.RUNTIME,
    "devDependencies": DependencyScope.DEVELOPMENT,
    "optionalDependencies": DependencyScope.OPTIONAL,
    "peerDependencies": DependencyScope.PEER,
}


class InventoryService:
    """Build a stable inventory from filesystem and framework ports."""

    def __init__(
        self,
        filesystem: FilesystemInspectorPort,
        frameworks: FrameworkAdapterRegistry,
    ) -> None:
        self._filesystem = filesystem
        self._frameworks = frameworks

    def inventory(
        self,
        root: Path,
        *,
        policy: InspectionPolicy | None = None,
    ) -> ProjectInventory:
        snapshot = self._filesystem.inspect(root, policy or InspectionPolicy())
        dependencies, boundaries, issues = self._inspect_manifests(snapshot)
        files = tuple(
            InventoryFile(
                path=file.path,
                category=file.category,
                size_bytes=file.size_bytes,
                sha256=file.sha256,
            )
            for file in snapshot.files
        )

        return ProjectInventory(
            repository=snapshot.repository,
            files=files,
            dependencies=dependencies,
            package_boundaries=boundaries,
            frameworks=self._frameworks.detect(snapshot),
            exclusions=snapshot.exclusions,
            issues=issues,
        )

    @staticmethod
    def _inspect_manifests(
        snapshot: RepositorySnapshot,
    ) -> tuple[tuple[Dependency, ...], tuple[PackageBoundary, ...], tuple[InventoryIssue, ...]]:
        manifests: list[tuple[str, dict[str, object] | None]] = []
        issues: list[InventoryIssue] = []
        for file in snapshot.files:
            if not file.path.endswith("package.json"):
                continue
            try:
                parsed = json.loads(file.content)
            except json.JSONDecodeError:
                parsed = None
            if not isinstance(parsed, dict):
                issues.append(
                    InventoryIssue(
                        code="invalid_package_manifest",
                        path=file.path,
                        message="The package manifest is not a valid JSON object.",
                    )
                )
                manifests.append((file.path, None))
                continue
            manifests.append((file.path, cast(dict[str, object], parsed)))

        root_manifest = next((data for path, data in manifests if path == "package.json"), None)
        workspace_patterns = InventoryService._workspace_patterns(root_manifest)

        dependencies: list[Dependency] = []
        boundaries: list[PackageBoundary] = []
        for manifest_path, manifest in manifests:
            package_path = PurePosixPath(manifest_path).parent.as_posix()
            if package_path == ".":
                declared_workspace = False
            else:
                declared_workspace = any(
                    fnmatch.fnmatchcase(package_path, pattern) for pattern in workspace_patterns
                )
            boundaries.append(
                PackageBoundary(
                    path=package_path,
                    manifest_path=manifest_path,
                    declared_workspace=declared_workspace,
                )
            )

            if manifest is None:
                continue
            for section_name, scope in _DEPENDENCY_SECTIONS.items():
                section = manifest.get(section_name)
                if not isinstance(section, dict):
                    continue
                for name, version_spec in cast(dict[object, object], section).items():
                    if isinstance(name, str) and isinstance(version_spec, str):
                        dependencies.append(
                            Dependency(
                                name=name,
                                version_spec=version_spec,
                                scope=scope,
                                manifest_path=manifest_path,
                            )
                        )

        return (
            tuple(
                sorted(
                    dependencies,
                    key=lambda item: (item.manifest_path, item.scope.value, item.name),
                )
            ),
            tuple(sorted(boundaries, key=lambda item: (item.path, item.manifest_path))),
            tuple(sorted(issues, key=lambda item: (item.path, item.code))),
        )

    @staticmethod
    def _workspace_patterns(manifest: dict[str, object] | None) -> tuple[str, ...]:
        if manifest is None:
            return ()
        workspaces = manifest.get("workspaces")
        if isinstance(workspaces, dict):
            workspaces = cast(dict[str, object], workspaces).get("packages")
        if not isinstance(workspaces, list):
            return ()
        return tuple(sorted(item for item in workspaces if isinstance(item, str)))
