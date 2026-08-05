import asyncio
from collections.abc import AsyncIterator

import pytest
from logfire.testing import CaptureLogfire
from opentelemetry.trace import StatusCode
from starlette.requests import ClientDisconnect

from hello_my_assistant_api._chat_streaming_response import ChatStreamingResponse
from hello_my_assistant_api.assistant import (
    AssistantCompleted,
    AssistantDelta,
    AssistantEvent,
    AssistantFailed,
)


async def _emit(*events: AssistantEvent) -> AsyncIterator[AssistantEvent]:
    for event in events:
        yield event


async def _run_streaming_response(
    events: AsyncIterator[AssistantEvent],
    send,
    *,
    receive=None,
    spec_version="2.4",
):
    async def receive_http_request():
        return {"type": "http.request"}

    response = ChatStreamingResponse(events)
    await response(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": spec_version},
        },
        receive or receive_http_request,
        send,
    )


def _collect_response_body(*events: AssistantEvent) -> str:
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(_run_streaming_response(_emit(*events), send))

    return b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    ).decode()


def _get_chat_stream_span(capfire: CaptureLogfire):
    spans = capfire.exporter.exported_spans_as_dict()
    chat_stream_spans = [span for span in spans if span["name"] == "chat.stream"]

    assert len(chat_stream_spans) == 1

    return chat_stream_spans[0]


def _get_exported_chat_stream_span(capfire: CaptureLogfire, chat_stream_span):
    return next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )


def test_streaming_response_sends_sse_events_when_assistant_emits_events(
    capfire: CaptureLogfire,
):
    body = _collect_response_body(
        AssistantDelta(content="안녕"),
        AssistantDelta(content="하세요"),
        AssistantCompleted(),
    )

    assert body == (
        'event: delta\ndata: {"content":"안녕"}\n\n'
        'event: delta\ndata: {"content":"하세요"}\n\n'
        "event: done\ndata: {}\n\n"
    )


def test_streaming_response_preserves_event_order_when_assistant_fails_after_delta(
    capfire: CaptureLogfire,
):
    body = _collect_response_body(
        AssistantDelta(content="부분 응답"),
        AssistantFailed(kind="model_error"),
    )

    assert body == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"model_error",'
        '"message":"Failed to generate chat response"}\n\n'
    )


@pytest.mark.parametrize(
    ("failure_kind", "error_code", "message"),
    [
        pytest.param(
            "invalid_response",
            "invalid_response",
            "Invalid chat response",
            id="invalid-response",
        ),
        pytest.param(
            "model_error",
            "model_error",
            "Failed to generate chat response",
            id="model-error",
        ),
        pytest.param(
            "timeout",
            "chat_timeout",
            "Chat response timed out",
            id="timeout",
        ),
        pytest.param(
            "internal_error",
            "internal_error",
            "Failed to generate chat response",
            id="internal-error",
        ),
    ],
)
def test_streaming_response_sends_error_event_when_assistant_fails(
    capfire: CaptureLogfire, failure_kind, error_code, message
):
    body = _collect_response_body(AssistantFailed(kind=failure_kind))

    assert body == (
        f'event: error\ndata: {{"code":"{error_code}","message":"{message}"}}\n\n'
    )


def test_streaming_response_records_done_outcome_when_assistant_completes(
    capfire: CaptureLogfire,
):
    _collect_response_body(AssistantCompleted())

    chat_stream_span = _get_chat_stream_span(capfire)
    exported_span = _get_exported_chat_stream_span(capfire, chat_stream_span)

    assert chat_stream_span["attributes"].get("chat.outcome") == "done"
    assert "error.type" not in chat_stream_span["attributes"]
    assert exported_span.status.status_code is StatusCode.UNSET


@pytest.mark.parametrize(
    "failure_kind",
    [
        pytest.param("invalid_response", id="invalid-response"),
        pytest.param("model_error", id="model-error"),
        pytest.param("timeout", id="timeout"),
        pytest.param("internal_error", id="internal-error"),
    ],
)
def test_streaming_response_records_error_outcome_when_assistant_fails(
    capfire: CaptureLogfire, failure_kind
):
    _collect_response_body(AssistantFailed(kind=failure_kind))

    chat_stream_span = _get_chat_stream_span(capfire)
    exported_span = _get_exported_chat_stream_span(capfire, chat_stream_span)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == failure_kind
    assert exported_span.status.status_code is StatusCode.ERROR


def test_streaming_response_records_ttft_when_assistant_emits_content_delta(
    capfire: CaptureLogfire,
):
    _collect_response_body(
        AssistantDelta(content="응답"),
        AssistantCompleted(),
    )

    chat_stream_span = _get_chat_stream_span(capfire)
    time_to_first_delta_ms = chat_stream_span["attributes"].get(
        "chat.time_to_first_delta_ms"
    )

    assert isinstance(time_to_first_delta_ms, int | float)
    assert time_to_first_delta_ms >= 0


def test_streaming_response_omits_ttft_when_assistant_emits_only_blank_delta(
    capfire: CaptureLogfire,
):
    _collect_response_body(
        AssistantDelta(content="   "),
        AssistantFailed(kind="invalid_response"),
    )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert "chat.time_to_first_delta_ms" not in chat_stream_span["attributes"]


def test_streaming_response_excludes_event_content_from_trace(
    capfire: CaptureLogfire,
):
    sensitive_content = "SENSITIVE_RESPONSE_CONTENT"

    _collect_response_body(
        AssistantDelta(content=sensitive_content),
        AssistantCompleted(),
    )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert sensitive_content not in str(chat_stream_span["attributes"])


