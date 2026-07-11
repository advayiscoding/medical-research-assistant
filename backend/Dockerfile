# Backend image. Multi-stage: a builder that resolves dependencies with uv, and
# a slim runtime. The embedding model is baked into the image at build time so
# the container never makes a first-request trip to Hugging Face (predictable
# cold starts, works air-gapped).

FROM python:3.12-slim AS builder

# uv for fast, reproducible installs. Copy the static binary from its image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install deps first (cached layer) using only the lock inputs, before app code.
COPY pyproject.toml ./
RUN uv venv /app/.venv && uv pip install --python /app/.venv/bin/python -r pyproject.toml

# --- Runtime ---
FROM python:3.12-slim AS runtime

# libpq/curl for asyncpg runtime + container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — never run the app as root.
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/appuser/.cache/huggingface

USER appuser

# Bake the default embedding model into the image BEFORE copying app code, so
# this layer depends only on the venv — editing application code no longer
# re-downloads the 90 MB model on every rebuild. (Skipped at runtime if a
# different model is configured; that one downloads on first use.)
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# App code last: the layer that changes most often invalidates the least.
COPY --chown=appuser:appuser . .

EXPOSE 8000

# Entrypoint applies migrations then starts the server, so a fresh database is
# schema-ready without a manual step.
ENTRYPOINT ["./docker-entrypoint.sh"]
