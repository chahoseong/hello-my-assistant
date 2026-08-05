import pytest
from fastapi import status
from pydantic_ai.models.function import FunctionModel


def test_chat_endpoint_returns_event_stream_when_request_is_valid(client, agent):
    async def stream_response(messages, _):
        yield "안"
        yield "녕하"
        yield "세요"

    with agent.override(model=FunctionModel(stream_function=stream_response)):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text == (
        'event: delta\ndata: {"content":"안"}\n\n'
        'event: delta\ndata: {"content":"녕하"}\n\n'
        'event: delta\ndata: {"content":"세요"}\n\n'
        "event: done\ndata: {}\n\n"
    )


def test_chat_endpoint_rejects_request_when_content_is_missing(client):
    response = client.post("/chat", json={})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    "content",
    [pytest.param("", id="empty"), pytest.param("   ", id="whitespace-only")],
)
def test_chat_endpoint_rejects_request_when_content_is_blank(client, content):
    response = client.post("/chat", json={"content": content})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_chat_endpoint_trims_content_before_forwarding_request(client, agent):
    async def respond_based_on_current_prompt(messages, _):
        current_prompt_is_trimmed = messages[-1].parts[-1].content == "안녕?"
        yield (
            "content-trimmed" if current_prompt_is_trimmed else "content-not-trimmed"
        )

    with agent.override(
        model=FunctionModel(stream_function=respond_based_on_current_prompt)
    ):
        response = client.post("/chat", json={"content": " 안녕? "})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"content-trimmed"}\n\nevent: done\ndata: {}\n\n'
    )
