FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
RUN corepack enable

COPY frontend/package.json frontend/pnpm-workspace.yaml frontend/pnpm-lock.yaml ./
COPY frontend/apps/web/package.json ./apps/web/package.json
COPY frontend/packages/viewers/markdown-renderer/package.json ./packages/viewers/markdown-renderer/package.json
COPY frontend/packages/viewers/json-renderer/package.json ./packages/viewers/json-renderer/package.json
COPY frontend/packages/viewers/code-renderer/package.json ./packages/viewers/code-renderer/package.json
COPY frontend/packages/viewers/trajectory-viewer/package.json ./packages/viewers/trajectory-viewer/package.json
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend

COPY --from=frontend-builder /app/frontend/apps/web/dist ./static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
