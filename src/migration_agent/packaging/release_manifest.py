"""Release manifest generation and checksum verification for distribution packaging."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ReleaseAsset(BaseModel):
    """Metadata and SHA-256 integrity digest for a distributable binary or wheel artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    platform: str = Field(min_length=1)  # "windows-x86_64", "linux-x86_64", "darwin-arm64", "any"
    content_type: str = Field(min_length=1)  # "binary", "wheel", "source_archive"
    signature_slot: str | None = None


class ReleaseManifest(BaseModel):
    """Cryptographically bound release manifest detailing all published assets and checksums."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    version: str = Field(min_length=1)
    release_channel: str = Field(default="stable")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    assets: list[ReleaseAsset] = Field(default_factory=list)


def compute_file_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hexadecimal hash over raw file bytes."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_release_manifest(
    version: str,
    dist_dir: Path,
    release_channel: str = "stable",
) -> ReleaseManifest:
    """Scan a distribution directory and produce a schema-versioned ReleaseManifest."""
    assets: list[ReleaseAsset] = []
    if dist_dir.is_dir():
        for asset_path in sorted(dist_dir.iterdir()):
            if asset_path.is_file() and not asset_path.name.endswith(".json"):
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

                assets.append(
                    ReleaseAsset(
                        name=name,
                        size_bytes=size,
                        sha256=sha256_hash,
                        platform=platform,
                        content_type=content_type,
                    )
                )

    return ReleaseManifest(
        version=version,
        release_channel=release_channel,
        assets=assets,
    )


def verify_release_manifest(manifest: ReleaseManifest, dist_dir: Path) -> bool:
    """Verify that all assets cited in a ReleaseManifest exist and match their SHA-256 digest."""
    for asset in manifest.assets:
        asset_file = dist_dir / asset.name
        if not asset_file.is_file():
            return False
        if compute_file_sha256(asset_file) != asset.sha256:
            return False
        if asset_file.stat().st_size != asset.size_bytes:
            return False
    return True
