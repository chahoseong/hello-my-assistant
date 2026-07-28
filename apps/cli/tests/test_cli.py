import pytest
from pytest_httpx import HTTPXMock

import hello_my_assistant_cli.main as cli


def test_cli_prints_response_when_user_enters_message(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.delenv("ASSISTANT_BASE_URL", raising=False)

    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        json={"content": "안녕하세요!"},
    )

    inputs = iter(["안녕?", "/exit"])

    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == "안녕하세요!\n"


@pytest.mark.parametrize(
    "message", [pytest.param("", id="empty"), pytest.param("   ", id="whitespace-only")]
)
def test_cli_skips_request_when_user_enters_blank_message(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    inputs = iter([message, "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    assert httpx_mock.get_request() is None


def test_cli_prints_error_when_api_returns_error(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        status_code=500,
        json={"detail": "Internal Server Error"},
    )

    inputs = iter(["안녕?", "/exit"])

    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.err == "Failed to get a response from the assistant.\n"


def test_cli_sets_client_timeout_when_timeout_is_provided() -> None:
    with cli.create_client("http://127.0.0.1", 90) as client:
        assert client.timeout.read == 90.0
