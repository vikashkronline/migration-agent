"""Domain models and rules for audit redaction and large payload digestion."""

import hashlib
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_SENSITIVE_KEY_SUBSTRINGS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "CREDENTIAL",
    "AUTH",
    "OPENAI",
    "GEMINI",
)

_SECRET_PATTERN = re.compile(
    r"(?:sk-[a-zA-Z0-9_\-]{16,}|bearer\s+[a-zA-Z0-9_\-\.]{16,}|ghp_[a-zA-Z0-9]{20,})",
    re.IGNORECASE,
)


class RedactionPolicy(BaseModel):
    """Enforces non-disclosure of secrets and truncation of oversized payloads in audit trails."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_payload_bytes: int = Field(default=512, ge=64)
    sensitive_substrings: tuple[str, ...] = _SENSITIVE_KEY_SUBSTRINGS

    def is_sensitive_key(self, key: str) -> bool:
        """Check if a dictionary key name suggests sensitive content."""
        upper = key.upper()
        return any(sub in upper for sub in self.sensitive_substrings)

    def redact_text(self, text: str) -> str:
        """Replace inline tokens or secrets in text with [REDACTED]."""
        return _SECRET_PATTERN.sub("[REDACTED]", text)

    def redact_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact secrets and bound oversized entries in audit payloads."""
        cleaned: dict[str, Any] = {}

        for k, v in payload.items():
            if self.is_sensitive_key(k):
                cleaned[k] = "[REDACTED]"
            elif isinstance(v, dict):
                cleaned[k] = self.redact_payload(v)
            elif isinstance(v, (list, tuple)):
                cleaned[k] = [
                    self.redact_payload(item)
                    if isinstance(item, dict)
                    else (self.redact_text(str(item)) if isinstance(item, str) else item)
                    for item in v
                ]
            elif isinstance(v, str):
                redacted_str = self.redact_text(v)
                raw_bytes = redacted_str.encode("utf-8")
                if len(raw_bytes) > self.max_payload_bytes:
                    digest = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
                    truncated = raw_bytes[: self.max_payload_bytes].decode(
                        "utf-8", errors="replace"
                    )
                    cleaned[k] = {
                        "digest": digest,
                        "preview": f"{truncated}\n... [TRUNCATED]",
                        "size_bytes": len(raw_bytes),
                    }
                else:
                    cleaned[k] = redacted_str
            elif isinstance(v, bytes):
                digest = f"sha256:{hashlib.sha256(v).hexdigest()}"
                if len(v) > self.max_payload_bytes:
                    cleaned[k] = {
                        "digest": digest,
                        "preview": "[BINARY_DATA_TRUNCATED]",
                        "size_bytes": len(v),
                    }
                else:
                    cleaned[k] = {"digest": digest, "size_bytes": len(v)}
            else:
                cleaned[k] = v

        return cleaned
