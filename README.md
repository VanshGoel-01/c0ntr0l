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

Each request receives an execution identity and trace before it reaches a model.
Deterministic policies evaluate budgets and repeated operations, while provider
adapters normalize model responses and usage data. If a provider becomes
unavailable, an approved handoff can summarize the active context and continue
through another compatible provider without making the safety decision itself.
