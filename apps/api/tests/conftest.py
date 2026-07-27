import pytest
from fastapi.testclient import TestClient

from hello_my_assistant_api.main import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
