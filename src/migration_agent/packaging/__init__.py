"""Distribution packaging, release manifests, and binary build specifications."""

from migration_agent.packaging.build_binary import (
    BinaryPackagingSpec,
    cloak_prompt_string,
    create_binary_aliases,
    decloak_prompt_string,
    generate_pyinstaller_spec,
    get_binary_packaging_spec,
    verify_binary_integrity,
    write_pyinstaller_spec_file,
)
from migration_agent.packaging.release_manifest import (
    ReleaseAsset,
    ReleaseManifest,
    compute_file_sha256,
    compute_manifest_digest,
    generate_release_manifest,
    load_release_manifest,
    save_release_manifest,
    verify_release_manifest,
)

__all__ = [
    "BinaryPackagingSpec",
    "ReleaseAsset",
    "ReleaseManifest",
    "cloak_prompt_string",
    "compute_file_sha256",
    "compute_manifest_digest",
    "create_binary_aliases",
    "decloak_prompt_string",
    "generate_pyinstaller_spec",
    "generate_release_manifest",
    "get_binary_packaging_spec",
    "load_release_manifest",
    "save_release_manifest",
    "verify_binary_integrity",
    "verify_release_manifest",
    "write_pyinstaller_spec_file",
]
