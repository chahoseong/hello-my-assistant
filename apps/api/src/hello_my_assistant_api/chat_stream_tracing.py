from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

import logfire
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

type _ChatStreamOutcome = Literal["done", "error", "incomplete"]


@dataclass
class _ChatStreamObservation:
    started_at: float
    outcome: _ChatStreamOutcome | None = None
    time_to_first_delta_ms: float | None = None

    def mark_done(self) -> None:
        self.outcome = "done"

    def mark_first_delta(self) -> None:
        if self.time_to_first_delta_ms is None:
            self.time_to_first_delta_ms = (perf_counter() - self.started_at) * 1000


_current_chat_stream_observation: ContextVar[_ChatStreamObservation | None] = (
    ContextVar("current_chat_stream_observation", default=None)
)


def mark_chat_stream_done() -> None:
    observation = _current_chat_stream_observation.get()
    if observation is not None:
        observation.mark_done()


def mark_chat_stream_first_delta() -> None:
    observation = _current_chat_stream_observation.get()
    if observation is not None:
        observation.mark_first_delta()


class TracedChatStreamingResponse(StreamingResponse):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        with logfire.span("chat.stream") as span:
            observation = _ChatStreamObservation(started_at=perf_counter())
            token = _current_chat_stream_observation.set(observation)

            try:
                await super().__call__(scope, receive, send)

                if observation.outcome is not None:
                    span.set_attribute("chat.outcome", observation.outcome)

                if observation.time_to_first_delta_ms is not None:
                    span.set_attribute(
                        "chat.time_to_first_delta_ms",
                        observation.time_to_first_delta_ms,
                    )
            finally:
                _current_chat_stream_observation.reset(token)
