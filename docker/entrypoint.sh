#!/bin/sh
set -eu

mkdir -p /app/data

/app/.venv/bin/alembic upgrade head

exec "$@"