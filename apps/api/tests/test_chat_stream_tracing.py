import asyncio

import pytest
from fastapi import status
from logfire.testing import CaptureLogfire
from opentelemetry.trace import StatusCode
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models.function import FunctionModel

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
