from celery import Celery

from core.config import settings

celery_app = Celery(
    "research_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.tasks", "workers.agent_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)