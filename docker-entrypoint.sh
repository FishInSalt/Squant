#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting Squant application..."
exec uvicorn squant.main:app --host 0.0.0.0 --port 8000
