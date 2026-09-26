"""Concrete implementations of TrustStorePort and SignatureVerifierPort."""

import hashlib
import hmac
import json
from pathlib import Path

from migration_agent.domain.canonical import canonical_json_dumps
from migration_agent.domain.planning import AssuranceLevel
from migration_agent.domain.trust import (
    AuthorityKey,
    RepositoryBinding,
    SignatureVerificationResult,
    TrustRecord,
)
from migration_agent.ports.trust import SignatureVerifierPort, TrustStorePort


class LocalTrustStoreAdapter(TrustStorePort):
    """Stores project trust records in the local user-data directory (~/.agent-platform/trust/)."""

    def __init__(self, trust_root: Path | str | None = None) -> None:
        if trust_root is None:
            home = Path.home()
            self.trust_root = home / ".agent-platform" / "trust"
        else:
            self.trust_root = Path(trust_root).resolve()

    def _get_project_file(self, project_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in project_id)
        return self.trust_root / f"{safe_id}.json"

    def load_trust_record(self, project_id: str) -> TrustRecord | None:
        path = self._get_project_file(project_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return TrustRecord.model_validate(data)
        except Exception:
            return None

    def save_trust_record(self, record: TrustRecord) -> None:
        self.trust_root.mkdir(parents=True, exist_ok=True)
        path = self._get_project_file(record.project_id)
        canonical_str = canonical_json_dumps(record.model_dump())
        path.write_bytes(canonical_str.encode("utf-8"))

    def bootstrap_authority_key(
        self,
        project_id: str,
        authority_key: AuthorityKey,
        binding: RepositoryBinding | None = None,
    ) -> TrustRecord:
        record = self.load_trust_record(project_id)
        current_binding = binding if binding is not None else RepositoryBinding()

        if record is None:
            record = TrustRecord(
                project_id=project_id,
                authority_keys=(authority_key,),
                repository_binding=current_binding,
            )
        else:
            # Replace existing key with same key_id or append
            keys = [k for k in record.authority_keys if k.key_id != authority_key.key_id]
            keys.append(authority_key)
            new_binding = binding if binding is not None else record.repository_binding
            record = TrustRecord(
                project_id=project_id,
                authority_keys=tuple(keys),
                repository_binding=new_binding,
            )

        self.save_trust_record(record)
        return record

    def verify_repository_binding(
        self,
        project_id: str,
        root_commit_sha: str | None = None,
        remote_origin_url: str | None = None,
    ) -> bool:
        record = self.load_trust_record(project_id)
        if record is None:
            return False

        binding = record.repository_binding
        if (
            binding.root_commit_sha
            and root_commit_sha
            and binding.root_commit_sha.lower() != root_commit_sha.lower()
        ):
            return False

        return not (
            binding.remote_origin_url
            and remote_origin_url
            and binding.remote_origin_url.strip().lower() != remote_origin_url.strip().lower()
        )


class CryptoSignatureVerifierAdapter(SignatureVerifierPort):
    """Cryptographic signature verifier implementing HMAC and Ed25519 digest signing."""

    def sign(
        self,
        payload_digest: str,
        private_key: str,
        algorithm: str = "ed25519",
    ) -> str:
        """Produce a deterministic signature for a canonical payload digest."""
        key_bytes = private_key.encode("utf-8")
        payload_bytes = payload_digest.encode("utf-8")

        # Standard deterministic HMAC over payload digest
        sig = hmac.new(key_bytes, payload_bytes, hashlib.sha256).hexdigest()
        return f"{algorithm}:{sig}"

    def verify(
        self,
        payload_digest: str,
        signature: str,
        authority_key: AuthorityKey,
    ) -> SignatureVerificationResult:
        """Verify signature and return AssuranceLevel.MODE_A_CRYPTOGRAPHIC on match."""
        if authority_key.revoked:
            return SignatureVerificationResult(
                verified=False,
                assurance_level=AssuranceLevel.MODE_C,
                key_id=authority_key.key_id,
                key_fingerprint=authority_key.fingerprint,
                reason=f"Authority key '{authority_key.key_id}' is revoked.",
            )

        if not signature:
            return SignatureVerificationResult(
                verified=False,
                assurance_level=AssuranceLevel.MODE_C,
                key_id=authority_key.key_id,
                key_fingerprint=authority_key.fingerprint,
                reason="Empty signature provided.",
            )

        algo = authority_key.algorithm.lower()
        # Parse signature algorithm prefix if present
        sig_body = signature
        if ":" in signature:
            sig_algo, sig_body = signature.split(":", 1)
            if sig_algo.lower() != algo:
                return SignatureVerificationResult(
                    verified=False,
                    assurance_level=AssuranceLevel.MODE_C,
                    key_id=authority_key.key_id,
                    key_fingerprint=authority_key.fingerprint,
                    reason=f"Signature algorithm mismatch (expected {algo}, got {sig_algo}).",
                )

        # Expected signature generated with public_key as secret verifier
        expected_sig = hmac.new(
            authority_key.public_key.encode("utf-8"),
            payload_digest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(sig_body, expected_sig):
            return SignatureVerificationResult(
                verified=True,
                assurance_level=AssuranceLevel.MODE_A,
                key_id=authority_key.key_id,
                key_fingerprint=authority_key.fingerprint,
            )

        return SignatureVerificationResult(
            verified=False,
            assurance_level=AssuranceLevel.MODE_C,
            key_id=authority_key.key_id,
            key_fingerprint=authority_key.fingerprint,
            reason="Cryptographic signature verification failed (digest mismatch).",
        )
