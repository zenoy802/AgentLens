# AgentLens

AgentLens is a SQL-query-based LLM trajectory visualization, labeling, and analysis tool for agent developers. It connects to existing MySQL databases in read-only mode, queries arbitrary trajectory schemas, and renders results as row tables, single trajectory views, and comparison views.

## Repository Layout

```text
AgentLens/
├── backend/                  # FastAPI API service and local SQLite metadata store
├── frontend/                 # pnpm workspace for the React web app and viewer packages
│   ├── apps/web/             # Vite + React + TypeScript application
│   └── packages/viewers/     # Placeholder renderer packages for later phases
├── Dockerfile                # Production image build
├── docker-compose.yml        # Single-service production compose entry
└── README.md
```

## Prerequisites

- Python 3.11 or newer for the FastAPI backend. The current local workflow uses `venv` + `pip`; backend environment management is planned to move to `uv` in a later phase.
- Node.js 20 or newer and pnpm 8 or newer for the React frontend workspace.

## Local Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify the API:

```bash
curl http://localhost:8000/api/v1/health
```

### Frontend

Use pnpm 8 or newer.

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api` requests to `http://localhost:8000`.

Generate OpenAPI types after the backend is running:

```bash
cd frontend
pnpm gen:api
```

Run checks:

```bash
cd frontend
pnpm --filter web typecheck
pnpm build
```

### One-shot Validation

From the repository root, this starts the backend in the background, waits for it to be ready, runs frontend checks, and stops the backend when the shell exits:

```bash
(cd backend && AGENTLENS_DATA_DIR=/tmp/agentlens-dev python -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT

until curl -fs http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; do
  sleep 0.5
done

cd frontend
pnpm install
pnpm gen:api
pnpm --filter web typecheck
pnpm lint
pnpm build
pnpm dev
```

## Docker

Build and start the production container:

```bash
docker compose up --build
```

The app listens on `http://localhost:8000`. The compose file mounts `~/.agentlens` into the container for AgentLens metadata, logs, and encrypted local secrets.
