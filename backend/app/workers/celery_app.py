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

from celery.signals import worker_ready


@worker_ready.connect
def on_worker_ready(**kwargs):
    try:
        from app.core.database import apply_lightweight_migrations
        apply_lightweight_migrations()
    except Exception as e:
        print(f"[Celery Worker DB Init Warning] {e}")
