# syntax=docker/dockerfile:1.7
# Memex Telegram bot — single-process long-polling bot.
# The `claude` binary itself is mounted from the host at runtime; we do not
# bundle it in the image (Claude Max session credentials live on the host).

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

FROM ${PYTHON_IMAGE} AS runtime
ARG APP_UID=10001
ARG APP_GID=10001

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid ${APP_GID} memex \
    && useradd  --system --uid ${APP_UID} --gid ${APP_GID} \
                --home-dir /home/memex --create-home memex

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY bot ./bot
COPY prompts ./prompts

USER memex
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MEMEX_TELEGRAM_VAULT_DIR=/vault \
    MEMEX_TELEGRAM_DB_PATH=/srv/memex/data/memex.db \
    MEMEX_TELEGRAM_CLAUDE_BIN=claude

# No HTTP port to expose — long polling only.
# No HEALTHCHECK either: the bot's liveness is a successful Telegram getUpdates
# loop, which we cannot probe without a token. Compose's restart policy is
# the recovery mechanism.

CMD ["python", "-m", "bot.main"]
