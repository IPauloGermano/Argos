from datetime import datetime, timezone, timedelta
import re
import unicodedata
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from app.core.database import get_db
from app.core.security import require_admin_token
from app.models.entities import Job, JobMatch, JobChangelog, SearchPreferences, User

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

def _search_variants(term: str) -> list[str]:
    if not term:
        return []
    clean = term.strip()
    norm = unicodedata.normalize("NFKD", clean).encode("ASCII", "ignore").decode("ASCII")
    res = {clean, norm}
    # Gera variações com curinga SQL '_' para lidar com vogais acentuadas comuns no português (ex: joão/joao -> jo_o)
    smart_wildcard = re.sub(r"ao\b", "_o", norm, flags=re.IGNORECASE)
    smart_wildcard = re.sub(r"ai", "a_", smart_wildcard, flags=re.IGNORECASE)
    smart_wildcard = re.sub(r"io\b", "_o", smart_wildcard, flags=re.IGNORECASE)
    smart_wildcard = re.sub(r"ea", "_a", smart_wildcard, flags=re.IGNORECASE)
    res.add(smart_wildcard)

    common_accents = {
        "estagio": "estágio", "junior": "júnior", "senior": "sênior",
        "tecnico": "técnico", "analise": "análise", "programacao": "programação"
    }
    low = clean.lower()
    if low in common_accents:
        res.add(common_accents[low])
    for k, v in common_accents.items():
        if k in low:
            res.add(re.sub(rf"\b{k}\b", v, low))
        if v in low:
            res.add(re.sub(rf"\b{v}\b", k, low))
    return [f"%{v}%" for v in res if v]


