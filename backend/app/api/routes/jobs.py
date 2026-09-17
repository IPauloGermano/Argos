from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from app.core.database import get_db
from app.models.entities import Job, JobMatch, JobChangelog

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


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
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    q = select(Job, JobMatch).outerjoin(JobMatch, JobMatch.job_id == Job.id)
    if status and status != "all":
        q = q.where(Job.status == status)
    if search:
        term = f"%{search}%"
        q = q.where(
            or_(
                Job.title.ilike(term),
                Job.company.ilike(term),
                Job.location.ilike(term),
                Job.description.ilike(term),
            )
        )
    if min_score:
        q = q.where(JobMatch.score >= min_score)
    if seniority:
        q = q.where(Job.seniority == seniority)
    if work_mode:
        q = q.where(Job.work_mode == work_mode)
    if company:
        q = q.where(Job.company.ilike(f"%{company}%"))
    if source:
        q = q.where(Job.source == source)
    if location:
        q = q.where(Job.location.ilike(f"%{location}%"))
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
            "date_status": j.date_status,
            "status": j.status,
            "status_reason": j.status_reason,
            "alternative_sources": j.alternative_sources or [],
            "score": m.score if m else None,
            "reasoning": (m.reasoning if m else []) or []
        }
        for j, m in rows
    ]


@router.get("/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Vaga não encontrada")
    m = db.scalar(select(JobMatch).where(JobMatch.job_id == job_id))
    changelogs = db.scalars(
        select(JobChangelog).where(JobChangelog.job_id == job_id).order_by(JobChangelog.created_at.desc())
    ).all()

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
        "date_status": j.date_status,
        "status": j.status,
        "status_reason": j.status_reason,
        "alternative_sources": j.alternative_sources or [],
        "score": m.score if m else None,
        "scores": {
            "skills": m.skills_score,
            "seniority": m.seniority_score,
            "location": m.location_score,
            "role": m.role_score,
            "recency": m.salary_score
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
