# syntax=docker/dockerfile:1.7
# Multi-stage build for the Memex processing worker.
#
# Stage 1 builds whisper.cpp from a pinned tag.
# Stage 2 fetches the whisper model file.
# Stage 3 assembles the runtime image with Python deps + the Claude Code CLI.
#
# The Claude Code CLI is installed system-wide via npm so its binary lives at
# /usr/local/bin/claude (outside the user's home). Auth state ($HOME/.claude/)
# is intentionally NOT created at build time — it is provided at runtime via
# a named volume mounted at /home/memex/.claude that is shared with the
# telegram_bot container, so a single `claude login` authenticates both.

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
ARG WHISPER_REPO=https://github.com/ggerganov/whisper.cpp.git
ARG WHISPER_COMMIT=v1.7.2
ARG WHISPER_MODEL=ggml-base.en.bin
ARG WHISPER_MODEL_URL=https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin

FROM ${PYTHON_IMAGE} AS whisper-builder
ARG WHISPER_REPO
ARG WHISPER_COMMIT
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch ${WHISPER_COMMIT} ${WHISPER_REPO} whisper.cpp \
    && cmake -S whisper.cpp -B whisper.cpp/build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build whisper.cpp/build -j --target whisper-cli \
    && cp whisper.cpp/build/bin/whisper-cli /usr/local/bin/whisper-cpp \
    && chmod +x /usr/local/bin/whisper-cpp


FROM ${PYTHON_IMAGE} AS model-fetcher
ARG WHISPER_MODEL
ARG WHISPER_MODEL_URL
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /models \
    && curl -fL --retry 3 --retry-delay 5 -o /models/${WHISPER_MODEL} ${WHISPER_MODEL_URL}


FROM ${PYTHON_IMAGE} AS runtime
ARG APP_UID=10001
ARG APP_GID=10001

# Runtime deps:
#   ffmpeg / libgomp1 — whisper.cpp + audio handling
#   nodejs npm        — Claude Code CLI (installed via npm install -g)
#   tini              — PID 1 to reap the claude / whisper / yt-dlp subprocesses
#   ca-certificates   — outbound HTTPS for trafilatura / yt-dlp / claude
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libgomp1 \
        nodejs \
        npm \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Install the Claude Code CLI globally. Node 18 (Bookworm default) is the
# minimum the package supports. The npm package is currently flagged as
# deprecated upstream in favour of a self-updating native installer, but it
# still ships the same binary; we use it because it puts /usr/local/bin/claude
# OUTSIDE the user's home, which lets us mount the auth state at
# /home/memex/.claude without clobbering the binary itself.
RUN npm install -g --no-audit --no-fund --omit=dev @anthropic-ai/claude-code \
    && claude --version \
    && rm -rf /root/.npm

COPY --from=whisper-builder /usr/local/bin/whisper-cpp /usr/local/bin/whisper-cpp
COPY --from=model-fetcher /models /models

RUN groupadd --system --gid ${APP_GID} memex \
    && useradd  --system --uid ${APP_UID} --gid ${APP_GID} \
                --home-dir /home/memex --create-home memex \
    && mkdir -p /home/memex/.claude \
    && chown -R memex:memex /home/memex /models

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY worker ./worker
COPY prompts ./prompts
COPY migrations ./migrations

USER memex
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/memex \
    MEMEX_WORKER_PROMPTS_DIR=/app/prompts \
    MEMEX_WORKER_MIGRATIONS_DIR=/app/migrations \
    MEMEX_WORKER_WHISPER_BIN=/usr/local/bin/whisper-cpp \
    MEMEX_WORKER_WHISPER_MODEL=/models/ggml-base.en.bin \
    MEMEX_WORKER_CLAUDE_BIN=/usr/local/bin/claude \
    MEMEX_WORKER_HEALTHCHECK_PATH=/tmp/memex-worker.healthy

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD test -f /tmp/memex-worker.healthy \
        && find /tmp/memex-worker.healthy -mmin -2 | grep -q . || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "worker.main"]
