# Team Contribution Workflow

## Ownership

| Workstream | Branch | Paths |
|---|---|---|
| Core gateway | `feat/core-gateway` | `apps/api/`, `packages/schemas/`, `migrations/` |
| Dashboard | `feat/dashboard` | `apps/dashboard/` |
| Tests and scenarios | `feat/test-scenarios` | `tests/`, `tools/mock-provider/`, `scripts/` |
| Infrastructure and providers | `feat/infra-providers` | `deploy/`, `.github/`, `apps/cli/`, `packages/providers/` |

## Handoff Process

1. Receive the module as a zip or patch, not pasted chat text.
2. Read the included `HANDOFF.md` and `FILES_CHANGED.md`.
3. Place the files in a clean clone on the assigned branch.
4. Inspect `git diff` before staging anything.
5. Follow `SETUP.md` and complete every item in `VERIFY.md`.
6. Correct discovered problems and record the evidence.
7. Commit only after the owner can explain the module.
8. Push the branch and notify the integration owner.

## Commit Format

Use Conventional Commit messages:

```text
feat(ui): add live execution monitoring
feat(policy): reserve project budgets atomically
test(loop): cover alternating tool-call detection
fix(provider): classify quota errors separately from outages
docs(demo): document offline review procedure
```

## Integration Gate

Before merging a workstream into `integration`:

- The module starts from documented commands.
- Required tests pass.
- No secret or local environment file is staged.
- API/event contract changes are documented.
- The owner can demonstrate one normal and one failure path.

