from celery import Celery

from relay.config import get_settings

settings = get_settings()

celery = Celery(
    "relay",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["relay.worker.tasks"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=30,
    task_max_retries=3,
)

