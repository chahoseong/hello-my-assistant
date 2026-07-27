import pytest
from pydantic import ValidationError

import hello_my_assistant_api.settings as settings_module


def test_settings_loads_values_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_TIMEOUT_SECONDS", "30")

    settings = settings_module.Settings(_env_file=None)

    assert str(settings.llm_base_url) == "http://127.0.0.1:8080/v1"
    assert settings.llm_model_name == "test-model"
    assert settings.llm_api_key.get_secret_value() == "test-key"
    assert settings.chat_timeout_seconds == 30.0


@pytest.mark.parametrize(
    "environment_variable", ["LLM_BASE_URL", "LLM_MODEL_NAME", "LLM_API_KEY"]
)
@pytest.mark.parametrize(
    "blank_value",
    [pytest.param("", id="empty"), pytest.param("   ", id="whitespace-only")],
)
def test_settings_rejects_blank_llm_setting(
    monkeypatch, environment_variable, blank_value
):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("CHAT_TIMEOUT_SECONDS", "30")

    monkeypatch.setenv(environment_variable, blank_value)

    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)


def test_settings_uses_default_timeout_when_timeout_is_missing(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    settings = settings_module.Settings(_env_file=None)

    assert settings.chat_timeout_seconds == 60.0


@pytest.mark.parametrize(
    "timeout", [pytest.param("0", id="zero"), pytest.param("-1", id="negative")]
)
def test_settings_rejects_non_positive_timeout(monkeypatch, timeout):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    monkeypatch.setenv("CHAT_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)


def test_settings_loads_values_from_dotenv_file(monkeypatch, tmp_path):
    for variable in (
        "LLM_BASE_URL",
        "LLM_MODEL_NAME",
        "LLM_API_KEY",
        "CHAT_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(variable, raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "LLM_BASE_URL=http://127.0.0.1:8080/v1\n"
            "LLM_MODEL_NAME=dotenv-model\n"
            "LLM_API_KEY=dotenv-key\n"
            "CHAT_TIMEOUT_SECONDS=45\n",
            encoding="utf-8",
        )

        monkeypatch.chdir(tmp_path)

        settings = settings_module.Settings()

    assert str(settings.llm_base_url) == "http://127.0.0.1:8080/v1"
    assert settings.llm_model_name == "dotenv-model"
    assert settings.llm_api_key.get_secret_value() == "dotenv-key"
    assert settings.chat_timeout_seconds == 45.0


@pytest.mark.parametrize(
    "environment_variable", ["LLM_BASE_URL", "LLM_MODEL_NAME", "LLM_API_KEY"]
)
def test_settings_rejects_missing_llm_setting(monkeypatch, environment_variable):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    monkeypatch.delenv(environment_variable, raising=False)

    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)
