from fastapi import FastAPI

from .assistant import Assistant
from .chat_http import create_chat_router
from .observability import initialize_observability


def create_app(assistant: Assistant) -> FastAPI:
    app = FastAPI()
    initialize_observability(app)
    app.include_router(create_chat_router(assistant))

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"message": "Hello World"}

    return app
