from logfire.testing import CaptureLogfire
from pydantic_ai.models.function import FunctionModel


def _request_successful_chat(client, agent):
    async def respond(messages, _):
        yield "안녕"
        yield "하세요"

    with agent.override(model=FunctionModel(stream_function=respond)):
        return client.post("/chat", json={"content": "안녕?"})


def _get_chat_stream_span(capfire: CaptureLogfire):
    spans = capfire.exporter.exported_spans_as_dict()
    chat_stream_spans = [span for span in spans if span["name"] == "chat.stream"]

    assert len(chat_stream_spans) == 1

    return chat_stream_spans[0]


def test_chat_trace_links_http_stream_agent_and_model_spans_when_request_is_valid(
    client, agent, capfire: CaptureLogfire
):
    _request_successful_chat(client, agent)

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


def test_chat_trace_excludes_prompt_and_response_content_when_chat_is_streamed(
    client, agent, capfire: CaptureLogfire
):
    _request_successful_chat(client, agent)

    spans = capfire.exporter.exported_spans_as_dict()
    sensitive_contents = ("안녕?", "안녕", "하세요")
    sensitive_content_locations = [
        f"{span['name']}.attributes.{attribute_name}"
        for span in spans
        for attribute_name, attribute_value in span["attributes"].items()
        if any(content in str(attribute_value) for content in sensitive_contents)
    ]

    assert sensitive_content_locations == []
