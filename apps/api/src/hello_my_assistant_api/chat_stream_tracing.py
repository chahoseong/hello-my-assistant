import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import logfire
from fastapi.responses import StreamingResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from starlette.requests import ClientDisconnect
from starlette.types import Receive, Scope, Send

type _ChatStreamOutcome = Literal["done", "error", "incomplete"]
type ChatStreamErrorType = Literal[
    "invalid_response", "model_error", "timeout", "internal_error"
]


@dataclass
class _ChatStreamObservation:
    started_at: float
    outcome: _ChatStreamOutcome | None = None
    error_type: ChatStreamErrorType | None = None
    time_to_first_delta_ms: float | None = None

    def mark_done(self) -> None:
        self.outcome = "done"

    def mark_first_delta(self) -> None:
        if self.time_to_first_delta_ms is None:
            self.time_to_first_delta_ms = (perf_counter() - self.started_at) * 1000

    def mark_error(self, error_type: ChatStreamErrorType) -> None:
        self.outcome = "error"
        self.error_type = error_type

    def mark_incomplete(self) -> None:
        if self.outcome is None:
            self.outcome = "incomplete"


_current_chat_stream_observation: ContextVar[_ChatStreamObservation | None] = (
    ContextVar("current_chat_stream_observation", default=None)
)


def mark_chat_stream_done() -> None:
    observation = _current_chat_stream_observation.get()
    if observation is not None:
        observation.mark_done()


def mark_chat_stream_error(error_type: ChatStreamErrorType) -> None:
    observation = _current_chat_stream_observation.get()
    if observation is not None:
        observation.mark_error(error_type)


def mark_chat_stream_first_delta() -> None:
    observation = _current_chat_stream_observation.get()
    if observation is not None:
        observation.mark_first_delta()


class TracedChatStreamingResponse(StreamingResponse):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        interruption: ClientDisconnect | asyncio.CancelledError | None = None
        failure: Exception | None = None

        with logfire.span("chat.stream") as span:
            observation = _ChatStreamObservation(started_at=perf_counter())
            token = _current_chat_stream_observation.set(observation)

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
                _current_chat_stream_observation.reset(token)

        if interruption is not None:
            raise interruption

        if failure is not None:
            raise failure
