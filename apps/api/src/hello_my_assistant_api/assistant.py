import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior

type AssistantFailureKind = Literal[
    "invalid_response", "model_error", "timeout", "internal_error"
]


@dataclass(frozen=True)
class AssistantDelta:
    content: str


@dataclass(frozen=True)
class AssistantCompleted:
    pass


@dataclass(frozen=True)
class AssistantFailed:
    kind: AssistantFailureKind


type AssistantEvent = AssistantDelta | AssistantCompleted | AssistantFailed


class Assistant:
    def __init__(self, agent: Agent[None, str], *, timeout_seconds: float) -> None:
        self._agent = agent
        self._timeout_seconds = timeout_seconds

    async def respond(self, content: str) -> AsyncIterator[AssistantEvent]:
        has_result = False

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._agent.run_stream(content) as result:
                    async for chunk in result.stream_text(delta=True, debounce_by=None):
                        if not chunk:
                            continue

                        if chunk.strip():
                            has_result = True

                        yield AssistantDelta(content=chunk)

            if has_result:
                yield AssistantCompleted()
            else:
                yield AssistantFailed(kind="invalid_response")
        except UnexpectedModelBehavior:
            yield AssistantFailed(kind="invalid_response")
        except ModelAPIError:
            yield AssistantFailed(kind="model_error")
        except TimeoutError:
            yield AssistantFailed(kind="timeout")
        except Exception:
            yield AssistantFailed(kind="internal_error")
