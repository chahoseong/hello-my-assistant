import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO, Literal

import httpx
from pydantic import PositiveFloat, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from .logfire_trace import (
    TraceVerificationError,
    verify_incomplete_trace,
    verify_model_error_trace,
    verify_success_trace,
    wait_for_traces,
)

type _Scenario = Literal["success", "model-error", "disconnect-after-delta"]

_API_ROOT = Path(__file__).resolve().parents[3]
_SENSITIVE_MARKER = "OBSERVABILITY_E2E_PRIVATE_MARKER"
_ALL_SCENARIOS: tuple[_Scenario, ...] = (
    "success",
    "model-error",
    "disconnect-after-delta",
)


class _E2ESettings(BaseSettings):
    logfire_read_token: SecretStr
    logfire_query_url: str | None = None
    logfire_ingest_timeout_seconds: PositiveFloat = 90.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def main() -> None:
    scenarios = _parse_scenarios()
    try:
        settings = _E2ESettings()
    except ValidationError:
        raise SystemExit(
            "E2E configuration is invalid; set LOGFIRE_READ_TOKEN in the "
            "environment or apps/api/.env"
        ) from None

    started_at = datetime.now(UTC) - timedelta(seconds=1)
    trace_ids: dict[str, str] = {}

    if "success" in scenarios:
        trace_ids["success"] = _run_success_scenario()

    fault_scenarios: list[Literal["model-error", "disconnect-after-delta"]] = []
    if "model-error" in scenarios:
        fault_scenarios.append("model-error")
    if "disconnect-after-delta" in scenarios:
        fault_scenarios.append("disconnect-after-delta")
    if fault_scenarios:
        with _running_uvicorn(
            "tests.e2e.observability.fault_model:app"
        ) as fault_model_url:
            for scenario in fault_scenarios:
                trace_ids[scenario] = _run_fault_scenario(
                    scenario, fault_model_url=fault_model_url
                )

    records_by_scenario = wait_for_traces(
        read_token=settings.logfire_read_token.get_secret_value(),
        trace_ids=trace_ids,
        started_at=started_at,
        timeout_seconds=float(settings.logfire_ingest_timeout_seconds),
        query_url=settings.logfire_query_url,
    )

    for selected_scenario in scenarios:
        records = records_by_scenario[selected_scenario]
        if selected_scenario == "success":
            verify_success_trace(records, sensitive_marker=_SENSITIVE_MARKER)
        elif selected_scenario == "model-error":
            verify_model_error_trace(records, sensitive_marker=_SENSITIVE_MARKER)
        else:
            verify_incomplete_trace(records, sensitive_marker=_SENSITIVE_MARKER)
        print(
            f"PASS {selected_scenario}: runtime trace satisfies the "
            "observability contract"
        )


def _parse_scenarios() -> tuple[_Scenario, ...]:
    parser = argparse.ArgumentParser(
        description="Validate API observability contracts against Logfire."
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=("all", *_ALL_SCENARIOS),
        default="all",
    )
    selected = parser.parse_args().scenario
    if selected == "all":
        return _ALL_SCENARIOS
    return (selected,)


def _run_success_scenario() -> str:
    trace_id, traceparent = _new_trace_context()
    with _running_uvicorn("hello_my_assistant_api.main:app") as base_url:
        response = httpx.post(
            f"{base_url}/chat",
            headers={"traceparent": traceparent},
            json={"content": _SENSITIVE_MARKER},
            timeout=90.0,
        )
        response.raise_for_status()
        _verify_successful_sse(response.text)
        time.sleep(1.0)
    return trace_id


