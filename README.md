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
docs/contracts/            API and event contracts shared by every workstream
handoffs/templates/        Files used when transferring a Codex-generated module
```

## Branches

- `main`: review-ready and demoable checkpoints only.
- `integration`: combined team work after verification.
- `feat/core-gateway`: gateway, schemas, policies, and backend integration.
- `feat/dashboard`: UI design and frontend implementation.
- `feat/test-scenarios`: mock failures, fixtures, and automated tests.
- `feat/infra-providers`: Docker, CI, CLI, provider adapters, and failover support.

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) before committing.
