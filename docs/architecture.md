# Architecture Baseline

```text
AI application / scenario runner
              |
              v
        FastAPI gateway
       /       |       \
 identity   policies   providers
       \       |       /
        execution trace
          |          |
      PostgreSQL    Redis
          |          |
       dashboard    CLI
```

## Request Path

1. Authenticate the project and resolve organization, user, application, and agent identity.
2. Create an execution and root span.
3. Estimate usage and atomically reserve applicable budgets.
4. Evaluate deterministic policies.
5. Route to an approved provider and stream the response.
6. Emit normalized usage and span events.
7. Reconcile reservations with final usage.
8. Create an incident when a policy intervenes.

## Review Scenarios

- Normal request completes and reconciles usage.
- Project budget blocks a request while another project continues.
- Repeated tool calls trigger an incident and stop the next operation.
- Provider timeout opens a circuit and produces an approved handoff.

