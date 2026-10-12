"""Deterministic signed digests for governance files that influence execution."""

import hashlib
import json
import re
from pathlib import Path

from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.ports.filesystem import InspectionPolicy

SECURITY_FILES = (
    ".agent/policy.json",
    ".agent/config.json",
    ".agent/architecture.json",
    ".agent/rules.json",
    ".agent/access/roles.json",
    ".agent/access/principals.json",
)
SECURITY_FOLDERS = (".agent/rules", ".agent/workflows")


def _unique_json(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("RULES_JSON_INVALID: duplicate security configuration key.")
        result[key] = value
    return result


def rule_text_digest(path: str, text: str) -> str:
    if path.endswith(".json"):
        return compute_canonical_digest(json.loads(text, object_pairs_hook=_unique_json))
    return "sha256:" + hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def governance_rule_digests(root: Path) -> dict[str, str]:
    paths = set(SECURITY_FILES)
    architecture = validate_repository_path(root, ".agent/architecture.json")
    if architecture.exists():
        from migration_agent.domain.stack import ArchitectureManifest

        manifest = ArchitectureManifest.model_validate_json(
            read_repository_text(root, ".agent/architecture.json")
        )
        for decision_path in manifest.decision_digests:
            if not re.fullmatch(r"\.agent/decisions/[A-Za-z0-9_-]+\.md", decision_path):
                raise ValueError("ARCHITECTURE_INVALID: sealed decisions need bounded safe paths.")
            paths.add(decision_path)
    for relative in SECURITY_FOLDERS:
        directory = validate_repository_path(root, relative)
        if directory.exists():
            if directory.is_symlink() or directory.is_junction():
                raise ValueError("RULES_UNSAFE: governance rule folders cannot be links.")
            for path in directory.rglob("*"):
                if path.is_file():
                    paths.add(path.relative_to(root).as_posix())
                if len(paths) > 512:
                    raise ValueError("RULES_TOO_LARGE: signed governance is limited to 512 files.")
    result = {}
    total = 0
    for relative in sorted(paths):
        path = validate_repository_path(root, relative)
        if path.exists():
            if not path.is_file() or path.stat().st_size > 1_000_000:
                raise ValueError("RULES_TOO_LARGE: security rules need bounded regular files.")
            data = read_repository_text(
                root, relative, policy=InspectionPolicy(max_text_file_bytes=1_000_000)
            ).encode("utf-8")
            total += len(data)
            if total > 2_000_000:
                raise ValueError("RULES_TOO_LARGE: total governance rule budget exceeded.")
            result[relative] = rule_text_digest(relative, data.decode("utf-8"))
    return result
