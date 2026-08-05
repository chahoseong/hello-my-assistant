import json
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from logfire.query_client import LogfireQueryClient

type LogfireRecord = dict[str, Any]


class TraceVerificationError(RuntimeError):
    """Raised when an exported trace does not satisfy the observability contract."""


def wait_for_trace(
    *,
    read_token: str,
    trace_id: str,
    started_at: datetime,
    timeout_seconds: float,
    query_url: str | None,
) -> list[LogfireRecord]:
    traces = wait_for_traces(
        read_token=read_token,
        trace_ids={"scenario": trace_id},
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        query_url=query_url,
    )
    return traces["scenario"]


def wait_for_traces(
    *,
    read_token: str,
    trace_ids: dict[str, str],
    started_at: datetime,
    timeout_seconds: float,
    query_url: str | None,
) -> dict[str, list[LogfireRecord]]:
    quoted_trace_ids = ", ".join(f"'{trace_id}'" for trace_id in trace_ids.values())
    sql = f"""
        SELECT
            trace_id,
            span_name,
            span_id,
            parent_span_id,
            attributes,
            level_name(level) AS level_name,
            message,
            log_body
        FROM records
        WHERE trace_id IN ({quoted_trace_ids})
    """
    deadline = time.monotonic() + timeout_seconds
    delay_seconds = 1.0

    with LogfireQueryClient(read_token=read_token, base_url=query_url) as client:
        while True:
            try:
                result = client.query_json_rows(
                    sql=sql,
                    min_timestamp=started_at,
                    limit=300,
                )
            except AssertionError as error:
                if "Rate limit exceeded" not in str(error):
                    raise
                records = []
            else:
                records = list(result["rows"])
            records_by_scenario = {
                scenario: [
                    record for record in records if record.get("trace_id") == trace_id
                ]
                for scenario, trace_id in trace_ids.items()
            }
            missing_scenarios = [
                scenario
                for scenario, scenario_records in records_by_scenario.items()
                if not any(
                    record.get("span_name") == "chat.stream"
                    for record in scenario_records
                )
            ]
            if not missing_scenarios:
                return records_by_scenario

            if time.monotonic() >= deadline:
                raise TraceVerificationError(
                    "Logfire did not return the expected chat.stream spans for "
                    f"{', '.join(missing_scenarios)} within "
                    f"{timeout_seconds:g} seconds"
                )

            time.sleep(delay_seconds)
            delay_seconds = min(delay_seconds * 2, 2.0)


def verify_success_trace(
    records: Sequence[LogfireRecord], *, sensitive_marker: str
) -> None:
    chat_stream_span = _verify_core_trace(records, sensitive_marker=sensitive_marker)
    chat_attributes = _attributes(chat_stream_span)

    if chat_attributes.get("chat.outcome") != "done":
        raise TraceVerificationError("chat.stream did not record chat.outcome=done")

    if "error.type" in chat_attributes:
        raise TraceVerificationError(
            "successful chat.stream unexpectedly has error.type"
        )

    _require_first_delta_timing(chat_attributes, scenario="successful")

    if chat_stream_span.get("level_name") == "error":
        raise TraceVerificationError("successful chat.stream has an error level")


def verify_model_error_trace(
    records: Sequence[LogfireRecord], *, sensitive_marker: str
) -> None:
    chat_stream_span = _verify_core_trace(records, sensitive_marker=sensitive_marker)
    chat_attributes = _attributes(chat_stream_span)

    if chat_attributes.get("chat.outcome") != "error":
        raise TraceVerificationError("chat.stream did not record chat.outcome=error")

    if chat_attributes.get("error.type") != "model_error":
        raise TraceVerificationError(
            "chat.stream did not record error.type=model_error"
        )

    if chat_stream_span.get("level_name") != "error":
        raise TraceVerificationError("model error chat.stream has no error level")

    if "chat.time_to_first_delta_ms" in chat_attributes:
        raise TraceVerificationError(
            "model error chat.stream unexpectedly recorded a first delta"
        )


