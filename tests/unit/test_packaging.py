"""Unit tests for release manifest generation, prompt cloaking, and distribution packaging."""

from pathlib import Path

from migration_agent.packaging import (
    cloak_prompt_string,
    decloak_prompt_string,
    generate_release_manifest,
    get_binary_packaging_spec,
    verify_release_manifest,
)


def test_prompt_cloaking_and_decloaking() -> None:
    prompt = "System prompt with sensitive heuristic rules and intellectual property."
    cloaked = cloak_prompt_string(prompt)
    assert cloaked != prompt
    assert isinstance(cloaked, str)

    decloaked = decloak_prompt_string(cloaked)
    assert decloaked == prompt


def test_release_manifest_generation_and_verification(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    # Create dummy wheel and binary files
    wheel_file = dist_dir / "migration_agent-0.1.0-py3-none-any.whl"
    wheel_file.write_bytes(b"PK\x03\x04dummy wheel content")

    bin_file = dist_dir / "migration-agent.exe"
    bin_file.write_bytes(b"MZ\x90\x00dummy windows executable")

    manifest = generate_release_manifest(
        version="0.1.0",
        dist_dir=dist_dir,
        release_channel="stable",
    )
    assert manifest.version == "0.1.0"
    assert len(manifest.assets) == 2

    # Check asset classifications
    wheel_asset = next(a for a in manifest.assets if a.name.endswith(".whl"))
    assert wheel_asset.content_type == "wheel"
    assert len(wheel_asset.sha256) == 64

    bin_asset = next(a for a in manifest.assets if a.name.endswith(".exe"))
    assert bin_asset.content_type == "binary"
    assert bin_asset.platform == "windows-x86_64"

    # Verify manifest against intact dist_dir
    assert verify_release_manifest(manifest, dist_dir) is True

    # Tamper with an asset and verify failure
    bin_file.write_bytes(b"tampered content")
    assert verify_release_manifest(manifest, dist_dir) is False


def test_binary_packaging_spec(tmp_path: Path) -> None:
    spec = get_binary_packaging_spec(tmp_path)
    assert spec["binary_name"] == "migration-agent"
    assert "migration_agent.adapters.control_api" in spec["hidden_imports"]
    assert spec["enable_lto"] is True
