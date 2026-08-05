import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import logfire
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from starlette.requests import ClientDisconnect
from starlette.types import Receive, Scope, Send

from .assistant import (
    AssistantCompleted,
    AssistantDelta,
    AssistantEvent,
    AssistantFailed,
    AssistantFailureKind,
)

type _ChatStreamOutcome = Literal["done", "error", "incomplete"]


@dataclass
class _ChatStreamObservation:
    started_at: float
    outcome: _ChatStreamOutcome | None = None
    error_type: AssistantFailureKind | None = None
    time_to_first_delta_ms: float | None = None

    def mark_done(self) -> None:
        self.outcome = "done"

    def mark_first_delta(self) -> None:
        if self.time_to_first_delta_ms is None:
            self.time_to_first_delta_ms = (perf_counter() - self.started_at) * 1000

    def mark_error(self, error_type: AssistantFailureKind) -> None:
        self.outcome = "error"
        self.error_type = error_type

    def mark_incomplete(self) -> None:
        if self.outcome is None:
            self.outcome = "incomplete"


class ChatStreamingResponse(StreamingResponse):
    def __init__(self, events: AsyncIterator[AssistantEvent]) -> None:
        self._events = events
        self._observation: _ChatStreamObservation | None = None
        super().__init__(
            self._stream_events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        interruption: ClientDisconnect | asyncio.CancelledError | None = None
        failure: Exception | None = None

        with logfire.span("chat.stream") as span:
            observation = _ChatStreamObservation(started_at=perf_counter())
            self._observation = observation

            try:
                try:
                    await super().__call__(scope, receive, send)
                except (ClientDisconnect, asyncio.CancelledError) as exc:
                    observation.mark_incomplete()
                    interruption = exc
                except Exception as exc:
                    observation.mark_error("internal_error")
                    failure = exc
                else:
                    observation.mark_incomplete()
                finally:
                    if observation.outcome is not None:
                        span.set_attribute("chat.outcome", observation.outcome)

                    if observation.error_type is not None:
                        span.set_attribute("error.type", observation.error_type)
                        trace.get_current_span().set_status(Status(StatusCode.ERROR))

                    if observation.time_to_first_delta_ms is not None:
                        span.set_attribute(
                            "chat.time_to_first_delta_ms",
                            observation.time_to_first_delta_ms,
                        )
            finally:
                self._observation = None

        if interruption is not None:
            raise interruption

        if failure is not None:
            raise failure

    async def _stream_events(self) -> AsyncIterator[str]:
        observation = self._observation
        if observation is None:
            raise RuntimeError("ChatStreamingResponse must be called before streaming")

        async for event in self._events:
            match event:
                case AssistantDelta(content=content):
                    if content.strip():
                        observation.mark_first_delta()

                    yield _encode_sse("delta", {"content": content})
                case AssistantCompleted():
                    observation.mark_done()
                    yield _encode_sse("done", {})
                case AssistantFailed(kind=kind):
                    observation.mark_error(kind)
                    yield _encode_chat_error(kind)


def _encode_chat_error(kind: AssistantFailureKind) -> str:
    match kind:
        case "invalid_response":
            return _encode_sse(
                "error",
                {"code": "invalid_response", "message": "Invalid chat response"},
            )
        case "model_error":
            return _encode_sse(
                "error",
                {
                    "code": "model_error",
                    "message": "Failed to generate chat response",
                },
            )
        case "timeout":
            return _encode_sse(
                "error",
                {"code": "chat_timeout", "message": "Chat response timed out"},
            )
        case "internal_error":
            return _encode_sse(
                "error",
                {
                    "code": "internal_error",
                    "message": "Failed to generate chat response",
                },
            )


def _encode_sse(event: str, data: dict[str, object]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"