@router.get("")
def list_jobs(
    db: Session = Depends(get_db),
    search: Optional[str] = None,
    min_score: int = 0,
    seniority: Optional[str] = None,
    location: Optional[str] = None,
    work_mode: Optional[str] = None,
    company: Optional[str] = None,
    source: Optional[str] = None,
    area: Optional[str] = None,
    employment_type: Optional[str] = None,
    status: Optional[str] = "active",
    only_new: bool = False,
    exclude_dismissed: bool = True,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    q = select(Job, JobMatch).outerjoin(JobMatch, JobMatch.job_id == Job.id)
    if status and status != "all":
        q = q.where(Job.status == status)

    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    excluded_set = set(prefs.excluded_jobs or []) if prefs else set()

    if exclude_dismissed and excluded_set:
        q = q.where(Job.id.not_in(list(excluded_set)))

    if only_new:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        q = q.where((Job.discovered_at >= cutoff) | (Job.published_at >= cutoff))

    if search:
        variants = _search_variants(search)
        search_clauses = []
        for v in variants:
            search_clauses.extend([
                Job.title.ilike(v),
                Job.company.ilike(v),
                Job.location.ilike(v),
                Job.description.ilike(v),
            ])
        q = q.where(or_(*search_clauses))
    if min_score:
        q = q.where(JobMatch.score >= min_score)
    if seniority:
        q = q.where(Job.seniority == seniority)
    if work_mode:
        q = q.where(Job.work_mode == work_mode)
    if company:
        variants = _search_variants(company)
        q = q.where(or_(*(Job.company.ilike(v) for v in variants)))
    if source:
        q = q.where(Job.source == source)
    if location:
        loc_clean = location.split(",")[0].split("-")[0].split("/")[0].strip()
        variants = _search_variants(loc_clean)
        q = q.where(or_(*(Job.location.ilike(v) for v in variants)))
    if area:
        q = q.where(Job.area.ilike(f"%{area}%"))
    if employment_type:
        q = q.where(Job.employment_type == employment_type)

    q = q.order_by(JobMatch.score.desc().nullslast(), Job.id.desc()).limit(limit).offset(offset)
    rows = db.execute(q).all()

    return [
        {
            "id": j.id,
            "uuid": j.uuid,
            "source": j.source,
            "url": j.url,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "work_mode": j.work_mode,
            "seniority": j.seniority,
            "employment_type": j.employment_type,
            "area": j.area,
            "description": (j.description or "")[:2000],
            "salary_min": j.salary_min,
            "salary_max": j.salary_max,
            "currency": j.currency,
            "published_at": j.published_at.isoformat() if j.published_at else None,
            "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
            "date_status": j.date_status,
            "status": j.status,
            "status_reason": j.status_reason,
            "is_dismissed": j.id in excluded_set,
            "alternative_sources": j.alternative_sources or [],
            "score": m.score if m else None,
            "reasoning": (m.reasoning if m else []) or []
        }
        for j, m in rows
    ]


@router.post("/cleanup-expired", dependencies=[Depends(require_admin_token)])
def cleanup_expired_jobs_endpoint(db: Session = Depends(get_db)):
    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    max_age = (prefs.max_job_age_days if prefs else None) or 60
    from app.services.cleanup import purge_expired_jobs
    purged = purge_expired_jobs(db, max_age_days=max_age)
    return {"status": "ok", "purged_count": purged, "max_age_days": max_age}


@router.get("/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Vaga não encontrada")
    m = db.scalar(select(JobMatch).where(JobMatch.job_id == job_id))
    changelogs = db.scalars(
        select(JobChangelog).where(JobChangelog.job_id == job_id).order_by(JobChangelog.created_at.desc())
    ).all()
    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    excluded_set = set(prefs.excluded_jobs or []) if prefs else set()

    return {
        "id": j.id,
        "uuid": j.uuid,
        "source": j.source,
        "url": j.url,
        "title": j.title,
        "company": j.company,
        "location": j.location,
        "work_mode": j.work_mode,
        "seniority": j.seniority,
        "employment_type": j.employment_type,
        "area": j.area,
        "description": j.description,
        "salary_min": j.salary_min,
        "salary_max": j.salary_max,
        "currency": j.currency,
        "requirements": j.requirements or [],
        "nice_to_have": j.nice_to_have or [],
        "published_at": j.published_at.isoformat() if j.published_at else None,
        "discovered_at": j.discovered_at.isoformat() if j.discovered_at else None,
        "date_status": j.date_status,
        "status": j.status,
        "status_reason": j.status_reason,
        "is_dismissed": j.id in excluded_set,
        "alternative_sources": j.alternative_sources or [],
        "score": m.score if m else None,
        "scores": {
            "skills": m.skills_score,
            "seniority": m.seniority_score,
            "location": m.location_score,
            "role": m.role_score,
            "salary": m.salary_score,
            "recency": getattr(m, "recency_score", 0)
        } if m else {},
        "reasoning": (m.reasoning if m else []) or [],
        "changelog": [
            {
                "field_name": chg.field_name,
                "old_value": chg.old_value,
                "new_value": chg.new_value,
                "change_type": chg.change_type,
                "created_at": chg.created_at.isoformat() if chg.created_at else None
            }
            for chg in changelogs
        ]
    }


@router.post("/{job_id}/dismiss")
def dismiss_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Vaga não encontrada")

    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    if not prefs:
        user = db.scalar(select(User).order_by(User.id).limit(1))
        if not user:
            user = User(name="Usuário", email="user@hermes.local")
            db.add(user)
            db.commit()
            db.refresh(user)
        prefs = SearchPreferences(user_id=user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)

    excluded = list(prefs.excluded_jobs or [])
    if job_id not in excluded:
        excluded.append(job_id)
        prefs.excluded_jobs = excluded
        db.commit()

    return {"status": "ok", "job_id": job_id, "dismissed": True}


@router.post("/{job_id}/undismiss")
def undismiss_job(job_id: int, db: Session = Depends(get_db)):
    prefs = db.scalar(select(SearchPreferences).order_by(SearchPreferences.id).limit(1))
    if prefs and prefs.excluded_jobs and job_id in prefs.excluded_jobs:
        excluded = [jid for jid in prefs.excluded_jobs if jid != job_id]
        prefs.excluded_jobs = excluded
        db.commit()

    return {"status": "ok", "job_id": job_id, "dismissed": False}
