"""Release manifest generation, cryptographic binding, and verification."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from migration_agent.adapters.trust_store import CryptoSignatureVerifierAdapter
from migration_agent.domain.canonical import compute_canonical_digest
from migration_agent.domain.trust import AuthorityKey


class ReleaseAsset(BaseModel):
    """Metadata and SHA-256 integrity digest for a distributable binary or wheel artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    platform: str = Field(min_length=1)  # "windows-x86_64", "linux-x86_64", "darwin-arm64", "any"
    content_type: str = Field(min_length=1)  # "binary", "wheel", "source_archive", "signature"
    signature_slot: str | None = None


class ReleaseManifest(BaseModel):
    """Cryptographically bound release manifest detailing all published assets and checksums."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    version: str = Field(min_length=1)
    release_channel: str = Field(default="stable")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    canonical_cli: str = "agent"
    cli_aliases: list[str] = Field(default_factory=lambda: ["migration-agent"])
    manifest_digest: str | None = None
    signature: str | None = None
    key_id: str | None = None
    assets: list[ReleaseAsset] = Field(default_factory=list)


def compute_file_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hexadecimal hash over raw file bytes."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_manifest_digest(manifest_data: ReleaseManifest | dict[str, Any]) -> str:
    """Compute the RFC 8785 canonical digest over manifest content excluding signatures."""
    if isinstance(manifest_data, ReleaseManifest):
        dump = manifest_data.model_dump(mode="json")
    else:
        dump = dict(manifest_data)

    # Exclude dynamic signature and manifest_digest fields from digest calculation
    dump.pop("manifest_digest", None)
    dump.pop("signature", None)
    dump.pop("key_id", None)

    return compute_canonical_digest(dump)


def generate_release_manifest(
    version: str,
    dist_dir: Path,
    release_channel: str = "stable",
    canonical_cli: str = "agent",
    cli_aliases: list[str] | None = None,
    signing_key: str | None = None,
    key_id: str | None = None,
    algorithm: str = "ed25519",
) -> ReleaseManifest:
    """Scan a distribution directory and produce a cryptographically bound ReleaseManifest."""
    assets: list[ReleaseAsset] = []
    resolved_aliases = cli_aliases if cli_aliases is not None else ["migration-agent"]

    if dist_dir.is_dir():
        for asset_path in sorted(dist_dir.iterdir()):
            is_valid_asset = (
                asset_path.is_file()
                and not asset_path.name.endswith(".json")
                and not asset_path.name.endswith(".sig")
            )
            if is_valid_asset:
                sha256_hash = compute_file_sha256(asset_path)
                size = asset_path.stat().st_size
                name = asset_path.name

                platform = "any"
                if "win" in name or name.endswith(".exe"):
                    platform = "windows-x86_64"
                elif "linux" in name:
                    platform = "linux-x86_64"
                elif "darwin" in name or "macos" in name:
                    platform = "darwin-arm64"

                content_type = "binary"
                if name.endswith(".whl"):
                    content_type = "wheel"
                elif name.endswith(".tar.gz") or name.endswith(".zip"):
                    content_type = "source_archive"
                elif name.endswith(".asc") or name.endswith(".sig"):
                    content_type = "signature"

                assets.append(
                    ReleaseAsset(
                        name=name,
                        size_bytes=size,
                        sha256=sha256_hash,
                        platform=platform,
                        content_type=content_type,
                    )
                )

    preliminary_manifest = ReleaseManifest(
        version=version,
        release_channel=release_channel,
        canonical_cli=canonical_cli,
        cli_aliases=resolved_aliases,
        assets=assets,
    )
    digest = compute_manifest_digest(preliminary_manifest)

    sig: str | None = None
    if signing_key is not None:
        verifier = CryptoSignatureVerifierAdapter()
        sig = verifier.sign(payload_digest=digest, private_key=signing_key, algorithm=algorithm)

    return ReleaseManifest(
        version=version,
        release_channel=release_channel,
        created_at=preliminary_manifest.created_at,
        canonical_cli=canonical_cli,
        cli_aliases=resolved_aliases,
        manifest_digest=digest,
        signature=sig,
        key_id=key_id,
        assets=assets,
    )


def verify_release_manifest(
    manifest: ReleaseManifest,
    dist_dir: Path,
    authority_key: AuthorityKey | None = None,
) -> bool:
    """Verify all assets in ReleaseManifest exist, match SHA-256, and signature is valid."""
    # 1. Verify manifest digest integrity
    recomputed_digest = compute_manifest_digest(manifest)
    if manifest.manifest_digest is not None and manifest.manifest_digest != recomputed_digest:
        return False

    # 2. Verify individual assets
    for asset in manifest.assets:
        asset_file = dist_dir / asset.name
        if not asset_file.is_file():
            return False
        if compute_file_sha256(asset_file) != asset.sha256:
            return False
        if asset_file.stat().st_size != asset.size_bytes:
            return False

    # 3. Cryptographic signature check if authority key is provided
    if authority_key is not None and manifest.signature is not None:
        verifier = CryptoSignatureVerifierAdapter()
        result = verifier.verify(
            payload_digest=recomputed_digest,
            signature=manifest.signature,
            authority_key=authority_key,
        )
        if not result.verified:
            return False

    return True


def save_release_manifest(manifest: ReleaseManifest, target_file: Path) -> Path:
    """Save a ReleaseManifest to a formatted JSON file."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return target_file


def load_release_manifest(source_file: Path) -> ReleaseManifest:
    """Load a ReleaseManifest from a JSON file."""
    if not source_file.is_file():
        raise FileNotFoundError(f"Release manifest file not found: {source_file}")
    data = json.loads(source_file.read_text(encoding="utf-8"))
    return ReleaseManifest.model_validate(data)
