import json

from typer.testing import CliRunner

from migration_agent.cli import app, collect_diagnostics

runner = CliRunner()


def test_doctor_emits_json_and_needs_no_api_key(monkeypatch) -> None:
    monkeypatch.delenv("MIGRATION_AGENT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-appear")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "must-not-appear" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["status"] == "ok"
    assert payload["checks"][2]["details"] == {
        "configured": False,
        "required_for_doctor": False,
    }


def test_diagnostics_fail_for_unsupported_python() -> None:
    payload = collect_diagnostics(python_version=(3, 11, 9))

    assert payload["status"] == "error"
    assert payload["checks"][0]["status"] == "fail"
