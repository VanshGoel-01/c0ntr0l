# Normalized Event Contract

Every event must contain enough identity and ordering information for the dashboard, CLI, tests, and incident engine to interpret it consistently.

```json
{
  "event_id": "evt_123",
  "event_type": "llm.completed",
  "occurred_at": "2026-08-29T10:00:00Z",
  "trace_id": "tr_123",
  "span_id": "sp_456",
  "execution_id": "exec_123",
  "organization_id": "org_1",
  "project_id": "project_1",
  "user_id": "user_1",
  "application_id": "app_1",
  "agent_id": "agent_1",
  "provider": "mock",
  "model": "mock-stream-v1",
  "status": "completed",
  "usage": {
    "input_tokens": 120,
    "output_tokens": 35,
    "total_tokens": 155,
    "source": "provider_reported"
  },
  "calculated_cost_usd": 0,
  "latency_ms": 840
}
```

## Required Event Types

- `execution.created`
- `execution.status_changed`
- `llm.started`
- `llm.completed`
- `tool.started`
- `tool.completed`
- `usage.reconciled`
- `policy.warned`
- `policy.blocked`
- `incident.created`
- `handoff.created`

Usage sources are `provider_reported`, `locally_estimated`, or `configured`. New event fields must be additive during the hackathon unless all four workstreams approve the change.

