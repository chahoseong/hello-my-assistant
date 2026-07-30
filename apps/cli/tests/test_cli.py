import pytest
from pytest_httpx import HTTPXMock, IteratorStream

import hello_my_assistant_cli.main as cli


def test_cli_prints_streamed_response_when_user_enters_message(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.delenv("ASSISTANT_BASE_URL", raising=False)

    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream(
            [
                'event: delta\ndata: {"content":"안녕'.encode(),
                '하세요!"}\n\n'.encode(),
                b"event: done\ndata: {}\n\n",
            ]
        ),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == "안녕하세요!\n"
    assert captured.err == ""


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


def test_cli_parses_complete_sse_event_frame():
    lines = ["event: delta", 'data: {"content":"안녕하세요"}', ""]

    assert list(cli.iter_sse_events(lines)) == [
        cli.SSEEvent(event="delta", data={"content": "안녕하세요"})
    ]


def test_cli_rejects_sse_frame_with_invalid_json():
    lines = ["event: delta", "data: not-json", ""]

    with pytest.raises(cli.ChatStreamError):
        list(cli.iter_sse_events(lines))


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("[]", id="array"),
        pytest.param("null", id="null"),
        pytest.param("'text'", id="string"),
    ],
)
def test_cli_rejects_sse_frame_with_non_object_data(payload):
    lines = ["event: delta", f"data: {payload}", ""]

    with pytest.raises(cli.ChatStreamError):
        list(cli.iter_sse_events(lines))


def test_cli_rejects_incomplete_sse_frame():
    lines = ["event: delta", 'data: {"content":"unfinished}']

    with pytest.raises(cli.ChatStreamError):
        list(cli.iter_sse_events(lines))


def test_cli_prints_error_when_stream_returns_error(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream(
            [
                (
                    b"event: error\n"
                    b'data: {"code":"model_error",'
                    b'"message":"Failed to generate char response"}\n\n'
                )
            ]
        ),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ("Failed to get a response from the assistant.\n")


def test_cli_preserves_partial_output_when_stream_returns_error(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream(
            [
                (
                    "event: delta\n"
                    'data: {"content":"부분 응답"}\n\n'
                    "event: error\n"
                    'data: {"code":"model_error",'
                    '"message":"Failed to generate chat response"}\n\n'
                ).encode()
            ]
        ),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == "부분 응답\n"
    assert captured.err == ("Failed to get a response from the assistant.\n")


def test_cli_prints_error_when_stream_content_type_is_invalid(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "application/json"},
        stream=IteratorStream(
            [
                (
                    "event: delta\n"
                    'data: {"content":"잘못된 응답"}\n\n'
                    "event: done\n"
                    "data: {}\n\n"
                ).encode()
            ]
        ),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ("Failed to get a response from the assistant.\n")


def test_cli_prints_error_when_stream_event_is_unknown(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream([(b"event: mystery\ndata: {}\n\n")]),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ("Failed to get a response from the assistant.\n")


def test_cli_prints_error_when_stream_ends_before_done(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream(
            [('event: delta\ndata: {"content":"중단된 응답"}\n\n').encode()]
        ),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == "중단된 응답\n"
    assert captured.err == ("Failed to get a response from the assistant.\n")


@pytest.mark.parametrize(
    "data",
    [
        pytest.param("{}", id="missing-content"),
        pytest.param('{"content":123}', id="non-string-content"),
    ],
)
def test_cli_prints_error_when_delta_payload_is_invalid(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    data: str,
):
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream([(f"event: delta\ndata: {data}\n\n").encode()]),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ("Failed to get a response from the assistant.\n")


def test_cli_prints_error_when_done_payload_is_not_empty(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream([(b'event: done\ndata: {"unexpected":true}\n\n')]),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == "Failed to get a response from the assistant.\n"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param("{}", id="missing-fields"),
        pytest.param(
            '{"code":123,"message":"Failed"}',
            id="non-string-code",
        ),
        pytest.param(
            '{"code":"model_error","message":123}',
            id="non-string-message",
        ),
    ],
)
def test_cli_prints_error_when_error_payload_is_invalid(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    data: str,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "안녕?"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream([(f"event: error\ndata: {data}\n\n").encode()]),
    )

    inputs = iter(["안녕?", "/exit"])
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt="": next(inputs),
    )

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ("Failed to get a response from the assistant.\n")


def test_cli_parses_multiple_sse_data_lines() -> None:
    lines = [
        "event: delta",
        'data: {"content":',
        'data: "안녕하세요"}',
        "",
    ]

    assert list(cli.iter_sse_events(lines)) == [
        cli.SSEEvent(
            event="delta",
            data={"content": "안녕하세요"},
        )
    ]


def test_cli_ignores_sse_comments_and_unrecognized_fields() -> None:
    lines = [
        ": keep-alive",
        "id: 42",
        "retry: 1000",
        "event: done",
        "data: {}",
        "",
    ]

    assert list(cli.iter_sse_events(lines)) == [cli.SSEEvent(event="done", data={})]


def test_cli_preserves_unicode_and_embedded_newline_in_streamed_content(
    httpx_mock: HTTPXMock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8000/chat",
        match_json={"content": "여러 줄로 답해줘"},
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream(
            [
                (
                    "event: delta\n"
                    'data: {"content":"첫째 줄\\n둘째 줄"}\n\n'
                    "event: done\n"
                    "data: {}\n\n"
                ).encode()
            ]
        ),
    )

    inputs = iter(["여러 줄로 답해줘", "/exit"])
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt="": next(inputs),
    )

    cli.main()

    captured = capsys.readouterr()

    assert captured.out == "첫째 줄\n둘째 줄\n"
    assert captured.err == ""
