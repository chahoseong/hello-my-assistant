from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)

    @field_validator("messages")
    @classmethod
    def validate_last_message_is_from_user(
        cls, messages: list[Message]
    ) -> list[Message]:
        if messages[-1].role != "user":
            raise ValueError("last message must be from user")

        return messages


class ChatResponse(BaseModel):
    content: str
