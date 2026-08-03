import importlib
import sys

import logfire
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from logfire.testing import CaptureLogfire
from pydantic_ai import Agent, models
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

import hello_my_assistant_api
import hello_my_assistant_api.observability as observability

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
        lambda instrumented_app: calls.append(("instrument_fastapi", instrumented_app)),
    )
    monkeypatch.setattr(
        logfire,
        "instrument_pydantic_ai",
        lambda **kwargs: calls.append(("instrument_pydantic_ai", kwargs)),
    )

    observability.initialize_observability(app)

    assert calls == [
        ("configure", {"service_name": "hello-my-assistant-api"}),
        ("instrument_fastapi", app),
        ("instrument_pydantic_ai", {"include_content": False}),
    ]


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


def test_api_startup_initializes_observability_once(monkeypatch):
    module_name = "hello_my_assistant_api.main"
    original_main_module = sys.modules[module_name]
    initialized_apps = []

    with monkeypatch.context() as context:
        context.setattr(
            observability, "initialize_observability", initialized_apps.append
        )
        context.delitem(sys.modules, module_name)
        context.delattr(hello_my_assistant_api, "main")

        main_module = importlib.import_module(module_name)

        assert initialized_apps == [main_module.app]

    assert sys.modules[module_name] is original_main_module
    assert hello_my_assistant_api.main is original_main_module


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
