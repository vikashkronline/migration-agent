"""Concrete implementations of TrustStorePort and SignatureVerifierPort."""

import json
from pathlib import Path

from migration_agent.domain.canonical import canonical_json_dumps
from migration_agent.domain.security import SecurityConfigurationError
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
    """Disabled legacy verifier retained only for an explicit compatibility error."""

    def sign(
        self,
        payload_digest: str,
        private_key: str,
        algorithm: str = "ed25519",
    ) -> str:
        raise SecurityConfigurationError(
            "LEGACY_MODE_A_DISABLED: use the genuine trusted human approval workflow."
        )

    def verify(
        self,
        payload_digest: str,
        signature: str,
        authority_key: AuthorityKey,
    ) -> SignatureVerificationResult:
        raise SecurityConfigurationError(
            "LEGACY_MODE_A_DISABLED: public-key HMAC is not accepted identity proof."
        )
