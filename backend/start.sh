#!/bin/bash

# Avvia il worker in background
# Usiamo python -m rq worker per assicurarci che il path sia corretto
python -m rq worker conversions --url $APP_REDIS_URL &

# Avvia le API (processo principale)
# Usiamo la variabile $PORT fornita da Render
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