def verify_incomplete_trace(
    records: Sequence[LogfireRecord], *, sensitive_marker: str
) -> None:
    chat_stream_span = _verify_core_trace(records, sensitive_marker=sensitive_marker)
    chat_attributes = _attributes(chat_stream_span)

    if chat_attributes.get("chat.outcome") != "incomplete":
        raise TraceVerificationError(
            "chat.stream did not record chat.outcome=incomplete"
        )

    if "error.type" in chat_attributes:
        raise TraceVerificationError(
            "incomplete chat.stream unexpectedly has error.type"
        )

    _require_first_delta_timing(chat_attributes, scenario="incomplete")

    if chat_stream_span.get("level_name") == "error":
        raise TraceVerificationError("incomplete chat.stream has an error level")


def _verify_core_trace(
    records: Sequence[LogfireRecord], *, sensitive_marker: str
) -> LogfireRecord:
    http_span = _find_one(
        records,
        description="HTTP /chat span",
        predicate=lambda record: _attributes(record).get("http.route") == "/chat",
    )
    chat_stream_span = _find_one(
        records,
        description="chat.stream span",
        predicate=lambda record: record.get("span_name") == "chat.stream",
    )
    agent_span = _find_one(
        records,
        description="Agent span",
        predicate=lambda record: (
            _attributes(record).get("gen_ai.operation.name") == "invoke_agent"
        ),
    )
    model_span = _find_one(
        records,
        description="Model span",
        predicate=lambda record: (
            _attributes(record).get("gen_ai.operation.name") == "chat"
        ),
    )

    _require_parent(chat_stream_span, http_span, child_name="chat.stream")
    _require_parent(agent_span, chat_stream_span, child_name="Agent")
    _require_parent(model_span, agent_span, child_name="Model")

    relevant_records = [http_span, chat_stream_span, agent_span, model_span]
    sensitive_locations = [
        location
        for record in relevant_records
        for location in _find_sensitive_locations(record, sensitive_marker)
    ]
    if sensitive_locations:
        raise TraceVerificationError(
            "request content was captured in: " + ", ".join(sensitive_locations)
        )

    return chat_stream_span


def _require_first_delta_timing(
    chat_attributes: dict[str, Any], *, scenario: str
) -> None:
    first_delta_ms = chat_attributes.get("chat.time_to_first_delta_ms")
    if not isinstance(first_delta_ms, int | float) or first_delta_ms < 0:
        raise TraceVerificationError(
            f"{scenario} chat.stream has no valid chat.time_to_first_delta_ms"
        )


def _find_one(
    records: Sequence[LogfireRecord],
    *,
    description: str,
    predicate: Any,
) -> LogfireRecord:
    matches = [record for record in records if predicate(record)]
    if len(matches) != 1:
        raise TraceVerificationError(
            f"expected one {description}, found {len(matches)}"
        )

    return matches[0]


def _attributes(record: LogfireRecord) -> dict[str, Any]:
    attributes = record.get("attributes")
    if isinstance(attributes, dict):
        return attributes
    if isinstance(attributes, str):
        parsed = json.loads(attributes)
        if isinstance(parsed, dict):
            return parsed

    raise TraceVerificationError("Logfire record has invalid attributes")


def _require_parent(
    child: LogfireRecord, parent: LogfireRecord, *, child_name: str
) -> None:
    if child.get("parent_span_id") != parent.get("span_id"):
        raise TraceVerificationError(f"{child_name} span has an unexpected parent")


def _find_sensitive_locations(
    record: LogfireRecord, sensitive_marker: str
) -> list[str]:
    span_name = str(record.get("span_name", "unknown span"))
    locations: list[str] = []

    for field in ("attributes", "message", "log_body"):
        value = record.get(field)
        if sensitive_marker in json.dumps(value, ensure_ascii=False, default=str):
            locations.append(f"{span_name}.{field}")

    return locations
