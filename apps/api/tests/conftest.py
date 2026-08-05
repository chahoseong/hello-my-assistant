import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent, models
from pydantic_ai.models.function import FunctionModel

from hello_my_assistant_api.app import create_app
from hello_my_assistant_api.assistant import Assistant

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def agent():
    async def unused_response(messages, _):
        yield "unused"

    return Agent(FunctionModel(stream_function=unused_response))


@pytest.fixture
def assistant(agent):
    return Assistant(agent, timeout_seconds=30)


@pytest.fixture
def app(assistant):
    return create_app(assistant)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
