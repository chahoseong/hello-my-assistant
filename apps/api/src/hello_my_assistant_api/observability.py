import logging

import logfire
from fastapi import FastAPI

logger = logging.getLogger(__name__)


def initialize_observability(app: FastAPI) -> None:
    try:
        logfire.configure(service_name="hello-my-assistant-api")
        logfire.instrument_fastapi(app)
        logfire.instrument_pydantic_ai(include_content=False)
    except Exception:
        logger.warning("Failed to initialize observability")
