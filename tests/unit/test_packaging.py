"""Unit tests for release manifest generation, prompt cloaking, and distribution packaging."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from migration_agent.cli import app
from migration_agent.domain.security import SecurityConfigurationError
from migration_agent.domain.trust import AuthorityKey
from migration_agent.packaging import (
    cloak_prompt_string,
    create_binary_aliases,
    decloak_prompt_string,
    generate_pyinstaller_spec,
    generate_release_manifest,
    get_binary_packaging_spec,
    load_release_manifest,
    save_release_manifest,
    verify_binary_integrity,
    verify_release_manifest,
    write_pyinstaller_spec_file,
)

runner = CliRunner()


def test_prompt_cloaking_and_decloaking() -> None:
    prompt = "System prompt with sensitive heuristic rules and intellectual property."
    cloaked = cloak_prompt_string(prompt)
    assert cloaked != prompt
    assert isinstance(cloaked, str)

    decloaked = decloak_prompt_string(cloaked)
    assert decloaked == prompt


def test_binary_packaging_spec(tmp_path: Path) -> None:
    # Test canonical default 'agent'
    spec = get_binary_packaging_spec(tmp_path)
    assert spec["binary_name"] == "agent"
    assert spec["canonical_name"] == "agent"
    assert spec["aliases"] == ["migration-agent"]
    assert "migration_agent.adapters.control_api" in spec["hidden_imports"]
    assert "migration_agent.adapters.trust_store" in spec["hidden_imports"]
    assert spec["enable_lto"] is True
    assert spec["strip_binaries"] is True

    # Test backward-compatible alias 'migration-agent'
    alias_spec = get_binary_packaging_spec(tmp_path, binary_name="migration-agent")
    assert alias_spec["binary_name"] == "migration-agent"
    assert alias_spec["aliases"] == ["agent"]


def test_pyinstaller_spec_generation_and_writing(tmp_path: Path) -> None:
    content = generate_pyinstaller_spec(tmp_path, binary_name="agent")
    assert "name='agent'" in content
    assert "migration_agent.adapters.control_api" in content
    assert "Analysis(" in content
    assert "EXE(" in content

    # Write spec file
    spec_path = write_pyinstaller_spec_file(tmp_path, binary_name="agent")
    assert spec_path.is_file()
    assert spec_path.name == "agent.spec"
    assert spec_path.read_text(encoding="utf-8") == content


def test_binary_integrity_and_alias_creation(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    primary = bin_dir / "agent.exe"
    # Write synthetic Windows PE executable content (starts with MZ)
    primary.write_bytes(b"MZ\x90\x00synthetic portable executable test payload")

    # Verify primary binary
    result = verify_binary_integrity(primary)
    assert result["valid"] is True
    assert result["is_executable_format"] is True
    assert result["format"] == "PE"
    assert len(result["sha256"]) == 64

    # Create alias binary
    aliases = create_binary_aliases(primary, ["migration-agent"])
    assert len(aliases) == 1
    alias_file = aliases[0]
    assert alias_file.name == "migration-agent.exe"
    assert alias_file.is_file()
    assert alias_file.read_bytes() == primary.read_bytes()

    # Verify alias binary integrity
    alias_res = verify_binary_integrity(alias_file, expected_sha256=result["sha256"])
    assert alias_res["valid"] is True

    # Verify mismatch handling
    mismatch_res = verify_binary_integrity(alias_file, expected_sha256="0" * 64)
    assert mismatch_res["valid"] is False
    assert "SHA-256 mismatch" in mismatch_res["reason"]


def test_release_manifest_generation_digest_and_verification(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    # Create dummy wheel and binary files
    wheel_file = dist_dir / "migration_agent-0.1.0-py3-none-any.whl"
    wheel_file.write_bytes(b"PK\x03\x04dummy wheel content")

    bin_file = dist_dir / "agent.exe"
    bin_file.write_bytes(b"MZ\x90\x00dummy windows executable")

    manifest = generate_release_manifest(
        version="0.1.0",
        dist_dir=dist_dir,
        release_channel="stable",
        canonical_cli="agent",
    )
    assert manifest.version == "0.1.0"
    assert manifest.canonical_cli == "agent"
    assert manifest.cli_aliases == ["migration-agent"]
    assert manifest.manifest_digest is not None
    assert manifest.manifest_digest.startswith("sha256:")
    assert len(manifest.assets) == 2

    # Verify asset classifications
    wheel_asset = next(a for a in manifest.assets if a.name.endswith(".whl"))
    assert wheel_asset.content_type == "wheel"
    assert len(wheel_asset.sha256) == 64

    bin_asset = next(a for a in manifest.assets if a.name.endswith(".exe"))
    assert bin_asset.content_type == "binary"
    assert bin_asset.platform == "windows-x86_64"

    # Verify manifest against intact dist_dir
    assert verify_release_manifest(manifest, dist_dir) is True

    # Save and reload manifest
    manifest_file = dist_dir / "release-manifest.json"
    save_release_manifest(manifest, manifest_file)
    loaded = load_release_manifest(manifest_file)
    assert loaded.version == manifest.version
    assert loaded.manifest_digest == manifest.manifest_digest

    # Tamper with an asset and verify failure
    bin_file.write_bytes(b"tampered content")
    assert verify_release_manifest(manifest, dist_dir) is False


def test_release_manifest_cryptographic_signing_and_verification(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    asset = dist_dir / "agent-linux-x86_64"
    asset.write_bytes(b"\x7fELFsynthetic linux elf payload")

    key_secret = "release-signing-secret-key-32bytes!!"
    authority_key = AuthorityKey(
        key_id="release-key-1",
        public_key=key_secret,
        fingerprint="sha256:releasekey1fingerprint12345678",
        created_at="2026-10-02T00:00:00Z",
        algorithm="ed25519",
    )

    with pytest.raises(SecurityConfigurationError, match="LEGACY_MODE_A_DISABLED"):
        generate_release_manifest(
            version="1.0.0",
            dist_dir=dist_dir,
            signing_key=key_secret,
            key_id="release-key-1",
        )
    unsigned = generate_release_manifest(version="1.0.0", dist_dir=dist_dir)
    forged = unsigned.model_copy(update={"signature": "ed25519:public-key-hmac"})
    with pytest.raises(SecurityConfigurationError, match="LEGACY_MODE_A_DISABLED"):
        verify_release_manifest(forged, dist_dir, authority_key=authority_key)


def test_cli_package_commands(tmp_path: Path) -> None:
    # 1. Test 'agent package spec'
    spec_res = runner.invoke(app, ["package", "spec", "--package-root", str(tmp_path)])
    assert spec_res.exit_code == 0
    spec_data = json.loads(spec_res.stdout)
    assert spec_data["canonical_name"] == "agent"

    # Test writing spec
    spec_file = tmp_path / "custom.spec"
    write_res = runner.invoke(
        app,
        ["package", "spec", "--package-root", str(tmp_path), "--output", str(spec_file)],
    )
    assert write_res.exit_code == 0
    assert spec_file.is_file()

    # 2. Test 'agent package manifest' and 'verify'
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "agent.exe").write_bytes(b"MZtest executable")

    manifest_file = dist_dir / "release-manifest.json"
    manifest_res = runner.invoke(
        app,
        [
            "package",
            "manifest",
            "--dist-dir",
            str(dist_dir),
            "--version",
            "0.2.0",
            "--output",
            str(manifest_file),
        ],
    )
    assert manifest_res.exit_code == 0
    assert manifest_file.is_file()

    # Verify command
    verify_res = runner.invoke(
        app,
        ["package", "verify", "--dist-dir", str(dist_dir), "--manifest", str(manifest_file)],
    )
    assert verify_res.exit_code == 0
    verify_data = json.loads(verify_res.stdout)
    assert verify_data["valid"] is True
    assert verify_data["version"] == "0.2.0"

    # 3. Test 'agent package cloak' and 'decloak'
    sample_prompt = "Heuristic migration rule for AngularJS directives"
    cloak_res = runner.invoke(app, ["package", "cloak", sample_prompt])
    assert cloak_res.exit_code == 0
    cloaked_str = cloak_res.stdout.strip()
    assert cloaked_str != sample_prompt

    decloak_res = runner.invoke(app, ["package", "decloak", cloaked_str])
    assert decloak_res.exit_code == 0
    assert decloak_res.stdout.strip() == sample_prompt
