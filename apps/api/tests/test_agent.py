from pydantic_ai.models.openai import OpenAIChatModel

import hello_my_assistant_api.agent as agent_module
import hello_my_assistant_api.main as main_module
from hello_my_assistant_api.settings import Settings


def test_create_assistant_configures_openai_chat_model():
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model_name="test-model",
        llm_api_key="test-key",
        chat_timeout_seconds=30,
        _env_file=None,
    )

    assistant = agent_module.create_assistant(settings)

    assert isinstance(assistant.model, OpenAIChatModel)
    assert assistant.model.model_name == "test-model"
    assert assistant.model.base_url == "http://127.0.0.1:8080/v1/"
    assert assistant.model.provider.client.api_key == "test-key"


def test_application_uses_configured_openai_chat_model():

    assert isinstance(main_module.assistant.model, OpenAIChatModel)
    assert main_module.assistant.model.model_name == main_module.settings.llm_model_name
