web: uv run uvicorn relay.api.main:api --host 0.0.0.0 --port $PORT
worker: uv run celery -A relay.worker.celery_app.celery worker --concurrency=2 --beat --loglevel=info
beat: uv run celery -A relay.worker.celery_app beat --loglevel=info
