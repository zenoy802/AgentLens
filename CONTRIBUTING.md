# Contributing

AgentLens is a local-first monorepo for SQL-first trajectory visualization, labeling, and Agent Bridge workflows. Before opening a PR, read the product context in `.design/PRD_v2.md` and keep changes scoped.

## Development Environment

Requirements:

- Python 3.11+
- Node 20+
- pnpm via Corepack
- Docker, if you are testing packaging
- MySQL, only for integration tests that explicitly require it

## Backend Install

```bash
pip install -e "backend[dev]"
```

Run the backend:

```bash
cd backend
AGENTLENS_DATA_DIR=/tmp/agentlens-dev python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Frontend Install

```bash
cd frontend
pnpm install
pnpm dev
```

The Vite dev server proxies API calls to the backend.

## CLI/MCP Development Install

```bash
pip install -e "backend[dev]"
pip install -e packages/agentlens-client
pip install -e cli
pip install -e mcp_server
```

Verify commands:

```bash
agentlens --help
agentlens-mcp --help
```

## Code Style

Backend:

```bash
cd backend
ruff check .
ruff format --check .
mypy app
```

Frontend:

```bash
cd frontend
pnpm typecheck
pnpm lint
```

Avoid unrelated formatting churn. Keep generated API types in sync when backend OpenAPI changes.

## Tests

```bash
cd backend && ruff check . && mypy app && pytest
cd frontend && pnpm typecheck && pnpm lint && pnpm build
cd cli && pytest
cd mcp_server && pytest
```

Do not require a real MySQL server for default CI tests unless the test is explicitly marked and provisioned.

## Conventional Commits

Use Conventional Commits:

- `feat:`
- `fix:`
- `chore:`
- `refactor:`
- `test:`
- `docs:`

Examples:

```text
feat: add annotation websocket updates
fix: keep row identity stable across reruns
docs: add Agent Bridge guide
```

## PR Process

1. Keep the PR scoped to one task.
2. Add or update tests for behavioral changes.
3. Update docs for user-visible changes.
4. Run the relevant backend, frontend, CLI, and MCP checks.
5. Include screenshots for UI changes.
6. Fill in the PR template test plan.
