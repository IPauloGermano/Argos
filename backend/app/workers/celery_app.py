from __future__ import annotations
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery("hermes", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    beat_schedule={
        # Verifica a cada 5min se uma busca está devida (frequência configurável pelo usuário)
        "periodic-search-if-due": {"task": "hermes.periodic_search_if_due", "schedule": 300.0},
        "hourly-digest": {"task": "hermes.hourly_digest", "schedule": crontab(minute=0)},
        "daily-digest": {"task": "hermes.daily_digest", "schedule": crontab(hour=8, minute=0)},
    },
)

# Registra as tasks do worker (app.workers.tasks)
celery_app.autodiscover_tasks(["app.workers"])
