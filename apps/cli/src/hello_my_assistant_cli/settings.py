from pydantic import HttpUrl, PositiveFloat
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    assistant_base_url: HttpUrl = HttpUrl("http://127.0.0.1:8000")
    assistant_timeout_seconds: PositiveFloat = 70.0
