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
    # Migrações: Alembic é o caminho oficial em PostgreSQL.
    # SQLite/dev/testes usam lightweight (create_all + ensures).
    # Nunca executa DDL concorrente: apenas o backend no lifespan.
    try:
        if settings.DATABASE_URL.startswith("sqlite"):
            apply_lightweight_migrations(engine)
        else:
            try:
                import os as _os
                from alembic.config import Config as _Ac
                from alembic import command as _acmd
                _here = _os.path.dirname(_os.path.abspath(__file__))  # backend/app
                _candidates = [
                    _os.path.join(_here, "..", "alembic.ini"),   # backend/alembic.ini (repo)
                    _os.path.join("/code", "alembic.ini"),        # /code/alembic.ini (docker)
                    _os.path.join(_os.getcwd(), "backend", "alembic.ini"),
                    _os.path.join(_os.getcwd(), "alembic.ini"),
                ]
                _ini = next((p for p in _candidates if _os.path.exists(p)), None)
                if _ini is None:
                    raise RuntimeError("alembic.ini não encontrado na imagem")
                _cfg = _Ac(_ini)
                _cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
                # script_location relativo ao repo quebra no container (/code):
                # resolve absoluto a partir do alembic.ini encontrado.
                _base = _os.path.dirname(_os.path.abspath(_ini))
                _script = _cfg.get_main_option("script_location") or "alembic"
                if not _os.path.isabs(_script):
                    _abs = _os.path.normpath(_os.path.join(_base, _script))
                    if not _os.path.isdir(_abs) and _os.path.isdir(_os.path.join(_base, "alembic")):
                        _abs = _os.path.join(_base, "alembic")
                    _cfg.set_main_option("script_location", _abs)
                _acmd.upgrade(_cfg, "head")
                print("[Hermes Alembic] upgrade head ok")
            except Exception as _ae:
                _msg = str(_ae)
                # Baseline: DB criado via create_all (sem alembic_version).
                # Convergência sem perda: lightweight (colunas) -> stamp base
                # -> upgrade head (0002/0003 idempotentes).
                if "DuplicateTable" in type(_ae).__name__ or "already exists" in _msg or "DuplicateTable" in _msg:
                    try:
                        print(f"[Hermes Alembic] baseline sem versionamento detectado; convergindo: {_msg[:120]}")
                        apply_lightweight_migrations(engine)
                        _acmd.stamp(_cfg, "baeffd94ede2")
                        _acmd.upgrade(_cfg, "head")
                        print("[Hermes Alembic] baseline convergido para head")
                    except Exception as _be:
                        print(f"[Hermes Alembic Warning] convergência falhou ({_be}); fallback lightweight")
                        apply_lightweight_migrations(engine)
                else:
                    print(f"[Hermes Alembic Warning] {_msg[:300]}; fallback lightweight")
                    apply_lightweight_migrations(engine)
    except Exception as _e:
        print(f"[Hermes DB Init Warning] {_e}")

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
