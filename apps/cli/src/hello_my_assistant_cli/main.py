import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import cast

import httpx

from .settings import Settings


class ChatStreamError(Exception):
    pass


@dataclass(frozen=True)
class SSEEvent:
    event: str
    data: dict[str, object]


def main() -> None:
    settings = Settings()

    with create_client(
        base_url=str(settings.assistant_base_url),
        timeout_seconds=settings.assistant_timeout_seconds,
    ) as client:
        while True:
            message = input("> ")

            if message == "/exit":
                return
            if not message.strip():
                continue

            printed_content = False

            try:
                for chunk in stream_message(client, message):
                    print(chunk, end="", flush=True)
                    printed_content |= bool(chunk)
            except httpx.HTTPError, ChatStreamError:
                if printed_content:
                    print()

                print("Failed to get a response from the assistant.", file=sys.stderr)
                continue

            print()


def create_client(base_url: str, timeout_seconds: float) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=timeout_seconds)


def stream_message(client: httpx.Client, content: str) -> Iterator[str]:
    with client.stream("POST", "/chat", json={"content": content}) as response:
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")

        if not content_type.lower().startswith("text/event-stream"):
            raise ChatStreamError("Invalid stream content type")

        for event in iter_sse_events(response.iter_lines()):
            if event.event == "delta":
                delta_content = event.data.get("content")

                if not isinstance(delta_content, str):
                    raise ChatStreamError("Delta event content must be a string")

                yield delta_content
            elif event.event == "done":
                if event.data:
                    raise ChatStreamError("Done event data must be an empty object")
                return
            elif event.event == "error":
                error_code = event.data.get("code")
                error_message = event.data.get("message")

                if not isinstance(error_code, str) or not isinstance(
                    error_message, str
                ):
                    raise ChatStreamError(
                        "Error event code and message must be strings"
                    )

                raise ChatStreamError("Assistant stream returned an error")
            else:
                raise ChatStreamError(f"Unknown SSE event: {event.event}")

    raise ChatStreamError("Stream ended before done event")


def iter_sse_events(lines: Iterable[str]) -> Iterator[SSEEvent]:
    event_name: str | None = None
    data_lines: list[str] = []

    for line in lines:
        if line == "":
            if event_name is not None and data_lines:
                try:
                    parsed: object = json.loads("\n".join(data_lines))
                except json.JSONDecodeError as ex:
                    raise ChatStreamError("Invalid SSE data") from ex

                if not isinstance(parsed, dict):
                    raise ChatStreamError("SSE data must be a JSON object")

                data = cast(dict[str, object], parsed)
                yield SSEEvent(event=event_name, data=data)

            event_name = None
            data_lines = []
            continue

        field, separator, value = line.partition(":")

        if not separator:
            continue
        if value.startswith(" "):
            value = value[1:]

        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)

    if event_name is not None or data_lines:
        raise ChatStreamError("Incomplete SSE frame")


if __name__ == "__main__":
    main()
