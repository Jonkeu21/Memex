# syntax=docker/dockerfile:1.7
# Memex Telegram bot — single-process long-polling bot.
#
# Phase 5 change: the Claude Code CLI is now installed inside this image
# rather than mounted from the host. Auth state ($HOME/.claude/) is provided
# at runtime via a named volume shared with the worker, so a single
# `claude login` authenticates both services.

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

FROM ${PYTHON_IMAGE} AS runtime
ARG APP_UID=10001
ARG APP_GID=10001

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        nodejs \
        npm \
        procps \
        tini \
    && rm -rf /var/lib/apt/lists/*

# See worker/Dockerfile for the rationale behind the npm-global install path.
RUN npm install -g --no-audit --no-fund --omit=dev @anthropic-ai/claude-code \
    && claude --version \
    && rm -rf /root/.npm

RUN groupadd --system --gid ${APP_GID} memex \
    && useradd  --system --uid ${APP_UID} --gid ${APP_GID} \
                --home-dir /home/memex --create-home memex \
    && mkdir -p /home/memex/.claude \
    && chown -R memex:memex /home/memex

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY bot ./bot
COPY prompts ./prompts

USER memex
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/memex \
    MEMEX_TELEGRAM_VAULT_DIR=/vault \
    MEMEX_TELEGRAM_DB_PATH=/srv/memex/data/memex.db \
    MEMEX_TELEGRAM_CLAUDE_BIN=/usr/local/bin/claude

# Process-presence healthcheck: the bot has no HTTP surface and Phase 4's
# implementation does not write a heartbeat file, so we probe for the python
# entrypoint process. Compose's restart policy handles the recovery if it
# disappears. The bot's actual liveness — successful Telegram getUpdates
# polls — is observable in `docker compose logs telegram_bot`.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD pgrep -f "python -m bot.main" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "bot.main"]
