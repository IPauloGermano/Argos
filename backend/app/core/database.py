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
    """
    if target_engine is None:
        target_engine = engine
    try:
        from app.models.entities import Base  # Registra todas as entidades
        Base.metadata.create_all(bind=target_engine)

        if target_engine.dialect.name == "sqlite":
            with target_engine.connect() as conn:
                res = conn.exec_driver_sql("PRAGMA table_info(search_preferences)").fetchall()
                cols = [r[1] for r in res]
                if cols and "excluded_jobs" not in cols:
                    conn.exec_driver_sql("ALTER TABLE search_preferences ADD COLUMN excluded_jobs JSON DEFAULT '[]'")
                    conn.commit()
        elif target_engine.dialect.name == "postgresql":
            with target_engine.connect() as conn:
                conn.exec_driver_sql(
                    "ALTER TABLE search_preferences ADD COLUMN IF NOT EXISTS excluded_jobs JSONB NOT NULL DEFAULT '[]'::jsonb"
                )
                conn.commit()
    except Exception as e:
        print(f"[Hermes DB Migration Warning] {e}")

