import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

_MODEL_ERROR = "model-error"
_DISCONNECT_AFTER_DELTA = "disconnect-after-delta"
_SYNTHETIC_DELTA = "synthetic delta"


def create_fault_model_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        payload = await request.json()
        model = payload.get("model") if isinstance(payload, dict) else None

        if model == _MODEL_ERROR:
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "message": "Synthetic model failure",
                        "type": "server_error",
                        "code": "observability_e2e_model_error",
                    }
                },
            )

        if model == _DISCONNECT_AFTER_DELTA:
            return StreamingResponse(
                _stream_delta_until_disconnected(request),
                media_type="text/event-stream",
            )

        return JSONResponse(
            status_code=400,
            content={"error": {"message": "Unknown synthetic model"}},
        )

    return app


async def _stream_delta_until_disconnected(request: Request) -> AsyncIterator[str]:
    chunk = {
        "id": "observability-e2e",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": _SYNTHETIC_DELTA},
                "finish_reason": None,
            }
        ],
        "created": int(time.time()),
        "model": _DISCONNECT_AFTER_DELTA,
        "object": "chat.completion.chunk",
    }
    yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"

    while not await request.is_disconnected():
        await asyncio.sleep(0.1)


app = create_fault_model_app()
