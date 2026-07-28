import asyncio

import pytest
from fastapi import status
from pydantic_ai import ModelResponse, TextPart, models
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

import hello_my_assistant_api.main as main_module

models.ALLOW_MODEL_REQUESTS = False


def test_chat_returns_content_when_request_is_valid(client):
    with main_module.assistant.override(model=TestModel(custom_output_text="테스트")):
        response = client.post("/chat", json={"content": "안녕하세요"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"content": "테스트"}


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
    def respond_based_on_current_prompt(messages, _):
        current_prompt_is_trimmed = messages[-1].parts[-1].content == "안녕"

        content = (
            "content-trimmed" if current_prompt_is_trimmed else "content-not-trimmed"
        )

        return ModelResponse(parts=[TextPart(content=content)])

    with main_module.assistant.override(
        model=FunctionModel(respond_based_on_current_prompt)
    ):
        response = client.post("/chat", json={"content": " 안녕 "})

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"content": "content-trimmed"}


def test_chat_returns_502_when_request_fails(client):
    def fail_model_request(messages, _):
        raise ModelAPIError(model_name="test", message="model unavailable")

    with main_module.assistant.override(model=FunctionModel(fail_model_request)):
        response = client.post("/chat", json={"content": "question"})

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert response.json() == {"detail": "Failed to generate chat response"}


def test_chat_returns_504_when_agent_run_exceeds_timeout(client, monkeypatch):
    async def respond_after_timeout(messages, _):
        await asyncio.sleep(0.1)

        return ModelResponse(parts=[TextPart(content="late response")])

    monkeypatch.setattr(main_module.settings, "chat_timeout_seconds", 0.001)

    with main_module.assistant.override(model=FunctionModel(respond_after_timeout)):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_504_GATEWAY_TIMEOUT
    assert response.json() == {"detail": "Chat response timed out"}


@pytest.mark.parametrize(
    "model_content",
    [pytest.param("", id="empty"), pytest.param("   ", id="whitespace-only")],
)
def test_chat_returns_502_when_model_returns_blank_content(client, model_content):
    with main_module.assistant.override(
        model=TestModel(custom_output_text=model_content)
    ):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert response.json() == {"detail": "Invalid chat response"}


def test_chat_returns_500_when_unexpected_error_occurs(client):
    def raise_unexpected_error(messages, _):
        raise RuntimeError("unexpected error")

    with main_module.assistant.override(model=FunctionModel(raise_unexpected_error)):
        response = client.post("/chat", json={"content": "안녕?"})

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
