from .agent import create_agent
from .app import create_app
from .assistant import Assistant
from .settings import Settings

settings = Settings()
agent = create_agent(settings)
assistant = Assistant(agent, timeout_seconds=settings.chat_timeout_seconds)
app = create_app(assistant)
