"""Celery 应用：异步任务队列。

- Broker / Result Backend: Redis
- Task 与 API 通过 `send_task` 解耦，便于跨进程调度。
"""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "enterprise_rag",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.document_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)