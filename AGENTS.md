# Codex Repository Instructions

## Product

c0ntr0l is a provider-agnostic AI runtime gateway. The hackathon demonstration must prove normal execution tracing, budget enforcement, deterministic loop intervention, incident evidence, and context-aware provider failover.

## Engineering Priorities

1. Keep `main` demoable.
2. Preserve the contracts in `docs/contracts/` unless an integration change is explicitly approved.
3. Implement safety decisions deterministically. An LLM may summarize a handoff, but it must not enforce budgets or decide whether a loop is unsafe.
4. Label usage as provider-reported, locally estimated, or configured.
5. Never store secrets, authorization headers, or raw tool arguments by default.
6. Every intervention must retain its policy, triggering span, evidence, and final execution state.
7. Prefer a complete vertical MVP over additional infrastructure or speculative features.

## Ownership Boundaries

- Core: `apps/api/`, `packages/schemas/`, `migrations/`.
- UI: `apps/dashboard/`.
- QA: `tests/`, `tools/mock-provider/`, `scripts/`.
- Infra/providers: `deploy/`, `.github/`, `apps/cli/`, `packages/providers/`.

Do not change another workstream's files without documenting the reason in the handoff and commit message.

## Verification

Every generated module must include setup instructions, tests, expected output, limitations, and a completed verification checklist before it is merged into `integration`.

