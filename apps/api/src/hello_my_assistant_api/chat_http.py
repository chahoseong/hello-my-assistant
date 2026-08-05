from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, StringConstraints

from ._chat_streaming_response import ChatStreamingResponse
from .assistant import Assistant


class ChatRequest(BaseModel):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def create_chat_router(assistant: Assistant) -> APIRouter:
    router = APIRouter()

    @router.post("/chat")
    async def chat(request: ChatRequest) -> ChatStreamingResponse:
        return ChatStreamingResponse(assistant.respond(request.content))

    return router
