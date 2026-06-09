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

FROM python:3.11-slim AS python-builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY cli ./cli
COPY packages ./packages
COPY --from=frontend-builder /app/frontend/apps/web/dist ./backend/app/static

RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AGENTLENS_HOST=0.0.0.0
ENV AGENTLENS_PORT=8000
ENV AGENTLENS_DATA_DIR=/data

WORKDIR /app

COPY --from=python-builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels agentlens==0.1.0 \
    && rm -rf /wheels \
    && useradd -m -u 1000 agentlens \
    && mkdir -p /data \
    && chown -R agentlens:agentlens /data

USER agentlens

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health').read()"

CMD ["agentlens", "run"]
