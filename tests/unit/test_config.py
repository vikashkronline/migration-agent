from migration_agent.config import Settings


def test_model_setting_uses_documented_environment_variable(monkeypatch) -> None:
    monkeypatch.setenv("MIGRATION_AGENT_MODEL", "test-model")

    settings = Settings()

    assert settings.agent_model == "test-model"


def test_model_setting_is_optional(monkeypatch) -> None:
    monkeypatch.delenv("MIGRATION_AGENT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert Settings().agent_model is None
