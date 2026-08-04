import asyncio

import pytest
from fastapi import status
from logfire.testing import CaptureLogfire
from opentelemetry.trace import StatusCode
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models.function import FunctionModel
from starlette.requests import ClientDisconnect

import hello_my_assistant_api.main as main_module


def _request_successful_chat(client):
    async def respond(messages, _):
        yield "안녕"
        yield "하세요"

    with main_module.assistant.override(model=FunctionModel(stream_function=respond)):
        return client.post("/chat", json={"content": "안녕?"})


def _get_chat_stream_span(capfire: CaptureLogfire):
    spans = capfire.exporter.exported_spans_as_dict()
    chat_stream_spans = [span for span in spans if span["name"] == "chat.stream"]

    assert len(chat_stream_spans) == 1

    return chat_stream_spans[0]


def test_chat_stream_trace_links_http_agent_and_model_spans(
    client, capfire: CaptureLogfire
):
    _request_successful_chat(client)

    spans = capfire.exporter.exported_spans_as_dict()

    http_spans = [
        span for span in spans if span["attributes"].get("http.route") == "/chat"
    ]
    chat_stream_spans = [span for span in spans if span["name"] == "chat.stream"]
    agent_spans = [
        span
        for span in spans
        if span["attributes"].get("gen_ai.operation.name") == "invoke_agent"
    ]
    model_spans = [
        span
        for span in spans
        if span["attributes"].get("gen_ai.operation.name") == "chat"
    ]

    assert len(http_spans) == 1
    assert len(chat_stream_spans) == 1
    assert len(agent_spans) == 1
    assert len(model_spans) == 1

    http_span = http_spans[0]
    chat_stream_span = chat_stream_spans[0]
    agent_span = agent_spans[0]
    model_span = model_spans[0]

    assert (
        http_span["context"]["trace_id"]
        == chat_stream_span["context"]["trace_id"]
        == agent_span["context"]["trace_id"]
        == model_span["context"]["trace_id"]
    )

    assert chat_stream_span["parent"] is not None
    assert chat_stream_span["parent"]["span_id"] == http_span["context"]["span_id"]

    assert agent_span["parent"] is not None
    assert agent_span["parent"]["span_id"] == chat_stream_span["context"]["span_id"]

    assert model_span["parent"] is not None
    assert model_span["parent"]["span_id"] == agent_span["context"]["span_id"]


def test_chat_stream_trace_records_successful_completion(
    client, capfire: CaptureLogfire
):
    response = _request_successful_chat(client)

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == (
        'event: delta\ndata: {"content":"안녕"}\n\n'
        'event: delta\ndata: {"content":"하세요"}\n\n'
        "event: done\ndata: {}\n\n"
    )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "done"
    assert "error.type" not in chat_stream_span["attributes"]

    chat_stream_exported_span = next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )
    assert chat_stream_exported_span.status.status_code is StatusCode.UNSET

    time_to_first_delta_ms = chat_stream_span["attributes"].get(
        "chat.time_to_first_delta_ms"
    )

    assert isinstance(time_to_first_delta_ms, int | float)
    assert time_to_first_delta_ms >= 0


def test_chat_stream_trace_excludes_prompt_and_response_content(
    client, capfire: CaptureLogfire
):
    _request_successful_chat(client)

    chat_stream_span = _get_chat_stream_span(capfire)
    serialized_chat_stream_attributes = str(chat_stream_span["attributes"])

    assert "안녕?" not in serialized_chat_stream_attributes
    assert "안녕" not in serialized_chat_stream_attributes
    assert "하세요" not in serialized_chat_stream_attributes


@pytest.mark.parametrize(
    ("model_output", "expected_delta"),
    [
        pytest.param("", "", id="empty"),
        pytest.param(
            "   ", 'event: delta\ndata: {"content":"   "}\n\n', id="whitespace-only"
        ),
    ],
)
def test_chat_stream_trace_records_invalid_response_for_blank_model_output(
    client,
    capfire: CaptureLogfire,
    model_output,
    expected_delta,
):
    async def stream_blank_content(messages, _):
        yield model_output

    with main_module.assistant.override(
        model=FunctionModel(stream_function=stream_blank_content)
    ):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == (
        expected_delta + "event: error\n"
        'data: {"code":"invalid_response",'
        '"message":"Invalid chat response"}\n\n'
    )

    chat_stream_span = _get_chat_stream_span(capfire)
    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "invalid_response"
    assert "chat.time_to_first_delta_ms" not in chat_stream_span["attributes"]

    chat_stream_exported_span = next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )

    assert chat_stream_exported_span.status.status_code is StatusCode.ERROR


def test_chat_stream_trace_records_invalid_response_for_unexpected_model_behavior(
    client, capfire: CaptureLogfire
):
    async def stream_unexpected_behavior(messages, _):
        yield "부분 응답"
        raise UnexpectedModelBehavior("sensitive model detail")

    with main_module.assistant.override(
        model=FunctionModel(stream_function=stream_unexpected_behavior)
    ):
        response = client.post("/chat", json={"content": "질문"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"invalid_response","message":"Invalid chat response"}\n\n'
    )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "invalid_response"

    time_to_first_delta_ms = chat_stream_span["attributes"].get(
        "chat.time_to_first_delta_ms"
    )
    assert isinstance(time_to_first_delta_ms, int | float)
    assert time_to_first_delta_ms >= 0

    chat_stream_exported_span = next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )

    assert chat_stream_exported_span.status.status_code is StatusCode.ERROR


