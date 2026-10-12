"""SSH-agent signing and genuine Ed25519 verification anchored outside the source."""

import base64
import getpass
import hashlib
import subprocess
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_ssh_public_key

from migration_agent.adapters.filesystem import read_repository_text, validate_repository_path
from migration_agent.adapters.ssh_tools import signing_environment, ssh_keygen
from migration_agent.domain.apply_approval import ApplyApprovalRecord
from migration_agent.domain.execution import NativeExecutionConsent
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.trust import AuthorityKey, TrustRecord
from migration_agent.ports.approval_authority import ApprovalAuthorityPort


def public_key_fingerprint(public_key: str) -> str:
    parts = public_key.strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("KEY_UNSUPPORTED: only an OpenSSH Ed25519 public key is accepted.")
    key = load_ssh_public_key(" ".join(parts[:2]).encode())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("KEY_UNSUPPORTED: an Ed25519 public key is required.")
    digest = hashlib.sha256(base64.b64decode(parts[1], validate=True)).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


class LocalApprovalProof:
    def __init__(
        self,
        trust_root: Path,
        state_root: Path,
        access_authority: ApprovalAuthorityPort | None = None,
    ) -> None:
        self.trust_root = trust_root.resolve()
        self.state_root = state_root.resolve()
        self.access_authority = access_authority

    def authority(
        self, project_id: str, fingerprint: str, root_commit: str | None = None
    ) -> AuthorityKey:
        if self.access_authority:
            return self.access_authority.key(project_id, fingerprint, root_commit)
        from migration_agent.application.host_proposals import opaque_id

        path = validate_repository_path(self.trust_root, f"{opaque_id(project_id)}.json")
        if not path.exists():
            raise ValueError("AUTHORITY_REQUIRED: bootstrap an out-of-band authority key.")
        record = TrustRecord.model_validate_json(read_repository_text(self.trust_root, path.name))
        if record.project_id != project_id or not record.repository_binding.root_commit_sha:
            raise ValueError(
                "TRUST_BINDING_INVALID: authority must bind this repository root commit."
            )
        if root_commit and record.repository_binding.root_commit_sha != root_commit:
            raise ValueError(
                "TRUST_BINDING_INVALID: repository does not match the authority record."
            )
        key = record.find_key(fingerprint)
        if (
            key is None
            or key.algorithm != "ed25519"
            or public_key_fingerprint(key.public_key) != key.fingerprint
        ):
            raise ValueError("AUTHORITY_REQUIRED: active Ed25519 authority is unavailable.")
        return key

    @staticmethod
    def _env() -> dict[str, str]:
        return signing_environment()

    def sign(self, record: ApplyApprovalRecord | NativeExecutionConsent) -> str:
        if record.assurance_level == AssuranceLevel.MODE_B:
            if record.actor != getpass.getuser():
                raise ValueError("ACTOR_MISMATCH: local review must identify the OS account.")
            return f"local-human:{record.signing_digest}"
        key = self.authority(record.project_id, record.key_fingerprint or "")
        self.state_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="sign-", dir=self.state_root) as directory:
            public_path = Path(directory) / "authority.pub"
            public_path.write_text(key.public_key, encoding="utf-8")
            result = subprocess.run(
                [
                    ssh_keygen(),
                    "-Y",
                    "sign",
                    "-U",
                    "-f",
                    str(public_path),
                    "-n",
                    "migration-agent-native-execution"
                    if isinstance(record, NativeExecutionConsent)
                    else "migration-agent-apply",
                ],
                input=record.signing_digest.encode(),
                capture_output=True,
                env=self._env(),
                shell=False,
                timeout=30,
            )
            if result.returncode or len(result.stdout) > 8192:
                raise ValueError("SIGNING_FAILED: trusted SSH-agent could not sign the review.")
            signature = result.stdout.decode("ascii")
            if not signature.startswith("-----BEGIN SSH SIGNATURE-----"):
                raise ValueError("SIGNING_FAILED: invalid SSH signature envelope.")
            return signature

    def verify(
        self, record: ApplyApprovalRecord | NativeExecutionConsent, root_commit: str
    ) -> bool:
        if self.access_authority and not self.access_authority.accepts(record):
            return False
        if record.assurance_level == AssuranceLevel.MODE_B:
            return (
                record.actor == getpass.getuser()
                and record.signature == f"local-human:{record.signing_digest}"
            )
        if record.assurance_level != AssuranceLevel.MODE_A:
            return False
        try:
            key = self.authority(record.project_id, record.key_fingerprint or "", root_commit)
            if record.signature.startswith("ed25519-base64:"):
                public_key = load_ssh_public_key(key.public_key.encode())
                if not isinstance(public_key, Ed25519PublicKey):
                    return False
                public_key.verify(
                    base64.b64decode(record.signature.split(":", 1)[1], validate=True),
                    record.signing_digest.encode(),
                )
                return True
            if not record.signature.startswith("-----BEGIN SSH SIGNATURE-----"):
                return False
            with tempfile.TemporaryDirectory(prefix="verify-", dir=self.state_root) as directory:
                signature_path = Path(directory) / "approval.sig"
                signature_path.write_text(record.signature, encoding="ascii")
                allowed = Path(directory) / "allowed_signers"
                allowed.write_text(f"migration-human {key.public_key}\n", encoding="ascii")
                result = subprocess.run(
                    [
                        ssh_keygen(),
                        "-Y",
                        "verify",
                        "-f",
                        str(allowed),
                        "-I",
                        "migration-human",
                        "-n",
                        "migration-agent-native-execution"
                        if isinstance(record, NativeExecutionConsent)
                        else "migration-agent-apply",
                        "-s",
                        str(signature_path),
                    ],
                    input=record.signing_digest.encode(),
                    capture_output=True,
                    shell=False,
                    env=self._env(),
                    timeout=10,
                )
                return result.returncode == 0
        except (ValueError, InvalidSignature, OSError, subprocess.TimeoutExpired):
            return False
