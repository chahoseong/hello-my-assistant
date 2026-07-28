import sys

import httpx

from .settings import Settings


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

            try:
                result = send_message(client, message)
            except httpx.HTTPError:
                print("Failed to get a response from the assistant.", file=sys.stderr)
                continue

            print(result)


def create_client(base_url: str, timeout_seconds: float) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=timeout_seconds)


def send_message(client: httpx.Client, content: str) -> str:
    response = client.post("/chat", json={"content": content})
    response.raise_for_status()
    return str(response.json()["content"])


if __name__ == "__main__":
    main()