def _run_fault_scenario(
    scenario: Literal["model-error", "disconnect-after-delta"],
    *,
    fault_model_url: str,
) -> str:
    trace_id, traceparent = _new_trace_context()
    environment = {
        "LLM_BASE_URL": f"{fault_model_url}/v1",
        "LLM_MODEL_NAME": scenario,
        "LLM_API_KEY": "observability-e2e",
    }
    with _running_uvicorn(
        "hello_my_assistant_api.main:app", environment=environment
    ) as base_url:
        if scenario == "model-error":
            response = httpx.post(
                f"{base_url}/chat",
                headers={"traceparent": traceparent},
                json={"content": _SENSITIVE_MARKER},
                timeout=90.0,
            )
            response.raise_for_status()
            _verify_model_error_sse(response.text)
        else:
            _disconnect_after_first_delta(base_url, traceparent=traceparent)
        time.sleep(1.0)
    return trace_id


def _new_trace_context() -> tuple[str, str]:
    trace_id = secrets.token_hex(16)
    parent_span_id = secrets.token_hex(8)
    return trace_id, f"00-{trace_id}-{parent_span_id}-01"


@contextmanager
def _running_uvicorn(
    app_import: str, *, environment: dict[str, str] | None = None
) -> Iterator[str]:
    port = _find_available_port()
    process_environment = os.environ.copy()
    if environment is not None:
        process_environment.update(environment)

    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as process_output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                app_import,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=_API_ROOT,
            env=process_environment,
            stdout=process_output,
            stderr=subprocess.STDOUT,
        )

        try:
            base_url = f"http://127.0.0.1:{port}"
            _wait_until_ready(process, base_url, process_output)
            yield base_url
        finally:
            _stop_process(process)


def _find_available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_until_ready(
    process: subprocess.Popen[bytes], base_url: str, process_output: IO[str]
) -> None:
    deadline = time.monotonic() + 15

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "Process exited before becoming ready:\n"
                f"{_read_process_output(process_output)}"
            )

        try:
            response = httpx.get(f"{base_url}/openapi.json", timeout=0.5)
            if response.is_success:
                return
        except httpx.HTTPError:
            pass

        time.sleep(0.1)

    raise RuntimeError(
        f"Process did not become ready:\n{_read_process_output(process_output)}"
    )


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _read_process_output(process_output: IO[str]) -> str:
    process_output.flush()
    process_output.seek(0)
    return process_output.read()[-4000:]


def _verify_successful_sse(body: str) -> None:
    if "event: delta\n" not in body:
        raise TraceVerificationError("successful chat response has no delta event")
    if not body.endswith("event: done\ndata: {}\n\n"):
        raise TraceVerificationError(
            "successful chat response has no terminal done event"
        )


def _verify_model_error_sse(body: str) -> None:
    events = _parse_sse_events(body.splitlines())
    if (
        len(events) != 1
        or events[0][0] != "error"
        or events[0][1].get("code") != "model_error"
    ):
        raise TraceVerificationError(
            "model failure did not produce one model_error SSE event"
        )


def _disconnect_after_first_delta(base_url: str, *, traceparent: str) -> None:
    with httpx.Client(timeout=90.0) as client:
        with client.stream(
            "POST",
            f"{base_url}/chat",
            headers={"traceparent": traceparent},
            json={"content": _SENSITIVE_MARKER},
        ) as response:
            response.raise_for_status()
            for event, _data in _iter_sse_events(response.iter_lines()):
                if event == "delta":
                    return

    raise TraceVerificationError("disconnect scenario received no delta event")


def _parse_sse_events(lines: Sequence[str]) -> list[tuple[str, dict[str, object]]]:
    return list(_iter_sse_events(lines))


def _iter_sse_events(
    lines: Iterable[str],
) -> Iterator[tuple[str, dict[str, object]]]:
    event_name: str | None = None
    data: dict[str, object] | None = None

    for line in lines:
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            parsed = json.loads(line.removeprefix("data: "))
            if isinstance(parsed, dict):
                data = parsed
        elif not line and event_name is not None and data is not None:
            yield event_name, data
            event_name = None
            data = None


if __name__ == "__main__":
    main()
