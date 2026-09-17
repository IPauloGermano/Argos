from __future__ import annotations
import os
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import get_db
from app.models.entities import User, CandidateProfile
from app.schemas import ProfileOut, ProfileUpdate
from app.services.resume import validate_upload, extract_text_from_upload

router = APIRouter(prefix="/api/profile", tags=["profile"])
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))


def _get_user(db: Session) -> User:
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if not user:
        user = User(name="Usuário", email="user@hermes.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _get_profile(db: Session, user_id: int) -> CandidateProfile:
    p = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user_id))
    if not p:
        p = CandidateProfile(user_id=user_id)
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


@router.get("", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db)):
    user = _get_user(db)
    return _get_profile(db, user.id)


@router.put("", response_model=ProfileOut)
def update_profile(body: ProfileUpdate, db: Session = Depends(get_db)):
    user = _get_user(db)
    p = _get_profile(db, user.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.post("/resume", response_model=ProfileOut)
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    try:
        validate_upload(file.filename or "", file.content_type or "", len(data))
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        target_dir = UPLOAD_DIR
    except Exception:
        target_dir = "/tmp/hermes_uploads"
        os.makedirs(target_dir, exist_ok=True)
    user = _get_user(db)
    path = os.path.join(target_dir, f"user_{user.id}_{(file.filename or 'cv.pdf').replace('/', '_')}")
    with open(path, "wb") as f:
        f.write(data)
    try:
        text = extract_text_from_upload(path, file.content_type or "")
    except Exception as e:
        raise HTTPException(400, f"Falha ao extrair texto do arquivo: {e}")

    from app.services.resume import deterministic_parse_resume
    from app.providers.llm.factory import get_llm_provider

    try:
        parsed = await get_llm_provider().parse_resume(text[:8000])
    except Exception:
        parsed = {}

    # Se LLM não extraiu skills ou retornou vazio, combina com parser determinístico
    det_parsed = deterministic_parse_resume(text)
    if not parsed.get("skills"):
        parsed["skills"] = det_parsed.get("skills", [])
    if not parsed.get("roles"):
        parsed["roles"] = det_parsed.get("roles", [])
    if not parsed.get("seniority"):
        parsed["seniority"] = det_parsed.get("seniority", "junior")

    p = _get_profile(db, user.id)
    p.resume_file_path = path
    p.resume_text = text[:20000]
    for k in ("headline", "summary", "years_experience", "seniority", "skills", "roles", "languages"):
        if parsed.get(k) not in (None, ""):
            setattr(p, k, parsed[k])
    db.commit()
    db.refresh(p)
    return p
