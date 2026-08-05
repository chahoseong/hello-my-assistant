import asyncio

import pytest
from pydantic_ai import Agent, models
from pydantic_ai.exceptions import ModelAPIError, UnexpectedModelBehavior
from pydantic_ai.models.function import FunctionModel

from hello_my_assistant_api.assistant import (
    Assistant,
    AssistantCompleted,
    AssistantDelta,
    AssistantFailed,
)

models.ALLOW_MODEL_REQUESTS = False


def _make_assistant(stream_function, *, timeout_seconds=30):
    agent = Agent(FunctionModel(stream_function=stream_function))
    return Assistant(agent, timeout_seconds=timeout_seconds)


def test_assistant_emits_completion_after_deltas():
    async def verify_response():
        async def respond(messages, _):
            yield "안"
            yield "녕"

        events = [event async for event in _make_assistant(respond).respond("질문")]

        assert events == [
            AssistantDelta(content="안"),
            AssistantDelta(content="녕"),
            AssistantCompleted(),
        ]

    asyncio.run(verify_response())


@pytest.mark.parametrize(
    ("model_output", "expected_events"),
    [
        pytest.param("", [AssistantFailed(kind="invalid_response")], id="empty"),
        pytest.param(
            "   ",
            [
                AssistantDelta(content="   "),
                AssistantFailed(kind="invalid_response"),
            ],
            id="whitespace-only",
        ),
    ],
)
def test_assistant_emits_invalid_response_when_model_output_is_blank(
    model_output, expected_events
):
    async def verify_response():
        async def respond(messages, _):
            yield model_output

        events = [event async for event in _make_assistant(respond).respond("질문")]

        assert events == expected_events

    asyncio.run(verify_response())


def test_assistant_emits_invalid_response_when_model_behavior_is_unexpected():
    async def verify_response():
        async def fail(messages, _):
            yield "부분 응답"
            raise UnexpectedModelBehavior("invalid stream")

        events = [event async for event in _make_assistant(fail).respond("질문")]

        assert events == [
            AssistantDelta(content="부분 응답"),
            AssistantFailed(kind="invalid_response"),
        ]

    asyncio.run(verify_response())


def test_assistant_emits_model_error_when_model_request_fails():
    async def verify_response():
        async def fail(messages, _):
            yield "부분 응답"
            raise ModelAPIError(model_name="test", message="unavailable")

        events = [event async for event in _make_assistant(fail).respond("질문")]

        assert events == [
            AssistantDelta(content="부분 응답"),
            AssistantFailed(kind="model_error"),
        ]

    asyncio.run(verify_response())


def test_assistant_emits_internal_error_when_unexpected_exception_occurs():
    async def verify_response():
        async def fail(messages, _):
            yield "부분 응답"
            raise RuntimeError("sensitive detail")

        events = [event async for event in _make_assistant(fail).respond("질문")]

        assert events == [
            AssistantDelta(content="부분 응답"),
            AssistantFailed(kind="internal_error"),
        ]

    asyncio.run(verify_response())


def test_assistant_emits_timeout_when_deadline_expires():
    async def verify_response():
        async def respond_after_timeout(messages, _):
            yield "부분 응답"
            await asyncio.sleep(0.1)
            yield "늦은 응답"

        events = [
            event
            async for event in _make_assistant(
                respond_after_timeout, timeout_seconds=0.01
            ).respond("질문")
        ]

        assert events == [
            AssistantDelta(content="부분 응답"),
            AssistantFailed(kind="timeout"),
        ]

    asyncio.run(verify_response())


def test_assistant_propagates_cancellation_when_model_run_is_cancelled():
    async def verify_response():
        cancellation = asyncio.CancelledError()

        async def cancel(messages, _):
            yield "부분 응답"
            raise cancellation

        events = _make_assistant(cancel).respond("질문")

        assert await anext(events) == AssistantDelta(content="부분 응답")

        with pytest.raises(asyncio.CancelledError) as raised_cancellation:
            await anext(events)

        assert raised_cancellation.value is cancellation

    asyncio.run(verify_response())


def test_assistant_emits_first_delta_before_model_finishes():
    async def verify_response():
        allow_model_to_finish = asyncio.Event()
        model_finished = asyncio.Event()

        async def controlled_stream(messages, _):
            yield "첫 조각"
            await allow_model_to_finish.wait()
            model_finished.set()
            yield "마지막 조각"

        events = _make_assistant(controlled_stream).respond("질문")

        first_event = await asyncio.wait_for(anext(events), timeout=1)

        assert first_event == AssistantDelta(content="첫 조각")
        assert not model_finished.is_set()

        allow_model_to_finish.set()
        remaining_events = [event async for event in events]

        assert model_finished.is_set()
        assert remaining_events == [
            AssistantDelta(content="마지막 조각"),
            AssistantCompleted(),
        ]

    asyncio.run(verify_response())
