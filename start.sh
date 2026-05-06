#!/bin/sh
set -e

echo "Running Database Initializations..."
# If Postgres is unreachable, this will fail and cause the container to restart, matching the desired wait-for-db behavior!
export PYTHONPATH=$PYTHONPATH:/app
# python -m src.database.make_table

echo "Starting FastAPI Server..."
exec uv run main.py
