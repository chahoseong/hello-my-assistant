import os

import pytest
from fastapi.testclient import TestClient

os.environ["LLM_BASE_URL"] = "http://127.0.0.1:8080/v1"
os.environ["LLM_MODEL_NAME"] = "test-model"
os.environ["LLM_API_KEY"] = "test-key"
os.environ["CHAT_TIMEOUT_SECONDS"] = "30"
os.environ["LOGFIRE_SEND_TO_LOGFIRE"] = "false"

from hello_my_assistant_api.main import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
