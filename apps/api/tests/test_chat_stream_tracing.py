from fastapi import status
from logfire.testing import CaptureLogfire
from opentelemetry.trace import StatusCode
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
