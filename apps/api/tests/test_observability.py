import logfire
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from logfire.testing import CaptureLogfire
from pydantic_ai import Agent, models
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

import hello_my_assistant_api.app as app_module
import hello_my_assistant_api.observability as observability
from hello_my_assistant_api.app import create_app
from hello_my_assistant_api.assistant import Assistant

models.ALLOW_MODEL_REQUESTS = False


def test_initialize_observability_registers_automatic_instrumentation(monkeypatch):
    app = FastAPI()
    calls = []

    monkeypatch.setattr(
        logfire, "configure", lambda **kwargs: calls.append(("configure", kwargs))
    )
    monkeypatch.setattr(
        logfire,
        "instrument_fastapi",
        lambda instrumented_app, **kwargs: calls.append(
            ("instrument_fastapi", instrumented_app, kwargs)
        ),
    )
    monkeypatch.setattr(
        logfire,
        "instrument_pydantic_ai",
        lambda **kwargs: calls.append(("instrument_pydantic_ai", kwargs)),
    )

    observability.initialize_observability(app)

    assert calls[0] == ("configure", {"service_name": "hello-my-assistant-api"})
    assert calls[1][0:2] == ("instrument_fastapi", app)
    assert calls[2] == ("instrument_pydantic_ai", {"include_content": False})

    request_attributes_mapper = calls[1][2]["request_attributes_mapper"]

    assert request_attributes_mapper(None, {"values": {"content": "secret"}}) is None


def test_initialize_observability_logs_safe_warning_when_configuration_fails(
    monkeypatch, caplog
):
    app = FastAPI()
    sensitive_message = "secret-token-value"

    def raise_configuration_error(**kwargs):
        raise RuntimeError(sensitive_message)

    monkeypatch.setattr(logfire, "configure", raise_configuration_error)

    observability.initialize_observability(app)

    assert "Failed to initialize observability" in caplog.text
    assert sensitive_message not in caplog.text


def test_create_app_initializes_observability_once(monkeypatch, agent):
    initialized_apps = []
    assistant = Assistant(agent, timeout_seconds=30)

    monkeypatch.setattr(app_module, "initialize_observability", initialized_apps.append)

    app = create_app(assistant)

    assert initialized_apps == [app]


def test_automatic_instrumentation_links_trace_without_ai_content(
    monkeypatch, capfire: CaptureLogfire
):
    app = FastAPI()

    monkeypatch.setattr(
        Agent,
        "_instrument_default",
        Agent._instrument_default,
    )
    monkeypatch.setattr(logfire, "configure", lambda **kwargs: None)
    observability.initialize_observability(app)

    received_model_inputs = []

    async def respond(messages, _):
        received_model_inputs.append(str(messages))
        return ModelResponse(parts=[TextPart("SYNTHETIC_RESPONSE")])

    agent = Agent(
        FunctionModel(respond, model_name="synthetic-model"), name="synthetic-agent"
    )

    @app.post("/synthetic-chat")
    async def synthetic_chat(content: str):
        result = await agent.run(content)
        return {"output": result.output}

    with TestClient(app) as client:
        response = client.post(
            "/synthetic-chat", params={"content": "SYNTHETIC_PROMPT"}
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"output": "SYNTHETIC_RESPONSE"}

    assert len(received_model_inputs) == 1
    assert "SYNTHETIC_PROMPT" in received_model_inputs[0]

    spans = capfire.exporter.exported_spans_as_dict()

    http_spans = [
        span
        for span in spans
        if span["attributes"].get("http.route") == "/synthetic-chat"
    ]
    agent_spans = [
        span
        for span in spans
        if span["attributes"].get("gen_ai.operation.name") == "invoke_agent"
    ]
    model_spans = [
        span
        for span in spans
        if span["attributes"].get("gen_ai.operation.name") == "chat"
    ]

    assert len(http_spans) == 1
    assert len(agent_spans) == 1
    assert len(model_spans) == 1

    http_span = http_spans[0]
    agent_span = agent_spans[0]
    model_span = model_spans[0]

    assert (
        http_span["context"]["trace_id"]
        == agent_span["context"]["trace_id"]
        == model_span["context"]["trace_id"]
    )

    assert agent_span["parent"] is not None
    assert agent_span["parent"]["span_id"] == http_span["context"]["span_id"]

    assert model_span["parent"] is not None
    assert model_span["parent"]["span_id"] == agent_span["context"]["span_id"]

    ai_span_attributes = [
        agent_span["attributes"],
        model_span["attributes"],
    ]

    for attributes in ai_span_attributes:
        serialized_attributes = str(attributes)

        assert "SYNTHETIC_PROMPT" not in serialized_attributes
        assert "SYNTHETIC_RESPONSE" not in serialized_attributes
