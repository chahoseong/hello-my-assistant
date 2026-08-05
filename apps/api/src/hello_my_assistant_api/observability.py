import logging

import logfire
from fastapi import FastAPI
from starlette.requests import Request
from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)


def initialize_observability(app: FastAPI) -> None:
    try:
        logfire.configure(service_name="hello-my-assistant-api")
        logfire.instrument_fastapi(
            app,
            request_attributes_mapper=_exclude_request_content,
        )
        logfire.instrument_pydantic_ai(include_content=False)
    except Exception:
        logger.warning("Failed to initialize observability")


def _exclude_request_content(
    _request: Request | WebSocket, _attributes: dict[str, object]
) -> None:
    return None
