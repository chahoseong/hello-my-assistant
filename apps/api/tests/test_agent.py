from pydantic_ai import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    models,
)
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel

import hello_my_assistant_api.agent as agent_module
from hello_my_assistant_api.settings import Settings

models.ALLOW_MODEL_REQUESTS = False


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


def test_create_agent_executes_current_datetime_tool_when_model_requests_it():
    def request_current_datetime(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("get_current_datetime", {"timezone": "Asia/Seoul"})]
            )

        tool_return = messages[-1].parts[0]
        assert isinstance(tool_return, ToolReturnPart)

        return ModelResponse(parts=[TextPart(str(tool_return.content))])

    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model_name="test-model",
        llm_api_key="test-key",
        chat_timeout_seconds=30,
        _env_file=None,
    )
    agent = agent_module.create_agent(settings)

    with agent.override(model=FunctionModel(request_current_datetime)):
        result = agent.run_sync("서울은 지금 몇 시야?")

    assert "Asia/Seoul" in result.output


def test_create_agent_exposes_current_datetime_tool_contract_to_model():
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model_name="test-model",
        llm_api_key="test-key",
        chat_timeout_seconds=30,
        _env_file=None,
    )
    agent = agent_module.create_agent(settings)
    test_model = TestModel(call_tools=[])

    with agent.override(model=test_model):
        agent.run_sync("현재 날짜와 시간을 확인하고 싶어.")

    request_parameters = test_model.last_model_request_parameters
    assert request_parameters is not None

    tool = next(
        tool
        for tool in request_parameters.function_tools
        if tool.name == "get_current_datetime"
    )

    assert (
        tool.description == "Get the current local date and time for an IANA time zone."
    )
    assert (
        tool.parameters_json_schema["properties"]["timezone"]["description"]
        == "An IANA time zone name, such as Asia/Seoul."
    )


def test_create_agent_returns_response_when_current_datetime_timezone_is_invalid():
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model_name="test-model",
        llm_api_key="test-key",
        chat_timeout_seconds=30,
        _env_file=None,
    )

    async def model_function(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> ModelResponse:
        retry_parts = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, RetryPromptPart)
        ]

        if not retry_parts:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_current_datetime",
                        args={"timezone": "Asia/Seoull"},
                    )
                ]
            )

        assert retry_parts[-1].content == ("Unknown IANA time zone: Asia/Seoull")

        return ModelResponse(parts=[TextPart("The time zone is invalid.")])

    agent = agent_module.create_agent(settings)

    with agent.override(model=FunctionModel(model_function)):
        result = agent.run_sync(
            'IANA 시간대 이름 "Asia/Seoull"을 수정하지 말고 그대로 사용해서 현재 날짜와 시간을 조회해줘.'
        )

    assert result.output == "The time zone is invalid."
