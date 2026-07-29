import asyncio

import pytest
from fastapi import status
from pydantic_ai import models
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models.function import FunctionModel

import hello_my_assistant_api.main as main_module

models.ALLOW_MODEL_REQUESTS = False


def test_chat_streams_content_when_request_is_valid(client):
    async def stream_response(messages, _):
        yield "안"
        yield "녕하"
        yield "세요"

    with main_module.assistant.override(
        model=FunctionModel(stream_function=stream_response)
    ):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text == (
        'event: delta\ndata: {"content":"안"}\n\n'
        'event: delta\ndata: {"content":"녕하"}\n\n'
        'event: delta\ndata: {"content":"세요"}\n\n'
        "event: done\ndata: {}\n\n"
    )


def test_chat_rejects_request_when_content_is_missing(client):
    response = client.post("/chat", json={})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.parametrize(
    "content", [pytest.param("", id="empty"), pytest.param("   ", id="whitespace-only")]
)
def test_chat_rejects_request_when_content_is_blank(client, content):
    response = client.post("/chat", json={"content": content})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_chat_passes_trimmed_content_to_agent(client):
    async def respond_based_on_current_prompt(messages, _):
        current_prompt_is_trimmed = messages[-1].parts[-1].content == "안녕?"

        yield (
            "content-trimmed" if current_prompt_is_trimmed else "content-not-trimmed"
        )

    with main_module.assistant.override(
        model=FunctionModel(stream_function=respond_based_on_current_prompt)
    ):
        response = client.post("/chat", json={"content": " 안녕? "})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"content-trimmed"}\n\nevent: done\ndata: {}\n\n'
    )


def test_chat_streams_model_error_when_request_fails(client):
    async def fail_model_request(messages, _):
        yield "부분 응답"
        raise ModelAPIError(model_name="test", message="model unavailable")

    with main_module.assistant.override(
        model=FunctionModel(stream_function=fail_model_request)
    ):
        response = client.post("/chat", json={"content": "question"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"model_error",'
        '"message":"Failed to generate chat response"}\n\n'
    )


def test_chat_streams_error_when_agent_run_exceeds_timeout(client, monkeypatch):
    async def respond_after_timeout(messages, _):
        yield "부분 응답"
        await asyncio.sleep(0.1)
        yield "늦은 응답"

    monkeypatch.setattr(main_module.settings, "chat_timeout_seconds", 0.05)

    with main_module.assistant.override(
        model=FunctionModel(stream_function=respond_after_timeout)
    ):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"chat_timeout",'
        '"message":"Chat response timed out"}\n\n'
    )


@pytest.mark.parametrize(
    ("model_content", "expected_delta"),
    [
        pytest.param("", "", id="empty"),
        pytest.param(
            "   ", 'event: delta\ndata: {"content":"   "}\n\n', id="whitespace-only"
        ),
    ],
)
def test_chat_streams_invalid_response_when_model_returns_blank_content(
    client, model_content, expected_delta
):
    async def stream_blank_content(messages, _):
        yield model_content

    with main_module.assistant.override(
        model=FunctionModel(stream_function=stream_blank_content)
    ):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        expected_delta
        + "event: error\n"
        + 'data: {"code":"invalid_response",'
        + '"message":"Invalid chat response"}\n\n'
    )


def test_chat_streams_internal_error_when_unexpected_error_occurs(client):
    async def raise_unexpected_error(messages, _):
        yield "부분 응답"
        raise RuntimeError("sensitive internal detail")

    with main_module.assistant.override(
        model=FunctionModel(stream_function=raise_unexpected_error)
    ):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"internal_error",'
        '"message":"Failed to generate chat response"}\n\n'
    )
    assert "sensitive internal detail" not in response.text


def test_chat_streams_invalid_response_when_model_behavior_is_unexpected(client):
    async def stream_unexpected_behavior(messages, _):
        yield "부분 응답"
        raise UnexpectedModelBehavior("invalid model stream")

    with main_module.assistant.override(
        model=FunctionModel(stream_function=stream_unexpected_behavior)
    ):
        response = client.post("/chat", json={"content": "question"})

    assert response.status_code == status.HTTP_200_OK
    assert response.text == (
        'event: delta\ndata: {"content":"부분 응답"}\n\n'
        "event: error\n"
        'data: {"code":"invalid_response",'
        '"message":"Invalid chat response"}\n\n'
    )


def test_chat_yields_first_delta_before_model_finishes():
    async def verify_stream_timing():
        allow_model_to_finish = asyncio.Event()
        model_finished = asyncio.Event()

        async def controlled_stream(messages, _):
            yield "첫 조각"
            await allow_model_to_finish.wait()
            model_finished.set()
            yield "마지막 조각"

        with main_module.assistant.override(
            model=FunctionModel(stream_function=controlled_stream)
        ):
            events = main_module.stream_chat_response("질문")

            first_event = await asyncio.wait_for(anext(events), timeout=1)

            assert first_event == ('event: delta\ndata: {"content":"첫 조각"}\n\n')
            assert not model_finished.is_set()

            allow_model_to_finish.set()
            remaining_events = [event async for event in events]

            assert model_finished.is_set()
            assert remaining_events == [
                'event: delta\ndata: {"content":"마지막 조각"}\n\n',
                "event: done\ndata: {}\n\n",
            ]

    asyncio.run(verify_stream_timing())
