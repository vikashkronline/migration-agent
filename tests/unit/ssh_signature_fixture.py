"""Ephemeral in-memory test proofs following OpenSSH PROTOCOL.sshsig; no key files."""

import base64
import hashlib
import struct
import textwrap

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _string(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


def ssh_signature(
    private: Ed25519PrivateKey, digest: str, namespace: str = "migration-agent-access-v2"
) -> str:
    public = private.public_key().public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
    public_blob = base64.b64decode(public.split()[1], validate=True)
    fields = _string(namespace.encode("ascii")) + _string(b"") + _string(b"sha512")
    message = b"SSHSIG" + fields + _string(hashlib.sha512(digest.encode("ascii")).digest())
    signature = _string(b"ssh-ed25519") + _string(private.sign(message))
    envelope = b"SSHSIG" + struct.pack(">I", 1) + _string(public_blob) + fields + _string(signature)
    armored = "\n".join(textwrap.wrap(base64.b64encode(envelope).decode("ascii"), 76))
    return f"-----BEGIN SSH SIGNATURE-----\n{armored}\n-----END SSH SIGNATURE-----\n"
