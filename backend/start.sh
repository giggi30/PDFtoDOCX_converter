#!/bin/bash

# Esegui le migrazioni del database
echo "Running database migrations..."
alembic upgrade head

# Avvia il worker in background
echo "Starting RQ worker..."
# Usiamo il comando 'rq' direttamente invece di 'python -m rq'
rq worker conversions --url $APP_REDIS_URL &

# Avvia le API
echo "Starting FastAPI app..."
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
