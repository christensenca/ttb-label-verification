# syntax=docker/dockerfile:1.6

# ---- Stage 1: build the React/Vite SPA ----
FROM node:20-alpine AS frontend-build

WORKDIR /build

RUN corepack enable && corepack prepare pnpm@10.31.0 --activate

# Install deps with cache-friendly layering.
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --frozen-lockfile || pnpm install

# Build the SPA.
COPY frontend/ ./
RUN pnpm build

# ---- Stage 2: Python runtime ----
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:/root/.local/bin:$PATH"

# Install uv (Astral) — the project's package manager.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy application source.
COPY pipeline/ ./pipeline/
COPY app/ ./app/
COPY alembic.ini ./alembic.ini
# Fixture seed reads from /app/test_data at startup; ship it in the image.
COPY test_data/ ./test_data/

# Now install the project itself (so `app` and `pipeline` are importable).
RUN uv sync --frozen

# Copy the prebuilt SPA from stage 1.
COPY --from=frontend-build /build/dist ./frontend/dist

# Entrypoint runs migrations + seed, then uvicorn.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

CMD ["/usr/local/bin/docker-entrypoint.sh"]
