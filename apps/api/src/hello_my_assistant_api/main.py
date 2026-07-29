import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior

from .agent import create_assistant
from .schemas import ChatRequest
from .settings import Settings

app = FastAPI()
settings = Settings()
assistant = create_assistant(settings)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World"}


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_chat_response(request.content),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def stream_chat_response(content: str) -> AsyncIterator[str]:
    has_result = False

    try:
        async with asyncio.timeout(settings.chat_timeout_seconds):
            async with assistant.run_stream(content) as result:
                async for chunk in result.stream_text(delta=True, debounce_by=None):
                    if chunk:
                        has_result |= bool(chunk.strip())
                        yield encode_sse("delta", {"content": chunk})

        if has_result:
            yield encode_sse("done", {})
        else:
            yield encode_sse(
                "error",
                {"code": "invalid_response", "message": "Invalid chat response"},
            )

    except UnexpectedModelBehavior:
        yield encode_sse(
            "error", {"code": "invalid_response", "message": "Invalid chat response"}
        )
    except ModelAPIError:
        yield encode_sse(
            "error",
            {"code": "model_error", "message": "Failed to generate chat response"},
        )
    except TimeoutError:
        yield encode_sse(
            "error", {"code": "chat_timeout", "message": "Chat response timed out"}
        )
    except Exception:
        yield encode_sse(
            "error",
            {"code": "internal_error", "message": "Failed to generate chat response"},
        )


def encode_sse(event: str, data: dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
