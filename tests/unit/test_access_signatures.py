"""Production access verification requires real purpose-bound OpenSSH envelopes."""

import base64
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from ssh_signature_fixture import ssh_signature

from migration_agent.adapters.access_signatures import AccessSignatures


@pytest.fixture
def proof_key():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH).decode()
    return private, public


def test_openssh_envelope_binds_message_key_and_namespace(tmp_path, proof_key):
    private, public = proof_key
    verifier = AccessSignatures(tmp_path)
    signature = ssh_signature(private, "exact-proposal")
    assert verifier.verify(public, "exact-proposal", signature)
    assert not verifier.verify(public, "changed-proposal", signature)
    foreign_key = Ed25519PrivateKey.generate()
    assert not verifier.verify(
        public, "exact-proposal", ssh_signature(foreign_key, "exact-proposal")
    )
    assert not verifier.verify(
        public, "exact-proposal", ssh_signature(private, "exact-proposal", "migration-agent-apply")
    )


def test_raw_ed25519_cannot_be_enabled_in_production(tmp_path, proof_key, monkeypatch):
    private, public = proof_key
    monkeypatch.setenv("AGENT_ALLOW_RAW_ED25519_PROOFS", "1")
    verifier = AccessSignatures(tmp_path / "uncreated")
    monkeypatch.setattr(
        verifier, "_executable", lambda: pytest.fail("raw proof must not invoke OpenSSH")
    )
    signature = "ed25519-base64:" + base64.b64encode(private.sign(b"exact-proposal")).decode()
    assert not verifier.verify(public, "exact-proposal", signature)
    assert not verifier.state_root.exists()


def test_malformed_and_oversized_envelopes_fail_closed(tmp_path, proof_key):
    _, public = proof_key
    verifier = AccessSignatures(tmp_path)
    assert not verifier.verify(public, "exact-proposal", "-----BEGIN SSH SIGNATURE-----\nbad")
    assert not verifier.verify(
        public, "exact-proposal", "-----BEGIN SSH SIGNATURE-----" + "x" * 8192
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows OpenSSH environment boundary")
def test_windows_openssh_uses_trusted_program_data_without_inheriting_secrets(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PROGRAMDATA", "untrusted-profile")
    monkeypatch.setenv("TEST_CREDENTIAL", "do-not-inherit")
    monkeypatch.setattr(
        "migration_agent.adapters.ssh_tools.windows_program_data_directory",
        lambda: Path(tmp_path),
    )
    environment = AccessSignatures._env()
    assert environment["PROGRAMDATA"] == str(tmp_path)
    assert "TEST_CREDENTIAL" not in environment
    assert "AGENT_ALLOW_RAW_ED25519_PROOFS" not in environment
