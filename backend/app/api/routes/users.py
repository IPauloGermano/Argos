from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import require_admin_token
from app.models.entities import User
from app.schemas import UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(db: Session = Depends(get_db)):
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if not user:
        user = User(name="Usuário", email="user@hermes.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.put("/me", response_model=UserOut, dependencies=[Depends(require_admin_token)])
def update_me(body: UserUpdate, db: Session = Depends(get_db)):
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if not user:
        user = User(name="Usuário", email="user@hermes.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user
