from pydantic import HttpUrl, PositiveFloat, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_base_url: HttpUrl
    llm_model_name: str
    llm_api_key: SecretStr
    chat_timeout_seconds: PositiveFloat = 60.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("llm_model_name", "llm_api_key", mode="before")
    @classmethod
    def reject_blank_llm_setting(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Value must not be blank")

        return value