def test_chat_stream_trace_records_model_error_for_model_api_failure(
    client,
    capfire: CaptureLogfire,
):
    async def fail_model_request(messages, _):
        yield "부분 응답"
        raise ModelAPIError(model_name="test", message="sensitive provider detail")

    with main_module.assistant.override(
        model=FunctionModel(stream_function=fail_model_request)
    ):
        response = client.post("/chat", json={"content": "질문"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"model_error",'
        '"message":"Failed to generate chat response"}\n\n'
    )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "model_error"

    time_to_first_delta_ms = chat_stream_span["attributes"].get(
        "chat.time_to_first_delta_ms"
    )
    assert isinstance(time_to_first_delta_ms, int | float)
    assert time_to_first_delta_ms >= 0

    chat_stream_exported_span = next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )

    assert chat_stream_exported_span.status.status_code is StatusCode.ERROR


def test_chat_stream_trace_records_timeout_for_chat_deadline(
    client,
    capfire: CaptureLogfire,
    monkeypatch,
):
    async def respond_after_timeout(messages, _):
        yield "부분 응답"
        await asyncio.sleep(0.1)
        yield "늦은 응답"

    monkeypatch.setattr(main_module.settings, "chat_timeout_seconds", 0.05)

    with main_module.assistant.override(
        model=FunctionModel(stream_function=respond_after_timeout)
    ):
        response = client.post("/chat", json={"content": "질문"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"chat_timeout",'
        '"message":"Chat response timed out"}\n\n'
    )

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "timeout"

    time_to_first_delta_ms = chat_stream_span["attributes"].get(
        "chat.time_to_first_delta_ms"
    )
    assert isinstance(time_to_first_delta_ms, int | float)
    assert time_to_first_delta_ms >= 0

    chat_stream_exported_span = next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )

    assert chat_stream_exported_span.status.status_code is StatusCode.ERROR


def test_chat_stream_trace_records_internal_error_without_sensitive_details(
    client,
    capfire: CaptureLogfire,
):
    sensitive_exception_message = "sensitive internal detail"

    async def raise_unexpected_error(messages, _):
        yield "부분 응답"
        raise RuntimeError(sensitive_exception_message)

    with main_module.assistant.override(
        model=FunctionModel(stream_function=raise_unexpected_error)
    ):
        response = client.post("/chat", json={"content": "민감한 질문"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"internal_error",'
        '"message":"Failed to generate chat response"}\n\n'
    )
    assert sensitive_exception_message not in response.text

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "internal_error"

    time_to_first_delta_ms = chat_stream_span["attributes"].get(
        "chat.time_to_first_delta_ms"
    )
    assert isinstance(time_to_first_delta_ms, int | float)
    assert time_to_first_delta_ms >= 0

    serialized_chat_stream_span = str(chat_stream_span)
    assert sensitive_exception_message not in serialized_chat_stream_span
    assert "민감한 질문" not in serialized_chat_stream_span
    assert "부분 응답" not in serialized_chat_stream_span
    assert "exception.stacktrace" not in serialized_chat_stream_span

    chat_stream_exported_span = next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )

    assert chat_stream_exported_span.status.status_code is StatusCode.ERROR
    assert chat_stream_exported_span.status.description is None


@pytest.mark.parametrize(
    ("send_exception_type", "expected_exception_type"),
    [
        pytest.param(OSError, ClientDisconnect, id="client-disconnect"),
        pytest.param(asyncio.CancelledError, asyncio.CancelledError, id="cancellation"),
    ],
)
def test_chat_stream_trace_records_interruption_before_first_delta_as_incomplete_without_error_or_ttft(
    capfire: CaptureLogfire, send_exception_type, expected_exception_type
):
    async def respond(messages, _):
        yield "응답"

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            raise send_exception_type()

    async def interrupt_chat():
        response = await main_module.chat(main_module.ChatRequest(content="질문"))

        with pytest.raises(expected_exception_type):
            await response(
                {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}},
                receive,
                send,
            )

    with main_module.assistant.override(model=FunctionModel(stream_function=respond)):
        asyncio.run(interrupt_chat())

    chat_stream_span = _get_chat_stream_span(capfire)
    chat_stream_attributes = chat_stream_span["attributes"]

    assert chat_stream_span["attributes"].get("chat.outcome") == "incomplete"
    assert "error.type" not in chat_stream_attributes
    assert "chat.time_to_first_delta_ms" not in chat_stream_attributes

    serialized_chat_stream_span = str(chat_stream_span)
    assert "exception.type" not in serialized_chat_stream_span
    assert "exception.stacktrace" not in serialized_chat_stream_span

    chat_stream_exported_span = next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )

    assert chat_stream_exported_span.status.status_code is StatusCode.UNSET


