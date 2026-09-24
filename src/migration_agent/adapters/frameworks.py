"""Small evidence-based framework detection adapters."""

import json
import re
from collections.abc import Mapping
from typing import cast

from migration_agent.domain import (
    FileCategory,
    FrameworkEvidence,
    FrameworkFingerprint,
    InspectedTextFile,
    RepositorySnapshot,
    ValidationCommand,
    ValidationProfile,
)

_ANGULAR_STANDALONE_PATTERN = re.compile(r"\bstandalone\s*:\s*true\b")


def _manifest_dependencies(file: InspectedTextFile) -> Mapping[str, object]:
    try:
        parsed = json.loads(file.content)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}

    dependencies: dict[str, object] = {}
    manifest = cast(dict[str, object], parsed)
    for section_name in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        section = manifest.get(section_name)
        if isinstance(section, dict):
            dependencies.update(cast(dict[str, object], section))
    return dependencies


def _fingerprint(
    framework_id: str,
    evidence: list[FrameworkEvidence],
    *,
    threshold: float = 0.5,
) -> FrameworkFingerprint | None:
    confidence = round(min(sum(item.weight for item in evidence), 1.0), 2)
    if confidence < threshold:
        return None
    return FrameworkFingerprint(
        framework_id=framework_id,
        confidence=confidence,
        evidence=tuple(sorted(evidence, key=lambda item: (item.path, item.kind))),
    )


class EmberClassicAdapter:
    """Detect evidence consistent with an Ember Classic project layout."""

    @property
    def framework_id(self) -> str:
        return "ember-classic"

    def detect(self, snapshot: RepositorySnapshot) -> FrameworkFingerprint | None:
        evidence: list[FrameworkEvidence] = []
        manifests = [
            file
            for file in snapshot.files
            if file.category is FileCategory.MANIFEST and file.path.endswith("package.json")
        ]
        for manifest in manifests:
            dependencies = _manifest_dependencies(manifest)
            if "ember-source" in dependencies or "ember-cli" in dependencies:
                evidence.append(
                    FrameworkEvidence(
                        path=manifest.path,
                        kind="manifest_dependency",
                        description="Declares ember-source or ember-cli.",
                        weight=0.55,
                    )
                )
                break

        build_file = next(
            (file for file in snapshot.files if file.path.endswith("ember-cli-build.js")),
            None,
        )
        if build_file is not None:
            evidence.append(
                FrameworkEvidence(
                    path=build_file.path,
                    kind="build_configuration",
                    description="Contains an Ember CLI build configuration.",
                    weight=0.25,
                )
            )

        component = next(
            (
                file
                for file in snapshot.files
                if "/app/components/" in f"/{file.path}" and file.path.endswith(".js")
            ),
            None,
        )
        if component is not None:
            evidence.append(
                FrameworkEvidence(
                    path=component.path,
                    kind="classic_component_layout",
                    description="Uses the classic app/components JavaScript layout.",
                    weight=0.1,
                )
            )

        template = next(
            (
                file
                for file in snapshot.files
                if "/app/templates/components/" in f"/{file.path}" and file.path.endswith(".hbs")
            ),
            None,
        )
        if template is not None:
            evidence.append(
                FrameworkEvidence(
                    path=template.path,
                    kind="classic_template_layout",
                    description="Uses the classic app/templates/components layout.",
                    weight=0.1,
                )
            )

        return _fingerprint(self.framework_id, evidence)

    def get_validation_commands(self, profile: ValidationProfile) -> tuple[ValidationCommand, ...]:
        """Return allowlisted validation commands for Ember Classic."""
        if profile == ValidationProfile.TEST:
            return (
                ValidationCommand(
                    executable="npm",
                    args=("test",),
                    profile=ValidationProfile.TEST,
                ),
            )
        return ()


class AngularAdapter:
    """Detect evidence consistent with an Angular project."""

    @property
    def framework_id(self) -> str:
        return "angular"

    def detect(self, snapshot: RepositorySnapshot) -> FrameworkFingerprint | None:
        evidence: list[FrameworkEvidence] = []
        manifests = [
            file
            for file in snapshot.files
            if file.category is FileCategory.MANIFEST and file.path.endswith("package.json")
        ]
        for manifest in manifests:
            if "@angular/core" in _manifest_dependencies(manifest):
                evidence.append(
                    FrameworkEvidence(
                        path=manifest.path,
                        kind="manifest_dependency",
                        description="Declares @angular/core.",
                        weight=0.6,
                    )
                )
                break

        config = next(
            (file for file in snapshot.files if file.path.endswith("angular.json")),
            None,
        )
        if config is not None:
            evidence.append(
                FrameworkEvidence(
                    path=config.path,
                    kind="build_configuration",
                    description="Contains an Angular workspace configuration.",
                    weight=0.25,
                )
            )

        standalone_component = next(
            (
                file
                for file in snapshot.files
                if file.path.endswith(".ts") and _ANGULAR_STANDALONE_PATTERN.search(file.content)
            ),
            None,
        )
        if standalone_component is not None:
            evidence.append(
                FrameworkEvidence(
                    path=standalone_component.path,
                    kind="standalone_component",
                    description="Contains an Angular standalone component declaration.",
                    weight=0.15,
                )
            )

        return _fingerprint(self.framework_id, evidence)

    def get_validation_commands(self, profile: ValidationProfile) -> tuple[ValidationCommand, ...]:
        """Return allowlisted validation commands for Angular."""
        if profile == ValidationProfile.LINT:
            return (
                ValidationCommand(
                    executable="npm",
                    args=("run", "lint"),
                    profile=ValidationProfile.LINT,
                ),
            )
        if profile == ValidationProfile.TYPECHECK:
            return (
                ValidationCommand(
                    executable="npx",
                    args=("tsc", "--noEmit"),
                    profile=ValidationProfile.TYPECHECK,
                ),
            )
        if profile == ValidationProfile.TEST:
            return (
                ValidationCommand(
                    executable="npm",
                    args=("test", "--", "--watch=false", "--browsers=ChromeHeadless"),
                    profile=ValidationProfile.TEST,
                ),
            )
        if profile == ValidationProfile.BUILD:
            return (
                ValidationCommand(
                    executable="npx",
                    args=("ng", "build"),
                    profile=ValidationProfile.BUILD,
                ),
            )
        return ()
