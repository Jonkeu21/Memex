# Phase 6 — Memex dashboard
#
# Multi-stage build: stage 1 builds the React + Vite bundle with Node 20;
# stage 2 is a Python 3.11-slim base that copies the built static assets in
# alongside the FastAPI backend. ARM64-compatible. Non-root runtime user.

# ─── Stage 1: build the frontend ────────────────────────────────────────────
FROM --platform=$BUILDPLATFORM node:20-bookworm-slim AS frontend
WORKDIR /build/frontend

# Copy lockfile + manifest first so npm cache reuses across rebuilds when only
# source files change.
COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --legacy-peer-deps --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ─── Stage 2: Python backend + static assets ────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Node + npm are needed only to install the Claude Code CLI. See
# worker/Dockerfile for the rationale: the npm-global install puts the binary
# at /usr/local/bin/claude (outside $HOME) so the auth-state volume mount at
# /home/memex/.claude can be shared with worker + telegram_bot without
# clobbering the binary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nodejs \
        npm \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g --no-audit --no-fund --omit=dev @anthropic-ai/claude-code \
    && claude --version \
    && rm -rf /root/.npm

# Same uid/gid as the other Memex services so vault bind-mounts have uniform
# ownership semantics.
RUN groupadd --system --gid 10001 memex \
    && useradd  --system --uid 10001 --gid memex --home-dir /app --shell /usr/sbin/nologin memex \
    && mkdir -p /app /home/memex/.claude /vault /srv/memex/data \
    && chown -R memex:memex /app /home/memex /vault /srv/memex/data

COPY pyproject.toml /tmp/pyproject.toml
COPY backend /tmp/backend
RUN cd /tmp \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && rm -rf /tmp/pyproject.toml /tmp/backend

WORKDIR /app
COPY backend /app/backend
COPY pyproject.toml /app/pyproject.toml
COPY --from=frontend /build/frontend/dist /app/frontend/dist

USER memex

ENV MEMEX_DASHBOARD_VAULT_DIR=/vault \
    MEMEX_DASHBOARD_DB_PATH=/srv/memex/data/memex.db \
    MEMEX_DASHBOARD_CLAUDE_BIN=/usr/local/bin/claude \
    MEMEX_DASHBOARD_FRONTEND_DIST_DIR=/app/frontend/dist \
    MEMEX_DASHBOARD_BIND_HOST=0.0.0.0 \
    MEMEX_DASHBOARD_BIND_PORT=8002 \
    MEMEX_LOG_LEVEL=INFO

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/healthz').status==200 else 1)"

CMD ["uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8002"]