def test_chat_stream_trace_exports_incomplete_span_before_repropagating_cancellation(
    capfire: CaptureLogfire,
):
    cancellation = asyncio.CancelledError()

    async def respond(messages, _):
        yield "응답"

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        if message["type"] == "http.response.start":
            raise cancellation

    async def cancel_chat():
        response = await main_module.chat(main_module.ChatRequest(content="질문"))

        try:
            await response(
                {
                    "type": "http",
                    "asgi": {
                        "version": "3.0",
                        "spec_version": "2.4",
                    },
                },
                receive,
                send,
            )
        except asyncio.CancelledError as propagated_cancellation:
            assert propagated_cancellation is cancellation

            chat_stream_span = _get_chat_stream_span(capfire)
            assert chat_stream_span["attributes"].get("chat.outcome") == "incomplete"

            raise

    with main_module.assistant.override(model=FunctionModel(stream_function=respond)):
        with pytest.raises(asyncio.CancelledError) as raised_cancellation:
            asyncio.run(cancel_chat())

    assert raised_cancellation.value is cancellation


def test_chat_stream_trace_records_incomplete_for_http_disconnect_before_first_delta(
    capfire: CaptureLogfire,
):
    async def respond(messages, _):
        yield "응답"

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        pass

    async def disconnect_chat():
        response = await main_module.chat(main_module.ChatRequest(content="질문"))

        await response(
            {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}},
            receive,
            send,
        )

    with main_module.assistant.override(model=FunctionModel(stream_function=respond)):
        asyncio.run(disconnect_chat())

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "incomplete"


def test_chat_stream_trace_records_internal_error_for_unknown_send_failure(
    capfire: CaptureLogfire,
):
    async def respond(messages, _):
        yield "응답"

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        if message["type"] == "http.response.start":
            raise RuntimeError("unknown send failure")

    async def fail_chat_send():
        response = await main_module.chat(main_module.ChatRequest(content="질문"))

        with pytest.raises(RuntimeError, match="unknown send failure"):
            await response(
                {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}},
                receive,
                send,
            )

    with main_module.assistant.override(model=FunctionModel(stream_function=respond)):
        asyncio.run(fail_chat_send())

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "internal_error"

    chat_stream_exported_span = next(
        span
        for span in capfire.exporter.exported_spans
        if span.context is not None
        and span.context.span_id == chat_stream_span["context"]["span_id"]
    )

    assert chat_stream_exported_span.status.status_code is StatusCode.ERROR


def test_chat_stream_trace_retains_time_to_first_delta_after_delta_disconnect(
    capfire: CaptureLogfire,
):
    async def respond(messages, _):
        yield "부분 응답"

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        if (
            message["type"] == "http.response.body"
            and b"event: delta" in message["body"]
        ):
            raise OSError("client disconnected")

    async def disconnect_chat():
        response = await main_module.chat(main_module.ChatRequest(content="질문"))

        with pytest.raises(ClientDisconnect):
            await response(
                {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}},
                receive,
                send,
            )

    with main_module.assistant.override(model=FunctionModel(stream_function=respond)):
        asyncio.run(disconnect_chat())

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "incomplete"

    time_to_first_delta_ms = chat_stream_span["attributes"].get(
        "chat.time_to_first_delta_ms"
    )

    assert isinstance(time_to_first_delta_ms, int | float)
    assert time_to_first_delta_ms >= 0


def test_chat_stream_trace_preserves_done_after_disconnect_on_done_event(
    capfire: CaptureLogfire,
):
    async def respond(messages, _):
        yield "완료 응답"

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        if (
            message["type"] == "http.response.body"
            and b"event: done" in message["body"]
        ):
            raise OSError("client disconnected")

    async def disconnect_on_done():
        response = await main_module.chat(main_module.ChatRequest(content="질문"))

        with pytest.raises(ClientDisconnect):
            await response(
                {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}},
                receive,
                send,
            )

    with main_module.assistant.override(model=FunctionModel(stream_function=respond)):
        asyncio.run(disconnect_on_done())

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "done"
    assert "error.type" not in chat_stream_span["attributes"]


def test_chat_stream_trace_preserves_error_after_disconnect_on_error_event(
    capfire: CaptureLogfire,
):
    async def respond(messages, _):
        yield ""

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        if (
            message["type"] == "http.response.body"
            and b"event: error" in message["body"]
        ):
            raise OSError("client disconnected")

    async def disconnect_on_error():
        response = await main_module.chat(main_module.ChatRequest(content="질문"))

        with pytest.raises(ClientDisconnect):
            await response(
                {
                    "type": "http",
                    "asgi": {
                        "version": "3.0",
                        "spec_version": "2.4",
                    },
                },
                receive,
                send,
            )

    with main_module.assistant.override(model=FunctionModel(stream_function=respond)):
        asyncio.run(disconnect_on_error())

    chat_stream_span = _get_chat_stream_span(capfire)

    assert chat_stream_span["attributes"].get("chat.outcome") == "error"
    assert chat_stream_span["attributes"].get("error.type") == "invalid_response"
