from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base, apply_lightweight_migrations
from app.models.entities import *  # noqa: F401,F403 — registra modelos
from app.api.routes import profile, preferences, jobs, agent, notifications, users, telegram, favorites, reports, feedback


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicialização do Banco de Dados e Migrações leves
    apply_lightweight_migrations(engine)

    # Inicialização do Scheduler 24/7 (se habilitado)
    if settings.ENABLE_BUILTIN_SCHEDULER:
        try:
            from app.services.scheduler import start_scheduler
            start_scheduler(settings.DEFAULT_SEARCH_FREQUENCY_MINUTES)
        except Exception as e:
            print(f"[Hermes Scheduler Warning] {e}")

    yield

    # Shutdown limpo
    try:
        from app.services.scheduler import get_scheduler
        sched = get_scheduler()
        if sched.running:
            sched.shutdown(wait=False)
    except Exception:
        pass


app = FastAPI(
    title="Hermes Job Hunter",
    version="2.0.0",
    description="Agente Autônomo 24/7 de Busca e Monitoramento Contínuo de Vagas e Oportunidades Profissionais.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


@app.get("/health/live")
def liveness():
    return {"status": "ok", "service": "hermes-agent"}


@app.get("/health/ready")
@app.get("/health")
@app.get("/api/health")
def health(response: Response):
    db_status, redis_status = "ok", "ok"
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:
        db_status = "error"
    try:
        from app.core.database import get_redis_client
        get_redis_client().ping()
    except Exception:
        redis_status = "offline"

    is_healthy = (db_status == "ok")
    status_str = "ok" if is_healthy else "degraded"
    
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": status_str,
        "database": db_status,
        "redis": redis_status,
        "agent": "Hermes Autonomous Job Hunter 2.0"
    }


app.include_router(profile.router)
app.include_router(preferences.router)
app.include_router(jobs.router)
app.include_router(agent.router)
app.include_router(notifications.router)
app.include_router(users.router)
app.include_router(telegram.router)
app.include_router(favorites.router)
app.include_router(reports.router)
app.include_router(feedback.router)
