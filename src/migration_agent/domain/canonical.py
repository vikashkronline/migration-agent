"""RFC 8785 Canonical JSON serialization and hashing.

Provides deterministic canonical JSON representations and cryptographic digests
for domain entities, ChangeSets, plans, and policies.
"""

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def _utf16_sort_key(s: str) -> bytes:
    """Sort key for string keys according to RFC 8785 (lexicographic by UTF-16 code units)."""
    return s.encode("utf-16-be")


def canonicalize_value(val: Any) -> Any:
    """Recursively convert data structures into canonical form."""
    if isinstance(val, BaseModel):
        val = val.model_dump(mode="json")

    if isinstance(val, dict):
        # Sort keys lexicographically by UTF-16 code units
        sorted_keys = sorted(val.keys(), key=_utf16_sort_key)
        return {k: canonicalize_value(val[k]) for k in sorted_keys}
    elif isinstance(val, (list, tuple)):
        return [canonicalize_value(item) for item in val]
    elif isinstance(val, float):
        # In RFC 8785 / ECMAScript, integers formatted as integers without trailing .0
        if val.is_integer():
            return int(val)
        return val
    return val


def canonical_json_dumps(data: Any) -> str:
    """Serialize data into a deterministic RFC 8785 canonical JSON string.

    Rules:
    - Object keys sorted by UTF-16 code units.
    - No whitespace between tokens (separators=(',', ':')).
    - UTF-8 characters preserved (ensure_ascii=False).
    - Float/integer canonicalization.
    """
    canonical_data = canonicalize_value(data)
    return json.dumps(
        canonical_data,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,  # Already sorted with UTF-16 code unit semantics
    )


def compute_canonical_digest(data: Any) -> str:
    """Compute SHA-256 digest over the RFC 8785 canonical JSON representation.

    Returns:
        Hex-encoded string prefixed with 'sha256:'.
    """
    canonical_str = canonical_json_dumps(data)
    digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
