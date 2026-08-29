# c0ntr0l

c0ntr0l is a runtime safety and observability layer for AI applications and agents. It sits between an application and model providers to trace executions, enforce hierarchical budgets, detect runaway loops, create incidents, and preserve context during approved provider failover.

## Hackathon MVP

- Compatible streaming AI gateway.
- Organization, user, project, application, agent, and execution identity.
- Usage, cost, latency, trace, and span collection.
- Hierarchical budgets with observe, warn, and enforce modes.
- Deterministic runaway-loop detection and intervention.
- Live dashboard and CLI.
- Structured, policy-approved provider handoff.

## Repository Layout

```text
apps/api/                 FastAPI gateway and control plane
apps/dashboard/           Next.js operational dashboard
apps/cli/                 Typer and Rich command-line client
packages/sdk-python/      Python guard SDK for tool and model calls
packages/schemas/         Shared request, event, policy, and handoff contracts
packages/providers/       Mock, Ollama, and optional cloud provider adapters
tools/mock-provider/      Deterministic provider used by demos and tests
tests/                     Unit, integration, end-to-end, and scenario tests
deploy/                    Docker Compose and environment setup
scripts/                   Seed, reset, validation, and demo scripts
migrations/                Database migrations
docs/contracts/            Shared API contracts
```

## Architecture

```text
AI application or agent
          |
          v
  c0ntr0l API gateway
          |
          +---- identity and execution tracing
          +---- budget and safety policies
          +---- loop detection and intervention
          +---- provider routing and failover
          |
          v
   AI model providers

PostgreSQL stores durable execution, usage, policy, and incident records.
Redis supports live state, atomic budget counters, and streaming coordination.
The dashboard and CLI expose the same control-plane data through the API.
```

## Dashboard

Start the dashboard after the API and local dependencies are running:

```powershell
cd apps/dashboard
pnpm install
pnpm dev
```

Open `http://localhost:3000`, select **Connect**, and enter the API URL and a
project API key created by the local seed command. The dashboard loads execution,
workspace, budget, incident, and trace data from authenticated API endpoints.
Provider cards probe Ollama and the deterministic mock service at runtime.

The project key is held only in browser memory. It is not written to local or
session storage and is discarded on reload or disconnect. Incident acknowledge
and resolve actions are project-scoped API updates persisted in PostgreSQL.

## Python Runtime Guard

The SDK places the policy decision directly before a tool or model call. If
c0ntr0l returns `block` or `cancel`, the handler is never invoked.

```python
from control_schemas import RuntimeExecutionRequest, RuntimePreflightRequest
from control_sdk import ControlRuntimeClient, ControlledExecution

async with ControlRuntimeClient(
    base_url="http://localhost:8000",
    api_key="<project-api-key>",
) as client:
    execution = await ControlledExecution.start(
        client,
        RuntimeExecutionRequest(task="Research watersheds", model="qwen2.5:0.5b"),
    )
    result = await execution.run_tool(
        name="search",
        arguments={"query": query},
        handler=lambda: search(query),
        progress=lambda output: bool(output["items"]),
        summary=lambda output: f"Found {len(output['items'])} sources",
    )
```

Model calls can reserve output capacity and enforce context and budget policy
before the provider handler runs:

```python
result = await execution.run_model(
    name="chat.completion",
    arguments={"model": "gemma3:1b"},
    handler=lambda: call_local_model(messages),
    progress=True,
    preflight=RuntimePreflightRequest(
        input_tokens=estimated_input_tokens,
        requested_output_tokens=512,
    ),
)
```

The server resolves active Ollama context metadata when available, otherwise it
uses provider-specific configuration. It projects the request across active
organization, project, user, application, and agent budgets. Enforce-mode
violations create a checkpoint and prevent the model handler from running.

Run the local no-progress loop demonstration without calling a paid model:

```powershell
$env:PYTHONPATH = "packages/sdk-python/src;packages/schemas/src"
$env:CONTROL_API_KEY = "<local-project-api-key>"
.\.venv\Scripts\python.exe scripts/demo_runtime_guard.py
```

Automatic recovery currently supports only configured local providers:

- `retry_modified` requires changed arguments and immediately executes the linked
  run through the source provider.
- `model_handoff` immediately executes the verified continuity packet through a
  different `mock` or `ollama` target.
- `manual_resume` prepares the linked execution without calling a provider.
- `stop` keeps the source execution stopped and preserves its checkpoint.

Completed recoveries record a provider span, provider attempt, usage, output
fingerprint, and source-to-resumed execution relationship. Raw model output is
returned to the calling application but is not stored in execution metadata.

Each request receives an execution identity and trace before it reaches a model.
Deterministic policies evaluate budgets and repeated operations, while provider
adapters normalize model responses and usage data. If a provider becomes
unavailable, an approved handoff can summarize the active context and continue
through another compatible provider without making the safety decision itself.
