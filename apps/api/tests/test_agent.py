from pydantic_ai.models.openai import OpenAIChatModel

import hello_my_assistant_api.agent as agent_module
from hello_my_assistant_api.settings import Settings


def test_create_agent_configures_openai_chat_model():
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model_name="test-model",
        llm_api_key="test-key",
        chat_timeout_seconds=30,
        _env_file=None,
    )

    agent = agent_module.create_agent(settings)

    assert isinstance(agent.model, OpenAIChatModel)
    assert agent.model.model_name == "test-model"
    assert agent.model.base_url == "http://127.0.0.1:8080/v1/"
    assert agent.model.provider.client.api_key == "test-key"
