# Contributing

AgentLens is developed as a local-first monorepo. Before opening a PR, read the product context in `.design/PRD_v2.md` and keep changes scoped to the task.

Recommended checks:

```bash
cd backend
ruff check .
ruff format --check .
mypy .
pytest
```

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```
