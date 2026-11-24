# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md ./
COPY sre_triage_agent ./sre_triage_agent
COPY server ./server

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install ".[cloud]"


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080 \
    HOST=0.0.0.0 \
    SRE_MEMORY_DB_PATH=/app/data/incident_memory.db

RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --shell /usr/sbin/nologin --create-home appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup sre_triage_agent ./sre_triage_agent
COPY --chown=appuser:appgroup server ./server
COPY --chown=appuser:appgroup eval ./eval

RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')" || exit 1

CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8080}"]
