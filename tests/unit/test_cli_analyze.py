import json
from pathlib import Path

from typer.testing import CliRunner

from migration_agent.cli import app

runner = CliRunner()


def test_cli_analyze_command_default_gemini(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    output_dir = tmp_path / "out"

    result = runner.invoke(
        app,
        ["analyze", str(fixture_path), "--output", str(output_dir), "--fake-runtime"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["provider"] == "gemini"
    assert payload["model"] == "gemini-2.5-pro"
    assert payload["findings_count"] >= 2
    assert Path(payload["json_report"]).exists()
    assert Path(payload["markdown_report"]).exists()


def test_cli_analyze_command_openai_provider(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    output_dir = tmp_path / "out_openai"

    result = runner.invoke(
        app,
        [
            "analyze",
            str(fixture_path),
            "--output",
            str(output_dir),
            "--provider",
            "openai",
            "--fake-runtime",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["provider"] == "openai"
    assert payload["model"] == "gpt-4o"


def test_cli_analyze_command_custom_model(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    output_dir = tmp_path / "out_custom"

    result = runner.invoke(
        app,
        [
            "analyze",
            str(fixture_path),
            "--output",
            str(output_dir),
            "--model",
            "custom-gemini-preview",
            "--fake-runtime",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["model"] == "custom-gemini-preview"


def test_cli_analyze_rejects_unsupported_provider(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"
    output_dir = tmp_path / "out_bad"

    result = runner.invoke(
        app,
        [
            "analyze",
            str(fixture_path),
            "--output",
            str(output_dir),
            "--provider",
            "unsupported_llm",
        ],
    )

    assert result.exit_code == 2
    assert "Unsupported runtime provider" in result.stderr


def test_cli_analyze_rejects_overlapping_path(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "ember-classic-mini"

    result = runner.invoke(
        app,
        [
            "analyze",
            str(fixture_path),
            "--output",
            str(fixture_path / "nested_output"),
            "--fake-runtime",
        ],
    )

    assert result.exit_code == 2
    assert "must not overlap" in result.stderr


def test_cli_analyze_rejects_nonexistent_path(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["analyze", str(tmp_path / "does_not_exist"), "--output", str(tmp_path / "out")],
    )
    assert result.exit_code != 0
