from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

engine_kwargs = {"future": True}
if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis_client():
    import redis

    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def apply_lightweight_migrations(target_engine=None):
    """
    Garante inicialização das tabelas e migrações leves de schema
    para bancos SQLite e PostgreSQL sem quebrar instâncias existentes.
    NOTA: caminho legado pré-Alembic. Novas instalações devem usar
    `alembic upgrade head`. Mantido para compatibilidade com SQLite local
    e testes. Não executar concorrentemente em múltiplos processos em prod:
    o backend executa no lifespan; o worker NÃO deve executar DDL.
    """
    if target_engine is None:
        target_engine = engine
    try:
        from app.models.entities import Base  # Registra todas as entidades
        Base.metadata.create_all(bind=target_engine)

        def _ensure_column(table: str, column: str, ddl_sqlite: str, ddl_pg: str):
            if target_engine.dialect.name == "sqlite":
                with target_engine.connect() as conn:
                    res = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
                    cols = [r[1] for r in res]
                    if cols and column not in cols:
                        conn.exec_driver_sql(ddl_sqlite)
                        conn.commit()
            elif target_engine.dialect.name == "postgresql":
                with target_engine.connect() as conn:
                    conn.exec_driver_sql(ddl_pg)
                    conn.commit()

        _ensure_column(
            "search_preferences", "excluded_jobs",
            "ALTER TABLE search_preferences ADD COLUMN excluded_jobs JSON DEFAULT '[]'",
            "ALTER TABLE search_preferences ADD COLUMN IF NOT EXISTS excluded_jobs JSONB NOT NULL DEFAULT '[]'::jsonb",
        )
        _ensure_column(
            "job_matches", "recency_score",
            "ALTER TABLE job_matches ADD COLUMN recency_score INTEGER DEFAULT 0",
            "ALTER TABLE job_matches ADD COLUMN IF NOT EXISTS recency_score INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            "notifications", "event_type",
            "ALTER TABLE notifications ADD COLUMN event_type VARCHAR(32) DEFAULT 'new_match'",
            "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS event_type VARCHAR(32) NOT NULL DEFAULT 'new_match'",
        )
        _ensure_column(
            "notifications", "attempts",
            "ALTER TABLE notifications ADD COLUMN attempts INTEGER DEFAULT 0",
            "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            "notifications", "next_attempt_at",
            "ALTER TABLE notifications ADD COLUMN next_attempt_at TIMESTAMP",
            "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ",
        )
        _ensure_column(
            "notifications", "last_error",
            "ALTER TABLE notifications ADD COLUMN last_error TEXT DEFAULT ''",
            "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS last_error TEXT NOT NULL DEFAULT ''",
        )
        _ensure_column(
            "notifications", "created_at",
            "ALTER TABLE notifications ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        )
        _ensure_column(
            "search_runs", "lock_skipped",
            "ALTER TABLE search_runs ADD COLUMN lock_skipped INTEGER DEFAULT 0",
            "ALTER TABLE search_runs ADD COLUMN IF NOT EXISTS lock_skipped INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            "search_runs", "provider_zero_results",
            "ALTER TABLE search_runs ADD COLUMN provider_zero_results JSON DEFAULT '[]'",
            "ALTER TABLE search_runs ADD COLUMN IF NOT EXISTS provider_zero_results JSONB NOT NULL DEFAULT '[]'::jsonb",
        )
        _ensure_column(
            "search_runs", "provider_failures",
            "ALTER TABLE search_runs ADD COLUMN provider_failures JSON DEFAULT '[]'",
            "ALTER TABLE search_runs ADD COLUMN IF NOT EXISTS provider_failures JSONB NOT NULL DEFAULT '[]'::jsonb",
        )
    except Exception as e:
        print(f"[Hermes DB Migration Warning] {e}")

