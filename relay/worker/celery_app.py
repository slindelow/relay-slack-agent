from celery import Celery

from relay.config import get_settings

settings = get_settings()

celery = Celery(
    "relay",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["relay.worker.tasks", "relay.sla.poller", "relay.worker.connector_tasks"],
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
    beat_schedule={
        "poll-sla-every-60s": {
            "task": "relay.poll_sla",
            "schedule": 60.0,
        },
        "sync-all-connectors-every-6h": {
            "task": "relay.sync_all_connectors",
            "schedule": 6 * 60 * 60,  # 6 hours in seconds
        },
    },
)

