from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, delete, or_, and_

from app.models.entities import (
    Job,
    JobMatch,
    JobChangelog,
    Notification,
    JobFeedback,
    UserFavorite,
    SearchPreferences,
)
from app.core.logging import log_event


def purge_expired_jobs(db: Session, max_age_days: Optional[int] = 60) -> int:
    """
    Remove automaticamente vagas expiradas que ultrapassaram 'max_age_days'.

    Salvaguardas estritas:
    1. Vagas salvas/favoritas (UserFavorite) NUNCA são apagadas.
    2. Exclusão em cascata controlada e segura para todas as tabelas dependentes
       (JobMatch, JobChangelog, Notification, JobFeedback).
    3. Proteção contra valores inválidos de max_age_days (mínimo 1 dia).
    4. Atualização da lista de 'excluded_jobs' em SearchPreferences para evitar
       acúmulo de IDs de vagas deletadas.
    5. Transação atômica com rollback automático em caso de falha.
    """
    if max_age_days is None or max_age_days < 1:
        return 0

    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=max_age_days)

    try:
        # 1. IDs de vagas favoritas protegidas pelo usuário
        favorited_ids = set(db.scalars(select(UserFavorite.job_id)).all())

        # 2. Critério de expiração:
        # Se published_at existir, compara com published_at < cutoff.
        # Se published_at for nulo, compara com discovered_at < cutoff.
        expired_filter = or_(
            and_(Job.published_at.is_not(None), Job.published_at < cutoff),
            and_(Job.published_at.is_(None), Job.discovered_at.is_not(None), Job.discovered_at < cutoff),
        )

        q = select(Job.id).where(expired_filter)
        if favorited_ids:
            q = q.where(Job.id.not_in(list(favorited_ids)))

        expired_ids = list(db.scalars(q).all())
        if not expired_ids:
            return 0

        # 3. Remoção em lote segura respeitando chaves estrangeiras
        batch_size = 500
        total_purged = 0

        for i in range(0, len(expired_ids), batch_size):
            batch = expired_ids[i:i + batch_size]
            db.execute(delete(JobMatch).where(JobMatch.job_id.in_(batch)))
            db.execute(delete(JobChangelog).where(JobChangelog.job_id.in_(batch)))
            db.execute(delete(Notification).where(Notification.job_id.in_(batch)))
            db.execute(delete(JobFeedback).where(JobFeedback.job_id.in_(batch)))
            db.execute(delete(Job).where(Job.id.in_(batch)))
            total_purged += len(batch)

        # 4. Limpeza de IDs órfãos em excluded_jobs
        prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
        if prefs and prefs.excluded_jobs:
            expired_set = set(expired_ids)
            cleaned = [jid for jid in prefs.excluded_jobs if jid not in expired_set]
            if len(cleaned) != len(prefs.excluded_jobs):
                prefs.excluded_jobs = cleaned

        db.commit()
        log_event("PURGED_EXPIRED_JOBS", count=total_purged, max_age_days=max_age_days)
        return total_purged

    except Exception as e:
        db.rollback()
        log_event("PURGE_EXPIRED_JOBS_ERROR", error=str(e), max_age_days=max_age_days)
        return 0


def purge_example_jobs(db: Session) -> int:
    """
    Remove definitivamente vagas de teste, mock ou exemplo do sistema.
    Identifica vagas de origem 'mock', domínios sintéticos (example.com),
    empresas fictícias (Empresa Alpha, Vagas Testes) ou vagas marcadas com [TESTE].
    """
    try:
        example_filter = or_(
            Job.source == "mock",
            Job.source.ilike("%mock%"),
            Job.url.ilike("%example.com%"),
            Job.url.ilike("%-demo.gupy.io%"),
            Job.company.ilike("%Empresa Alpha%"),
            Job.company.ilike("%VAGAS TESTES%"),
            Job.title.ilike("%[teste]%"),
            Job.title.ilike("%[mock]%"),
        )

        example_ids = list(db.scalars(select(Job.id).where(example_filter)).all())
        if not example_ids:
            return 0

        # Remoção segura em cascata
        db.execute(delete(JobMatch).where(JobMatch.job_id.in_(example_ids)))
        db.execute(delete(JobChangelog).where(JobChangelog.job_id.in_(example_ids)))
        db.execute(delete(Notification).where(Notification.job_id.in_(example_ids)))
        db.execute(delete(JobFeedback).where(JobFeedback.job_id.in_(example_ids)))
        db.execute(delete(UserFavorite).where(UserFavorite.job_id.in_(example_ids)))
        db.execute(delete(Job).where(Job.id.in_(example_ids)))

        # Limpeza de IDs órfãos em excluded_jobs
        prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
        if prefs and prefs.excluded_jobs:
            example_set = set(example_ids)
            cleaned = [jid for jid in prefs.excluded_jobs if jid not in example_set]
            if len(cleaned) != len(prefs.excluded_jobs):
                prefs.excluded_jobs = cleaned

        db.commit()
        log_event("PURGED_EXAMPLE_JOBS", count=len(example_ids), ids=example_ids)
        return len(example_ids)

    except Exception as e:
        db.rollback()
        log_event("PURGE_EXAMPLE_JOBS_ERROR", error=str(e))
        return 0

