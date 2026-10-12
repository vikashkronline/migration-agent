"""Public-key verification and SSH-agent signing; private keys never cross this boundary."""

import subprocess
import tempfile
from pathlib import Path

from migration_agent.adapters.approval_proof import public_key_fingerprint
from migration_agent.adapters.ssh_tools import signing_environment, ssh_keygen


class AccessSignatures:
    namespace = "migration-agent-access-v2"

    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root

    def fingerprint(self, public_key: str) -> str:
        return public_key_fingerprint(public_key)

    def _executable(self) -> str:
        return ssh_keygen()

    @staticmethod
    def _env() -> dict[str, str]:
        return signing_environment()

    def sign(self, public_key: str, digest: str) -> str:
        self.fingerprint(public_key)
        self.state_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="access-sign-", dir=self.state_root) as directory:
            key = Path(directory) / "owner.pub"
            key.write_text(public_key, encoding="ascii")
            result = subprocess.run(
                [self._executable(), "-Y", "sign", "-U", "-f", str(key), "-n", self.namespace],
                input=digest.encode("ascii"),
                capture_output=True,
                shell=False,
                env=self._env(),
                timeout=30,
            )
            if result.returncode or not result.stdout.startswith(b"-----BEGIN SSH SIGNATURE-----"):
                raise ValueError(
                    "SIGNING_FAILED: the trusted SSH-agent did not sign this proposal."
                )
            if len(result.stdout) > 8192:
                raise ValueError("SIGNING_FAILED: signature envelope exceeds the limit.")
            return result.stdout.decode("ascii")

    def verify(self, public_key: str, digest: str, signature: str) -> bool:
        try:
            if not signature.startswith("-----BEGIN SSH SIGNATURE-----") or len(signature) > 8192:
                return False
            self.fingerprint(public_key)
            self.state_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix="access-verify-", dir=self.state_root
            ) as directory:
                allowed = Path(directory) / "allowed"
                proof = Path(directory) / "proof.sig"
                allowed.write_text(f"access-owner {public_key}\n", encoding="ascii")
                proof.write_text(signature, encoding="ascii")
                result = subprocess.run(
                    [
                        self._executable(),
                        "-Y",
                        "verify",
                        "-f",
                        str(allowed),
                        "-I",
                        "access-owner",
                        "-n",
                        self.namespace,
                        "-s",
                        str(proof),
                    ],
                    input=digest.encode(),
                    capture_output=True,
                    shell=False,
                    timeout=10,
                    env=self._env(),
                )
                return result.returncode == 0
        except (ValueError, OSError, subprocess.TimeoutExpired):
            return False
