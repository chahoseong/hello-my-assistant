import pytest
from pydantic import ValidationError

import hello_my_assistant_cli.settings as settings_module


def test_settings_loads_values_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASSISTANT_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("ASSISTANT_TIMEOUT_SECONDS", "90")

    settings = settings_module.Settings(_env_file=None)

    assert str(settings.assistant_base_url) == "http://127.0.0.1:8000/"
    assert settings.assistant_timeout_seconds == 90.0


def test_settings_uses_default_values_when_environment_variables_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASSISTANT_BASE_URL", raising=False)
    monkeypatch.delenv("ASSISTANT_TIMEOUT_SECONDS", raising=False)

    settings = settings_module.Settings(_env_file=None)

    assert str(settings.assistant_base_url) == "http://127.0.0.1:8000/"
    assert settings.assistant_timeout_seconds == 70.0


def test_settings_rejects_invalid_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASSISTANT_BASE_URL", "not-a-url")
    monkeypatch.setenv("ASSISTANT_TIMEOUT_SECONDS", "70")

    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)


@pytest.mark.parametrize(
    "timeout",
    [
        pytest.param("0", id="zero"),
        pytest.param("-1", id="negative"),
    ],
)
def test_settings_rejects_non_positive_timeout(
    monkeypatch: pytest.MonkeyPatch,
    timeout: str,
) -> None:
    monkeypatch.setenv("ASSISTANT_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("ASSISTANT_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValidationError):
        settings_module.Settings(_env_file=None)
