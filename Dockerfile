FROM node:20-alpine AS frontend-builder

WORKDIR /app
RUN corepack enable

COPY frontend/package.json frontend/pnpm-workspace.yaml frontend/pnpm-lock.yaml ./frontend/
COPY frontend/apps/web/package.json ./frontend/apps/web/package.json
COPY frontend/packages ./frontend/packages

WORKDIR /app/frontend
RUN pnpm install --frozen-lockfile

COPY frontend ./
RUN pnpm --filter web build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/pyproject.toml backend/README.md backend/alembic.ini ./backend/
COPY backend/app ./backend/app
COPY backend/alembic ./backend/alembic

WORKDIR /app/backend
RUN pip install --no-cache-dir -e .

WORKDIR /app
COPY backend ./backend
COPY --from=frontend-builder /app/frontend/apps/web/dist ./backend/app/static

ENV AGENT_LENS_HOST=0.0.0.0
ENV AGENT_LENS_PORT=8000
ENV AGENT_LENS_DATA_DIR=/data
ENV AGENTLENS_HOST=0.0.0.0
ENV AGENTLENS_PORT=8000
ENV AGENTLENS_DATA_DIR=/data

VOLUME ["/data"]
EXPOSE 8000

WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
