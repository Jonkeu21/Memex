FROM --platform=$BUILDPLATFORM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir --upgrade pip build \
    && pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 memex \
    && useradd  --system --uid 10001 --gid memex --home-dir /app --shell /usr/sbin/nologin memex \
    && mkdir -p /data/inbox \
    && chown -R memex:memex /data

COPY --from=builder /install /usr/local
COPY app /app/app

WORKDIR /app
USER memex

ENV CAPTURE_DB_PATH=/data/queue.db \
    CAPTURE_INBOX_DIR=/data/inbox \
    CAPTURE_BIND_HOST=0.0.0.0 \
    CAPTURE_BIND_PORT=8001 \
    LOG_LEVEL=INFO

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/healthz').status==200 else 1)"

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