@pytest.mark.parametrize(
    ("send_exception", "expected_exception"),
    [
        pytest.param(OSError(), ClientDisconnect, id="client-disconnect"),
        pytest.param(
            asyncio.CancelledError(),
            asyncio.CancelledError,
            id="cancellation",
        ),
    ],
)
def test_streaming_response_records_incomplete_outcome_when_send_is_interrupted_before_first_delta(
    capfire: CaptureLogfire, send_exception, expected_exception
):
    async def send(message):
        if message["type"] == "http.response.start":
            raise send_exception

    with pytest.raises(expected_exception):
        asyncio.run(
            _run_streaming_response(
                _emit(AssistantDelta(content="응답"), AssistantCompleted()),
                send,
            )
        )

    chat_stream_span = _get_chat_stream_span(capfire)
    exported_span = _get_exported_chat_stream_span(capfire, chat_stream_span)

    assert chat_stream_span["attributes"].get("chat.outcome") == "incomplete"
    assert "error.type" not in chat_stream_span["attributes"]
    assert "chat.time_to_first_delta_ms" not in chat_stream_span["attributes"]
    assert "exception.type" not in str(chat_stream_span)
    assert "exception.stacktrace" not in str(chat_stream_span)
    assert exported_span.status.status_code is StatusCode.UNSET


def test_streaming_response_propagates_same_cancellation_when_send_is_cancelled(
    capfire: CaptureLogfire,
):
    cancellation = asyncio.CancelledError()

    async def send(message):
        if message["type"] == "http.response.start":
            raise cancellation

    async def cancel_response():
        try:
            await _run_streaming_response(
                _emit(AssistantDelta(content="응답"), AssistantCompleted()),
                send,
            )
        except asyncio.CancelledError as propagated_cancellation:
            assert propagated_cancellation is cancellation
            assert (
                _get_chat_stream_span(capfire)["attributes"].get("chat.outcome")
                == "incomplete"
            )
            raise

    with pytest.raises(asyncio.CancelledError) as raised_cancellation:
        asyncio.run(cancel_response())

    assert raised_cancellation.value is cancellation


def test_streaming_response_records_incomplete_outcome_when_client_disconnects_before_first_delta(
    capfire: CaptureLogfire,
):
    async def wait_before_first_delta():
        await asyncio.Event().wait()
        yield AssistantDelta(content="응답")

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        pass

    asyncio.run(
        _run_streaming_response(
            wait_before_first_delta(),
            send,
            receive=receive,
            spec_version="2.3",
        )
    )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "incomplete"


def test_streaming_response_records_internal_error_when_send_fails_unexpectedly(
    capfire: CaptureLogfire,
):
    sensitive_exception_message = "sensitive transport detail"

    async def send(message):
        if message["type"] == "http.response.start":
            raise RuntimeError(sensitive_exception_message)

    with pytest.raises(RuntimeError, match=sensitive_exception_message):
        asyncio.run(
            _run_streaming_response(
                _emit(AssistantDelta(content="응답"), AssistantCompleted()),
                send,
            )
        )

    chat_stream_span = _get_chat_stream_span(capfire)
    exported_span = _get_exported_chat_stream_span(capfire, chat_stream_span)
    serialized_span = str(chat_stream_span)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "internal_error"
    assert sensitive_exception_message not in serialized_span
    assert "exception.message" not in serialized_span
    assert "exception.stacktrace" not in serialized_span
    assert exported_span.status.status_code is StatusCode.ERROR


def test_streaming_response_preserves_ttft_when_client_disconnects_after_delta(
    capfire: CaptureLogfire,
):
    async def send(message):
        if (
            message["type"] == "http.response.body"
            and b"event: delta" in message["body"]
        ):
            raise OSError("client disconnected")

    with pytest.raises(ClientDisconnect):
        asyncio.run(
            _run_streaming_response(
                _emit(AssistantDelta(content="부분 응답"), AssistantCompleted()),
                send,
            )
        )

    chat_stream_span = _get_chat_stream_span(capfire)
    time_to_first_delta_ms = chat_stream_span["attributes"].get(
        "chat.time_to_first_delta_ms"
    )

    assert chat_stream_span["attributes"].get("chat.outcome") == "incomplete"
    assert isinstance(time_to_first_delta_ms, int | float)
    assert time_to_first_delta_ms >= 0


def test_streaming_response_preserves_done_outcome_when_client_disconnects_on_completion(
    capfire: CaptureLogfire,
):
    async def send(message):
        if (
            message["type"] == "http.response.body"
            and b"event: done" in message["body"]
        ):
            raise OSError("client disconnected")

    with pytest.raises(ClientDisconnect):
        asyncio.run(
            _run_streaming_response(
                _emit(AssistantDelta(content="완료 응답"), AssistantCompleted()),
                send,
            )
        )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "done"
    assert "error.type" not in chat_stream_span["attributes"]


def test_streaming_response_preserves_error_outcome_when_client_disconnects_on_failure(
    capfire: CaptureLogfire,
):
    async def send(message):
        if (
            message["type"] == "http.response.body"
            and b"event: error" in message["body"]
        ):
            raise OSError("client disconnected")

    with pytest.raises(ClientDisconnect):
        asyncio.run(
            _run_streaming_response(
                _emit(AssistantFailed(kind="invalid_response")),
                send,
            )
        )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "invalid_response"
