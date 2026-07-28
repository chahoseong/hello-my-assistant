import asyncio

from fastapi import FastAPI, HTTPException, status
from pydantic_ai.exceptions import (
    ModelAPIError,
    UnexpectedModelBehavior,
)

from .agent import create_assistant
from .schemas import ChatRequest, ChatResponse
from .settings import Settings

app = FastAPI()
settings = Settings()
assistant = create_assistant(settings)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World"}


@app.post("/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        async with asyncio.timeout(settings.chat_timeout_seconds):
            result = await assistant.run(request.content)
    except UnexpectedModelBehavior as ex:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid chat response"
        ) from ex
    except TimeoutError as ex:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Chat response timed out",
        ) from ex
    except ModelAPIError as ex:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate chat response",
        ) from ex

    if not result.output.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Invalid chat response"
        )

    return ChatResponse(content=result.output)
