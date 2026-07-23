# syntax=docker/dockerfile:1
# =============================================================================
# Multi-stage build for the lean API image.
#   Stage 1 (builder): install runtime deps into a venv.
#   Stage 2 (runtime): copy venv + app; run as non-root.
# The ML stack (torch/transformers) is intentionally NOT installed here — the
# API doesn't compute embeddings. The pipeline image adds requirements-ml.txt.
# =============================================================================

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    JOBAGENT_ENV=production

# Non-root user.
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY data ./data
COPY pyproject.toml requirements.txt ./

RUN mkdir -p logs exports && chown -R app:app /app
USER app

# Render (and other PaaS) inject $PORT and route to it. Default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Container-level liveness check (honours $PORT).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys,os; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen(f'http://localhost:{p}/health').status==200 else 1)"

# `exec` so uvicorn is PID 1 and receives SIGTERM for graceful shutdown; the
# shell only expands ${PORT} first. Render sets PORT; locally it defaults to 8000.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
