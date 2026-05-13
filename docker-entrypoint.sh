#!/bin/sh
set -e

# Apply schema migrations.
alembic upgrade head

# Idempotent fixture seed (no-op if fixtures already exist).
python -m app.db.seed

# Start the API.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
