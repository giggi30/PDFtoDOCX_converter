import uuid
from typing import Protocol

from redis import Redis
from rq import Queue

from app.core.config import get_settings


class JobDispatcher(Protocol):
    def enqueue(self, job_id: uuid.UUID) -> None: ...


class RqJobDispatcher:
    def __init__(self, redis_url: str, queue_name: str) -> None:
        self.queue = Queue(queue_name, connection=Redis.from_url(redis_url))

    def enqueue(self, job_id: uuid.UUID) -> None:
        self.queue.enqueue(
            "app.workers.tasks.process_conversion",
            str(job_id),
            job_timeout=60,
            result_ttl=0,
        )


def get_dispatcher() -> JobDispatcher:
    settings = get_settings()
    return RqJobDispatcher(settings.redis_url, settings.rq_queue_name)
