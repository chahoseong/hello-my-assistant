# Hello My Assistant API

## Runtime observability E2E

The regular pytest suite verifies telemetry deterministically in memory. The
runtime E2E command is separate because it starts real Uvicorn processes, sends
telemetry to Logfire, and queries the resulting traces from Logfire.

Set a Logfire read token only in the command environment, then run:

```shell
uv run python -m observability_e2e
```

The default command runs three scenarios and queries their traces together:

- `success` calls the configured model and expects a completed SSE stream.
- `model-error` uses a loopback fault model that returns HTTP 503.
- `disconnect-after-delta` closes the client stream after the first delta.

Run one scenario by passing its name, for example:

```shell
uv run python -m observability_e2e model-error
```

The runner verifies the HTTP → `chat.stream` → Agent → Model hierarchy,
scenario-specific outcome and error attributes, delta timing, and absence of a
synthetic private marker from core trace fields. The fault model lives outside
the production package and listens only on a dynamically selected loopback
port.

This is an explicit external check: `success` can incur model cost, every
scenario writes synthetic telemetry to the configured Logfire project, and the
Query API can be temporarily rate-limited. Do not put read tokens in source
control or command output. A failure to find a trace means the runtime export,
ingest, or query path needs investigation; it does not by itself prove that the
chat behavior failed.
