from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .settings import Settings


def create_assistant(settings: Settings) -> Agent[None, str]:
    provider = OpenAIProvider(
        base_url=str(settings.llm_base_url),
        api_key=settings.llm_api_key.get_secret_value(),
    )

    model = OpenAIChatModel(settings.llm_model_name, provider=provider)

    return Agent(model)
