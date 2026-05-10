# syntax=docker/dockerfile:1.7
# Multi-stage build for the Memex processing worker.
# Stage 1 builds whisper.cpp from a pinned commit; stage 2 assembles the runtime.

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
ARG WHISPER_REPO=https://github.com/ggerganov/whisper.cpp.git
ARG WHISPER_COMMIT=v1.7.2

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


FROM ${PYTHON_IMAGE} AS runtime
ARG APP_UID=10001
ARG APP_GID=10001

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=whisper-builder /usr/local/bin/whisper-cpp /usr/local/bin/whisper-cpp

RUN groupadd --system --gid ${APP_GID} memex \
    && useradd  --system --uid ${APP_UID} --gid ${APP_GID} \
                --home-dir /home/memex --create-home memex

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY worker ./worker
COPY prompts ./prompts
COPY migrations ./migrations

USER memex
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MEMEX_WORKER_PROMPTS_DIR=/app/prompts \
    MEMEX_WORKER_MIGRATIONS_DIR=/app/migrations \
    MEMEX_WORKER_WHISPER_BIN=/usr/local/bin/whisper-cpp \
    MEMEX_WORKER_HEALTHCHECK_PATH=/tmp/memex-worker.healthy

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD test -f /tmp/memex-worker.healthy \
        && find /tmp/memex-worker.healthy -mmin -2 | grep -q . || exit 1

CMD ["python", "-m", "worker.main"]
