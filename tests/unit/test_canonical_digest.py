"""Unit tests for RFC 8785 Canonical JSON scheme and deterministic digest hashing."""

import json

from pydantic import BaseModel

from migration_agent.domain import canonical_json_dumps, compute_canonical_digest


class SampleModel(BaseModel):
    name: str
    count: int
    tags: list[str]


def test_canonical_json_sorts_keys_by_utf16() -> None:
    # Keys out of order
    data = {
        "zebra": 1,
        "apple": 2,
        "Banana": 3,
        "123": 4,
    }
    # RFC 8785 sorting by UTF-16 code units: numbers < uppercase < lowercase
    canonical_str = canonical_json_dumps(data)
    assert canonical_str == '{"123":4,"Banana":3,"apple":2,"zebra":1}'


def test_canonical_json_no_whitespace() -> None:
    data = {
        "items": [1, 2, 3],
        "nested": {"a": "b"},
    }
    canonical_str = canonical_json_dumps(data)
    assert " " not in canonical_str
    assert "\n" not in canonical_str
    assert canonical_str == '{"items":[1,2,3],"nested":{"a":"b"}}'


def test_canonical_json_handles_floats_and_integers() -> None:
    data = {
        "int_as_float": 42.0,
        "real_float": 3.1415,
        "pure_int": 100,
    }
    canonical_str = canonical_json_dumps(data)
    parsed = json.loads(canonical_str)
    assert parsed["int_as_float"] == 42
    assert parsed["real_float"] == 3.1415
    assert parsed["pure_int"] == 100
    assert '"int_as_float":42' in canonical_str


def test_canonical_json_handles_pydantic_models() -> None:
    model = SampleModel(name="test", count=5, tags=["alpha", "beta"])
    canonical_str = canonical_json_dumps(model)
    assert canonical_str == '{"count":5,"name":"test","tags":["alpha","beta"]}'


def test_compute_canonical_digest_is_deterministic() -> None:
    data1 = {"b": 2, "a": 1}
    data2 = {"a": 1, "b": 2}
    digest1 = compute_canonical_digest(data1)
    digest2 = compute_canonical_digest(data2)

    assert digest1.startswith("sha256:")
    assert len(digest1) == 71  # "sha256:" (7) + 64 hex chars
    assert digest1 == digest2


def test_digest_changes_on_any_content_mutation() -> None:
    data1 = {"a": 1, "b": [1, 2, 3]}
    data2 = {"a": 1, "b": [1, 2, 4]}
    assert compute_canonical_digest(data1) != compute_canonical_digest(data2)
