#!/bin/sh
set -e

echo "Running Database Initializations..."
# If Postgres is unreachable, this will fail and cause the container to restart, matching the desired wait-for-db behavior!
python src/database/make_table.py

echo "Starting FastAPI Server..."
exec fastapi run main.py --port 8000 --host 0.0.0.0
