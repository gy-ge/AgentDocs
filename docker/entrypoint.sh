#!/bin/sh
set -eu

mkdir -p /app/data

uv run alembic upgrade head

exec "$@"