"""Identity fallback cannot turn token inspection failures into another principal."""

from types import SimpleNamespace

import pytest

from migration_agent.adapters import os_identity
from migration_agent.domain.security import SecurityConfigurationError


@pytest.mark.parametrize("error", [AttributeError, NotImplementedError])
def test_windows_api_absence_uses_guarded_fallback(monkeypatch, error):
    monkeypatch.setattr(os_identity, "os", SimpleNamespace(name="nt"))

    def unavailable():
        raise error("Win32 token API unavailable")

    monkeypatch.setattr(os_identity, "_windows_sid", unavailable)
    monkeypatch.setattr(os_identity, "_fallback_sid", lambda: "S-1-5-21-123-456-789-1001")
    assert os_identity.current_os_identity() == "windows:S-1-5-21-123-456-789-1001"


@pytest.mark.parametrize(
    "message",
    [
        "IDENTITY_FAILED: cannot inspect thread identity.",
        "IDENTITY_UNSUPPORTED: impersonated threads cannot administer access.",
        "IDENTITY_FAILED: cannot read TokenUser.",
    ],
)
def test_windows_token_failures_never_fall_back(monkeypatch, message):
    monkeypatch.setattr(os_identity, "os", SimpleNamespace(name="nt"))

    def failed():
        raise SecurityConfigurationError(message)

    monkeypatch.setattr(os_identity, "_windows_sid", failed)
    monkeypatch.setattr(
        os_identity, "_fallback_sid", lambda: pytest.fail("token failures must stay fail-closed")
    )
    with pytest.raises(SecurityConfigurationError, match=message):
        os_identity.current_os_identity()


@pytest.mark.parametrize("machine", [None, "uninitialized", "0123456789abcdef" * 2])
def test_linux_machine_identity_is_required_and_bound_to_uid(tmp_path, monkeypatch, machine):
    machine_path = tmp_path / "machine-id"
    if machine is not None:
        machine_path.write_text(machine + "\n", encoding="ascii")
    monkeypatch.setattr(os_identity, "os", SimpleNamespace(name="posix", geteuid=lambda: 1000))
    monkeypatch.setattr(os_identity, "Path", lambda _: machine_path)
    if machine is None:
        with pytest.raises(SecurityConfigurationError, match="stable OS machine identity"):
            os_identity.current_os_identity()
    elif machine == "uninitialized":
        with pytest.raises(SecurityConfigurationError, match="malformed OS machine identity"):
            os_identity.current_os_identity()
    else:
        assert os_identity.current_os_identity() == f"posix:{machine}:uid:1000"
