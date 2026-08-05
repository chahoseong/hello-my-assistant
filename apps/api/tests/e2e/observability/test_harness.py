import pytest
from fastapi.testclient import TestClient

from .__main__ import _verify_model_error_sse
from .fault_model import create_fault_model_app
from .logfire_trace import (
    TraceVerificationError,
    verify_incomplete_trace,
    verify_model_error_trace,
)


def _trace_records(
    *,
    outcome: str,
    error_type: str | None = None,
    level_name: str = "info",
    time_to_first_delta_ms: float | None = None,
) -> list[dict[str, object]]:
    chat_attributes: dict[str, object] = {"chat.outcome": outcome}
    if error_type is not None:
        chat_attributes["error.type"] = error_type
    if time_to_first_delta_ms is not None:
        chat_attributes["chat.time_to_first_delta_ms"] = time_to_first_delta_ms

    return [
        {
            "span_name": "POST /chat",
            "span_id": "http",
            "parent_span_id": "remote-parent",
            "attributes": {"http.route": "/chat"},
            "level_name": "info",
        },
        {
            "span_name": "chat.stream",
            "span_id": "chat",
            "parent_span_id": "http",
            "attributes": chat_attributes,
            "level_name": level_name,
        },
        {
            "span_name": "agent run",
            "span_id": "agent",
            "parent_span_id": "chat",
            "attributes": {"gen_ai.operation.name": "invoke_agent"},
            "level_name": level_name,
        },
        {
            "span_name": "model request",
            "span_id": "model",
            "parent_span_id": "agent",
            "attributes": {"gen_ai.operation.name": "chat"},
            "level_name": level_name,
        },
    ]


def test_model_error_trace_requires_the_expected_error_contract() -> None:
    records = _trace_records(
        outcome="error", error_type="model_error", level_name="error"
    )

    verify_model_error_trace(records, sensitive_marker="private-marker")


def test_model_error_trace_rejects_a_non_error_level() -> None:
    records = _trace_records(outcome="error", error_type="model_error")

    with pytest.raises(TraceVerificationError, match="error level"):
        verify_model_error_trace(records, sensitive_marker="private-marker")


def test_model_error_trace_rejects_delta_timing() -> None:
    records = _trace_records(
        outcome="error",
        error_type="model_error",
        level_name="error",
        time_to_first_delta_ms=12.5,
    )

    with pytest.raises(TraceVerificationError, match="first delta"):
        verify_model_error_trace(records, sensitive_marker="private-marker")


def test_incomplete_trace_requires_delta_timing_without_an_error() -> None:
    records = _trace_records(outcome="incomplete", time_to_first_delta_ms=12.5)

    verify_incomplete_trace(records, sensitive_marker="private-marker")


def test_incomplete_trace_rejects_an_error_type() -> None:
    records = _trace_records(
        outcome="incomplete",
        error_type="internal_error",
        time_to_first_delta_ms=12.5,
    )

    with pytest.raises(TraceVerificationError, match=r"error\.type"):
        verify_incomplete_trace(records, sensitive_marker="private-marker")


def test_trace_verifiers_report_sensitive_field_location_without_its_value() -> None:
    records = _trace_records(
        outcome="error", error_type="model_error", level_name="error"
    )
    records[0]["message"] = "private-marker"

    with pytest.raises(TraceVerificationError) as error:
        verify_model_error_trace(records, sensitive_marker="private-marker")

    assert "POST /chat.message" in str(error.value)
    assert "private-marker" not in str(error.value)


def test_fault_model_returns_a_retryable_provider_error() -> None:
    client = TestClient(create_fault_model_app())

    response = client.post(
        "/v1/chat/completions",
        json={"model": "model-error", "messages": []},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "message": "Synthetic model failure",
            "type": "server_error",
            "code": "observability_e2e_model_error",
        }
    }


def test_fault_model_rejects_unknown_scenarios() -> None:
    client = TestClient(create_fault_model_app())

    response = client.post(
        "/v1/chat/completions",
        json={"model": "unknown", "messages": []},
    )

    assert response.status_code == 400


def test_model_error_sse_requires_the_public_error_code() -> None:
    _verify_model_error_sse(
        'event: error\ndata: {"code":"model_error","message":"safe"}\n\n'
    )

    with pytest.raises(TraceVerificationError, match="model_error"):
        _verify_model_error_sse(
            'event: error\ndata: {"code":"internal_error","message":"safe"}\n\n'
        )
