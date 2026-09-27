#!/usr/bin/env python3
"""Seed do perfil de Paulo Germano no Argos Job Hunter (branch dev).

Uso:
    cd ~/projects/Argos/backend && DATABASE_URL="sqlite:///./hermes.db" \
        ../.venv/bin/python ../scripts/seed_perfil_paulo.py

Origem dos dados: /home/user/Downloads/curriculo.pdf
- Nome/e-mail retirados do cabeçalho do CV.
- Headline/roles/seniority validados contra o parser determinístico
  (app.services.resume.deterministic_parse_resume -> junior, Backend Python/Django).
- Skills limpas manualmente: o PDF extrai texto sem espaços em alguns
  trechos ("ComputerScienceand..."), então a lista abaixo usa os nomes
  canônicos de SKILLS_CANONICAL em vez do output cru do parser.
"""
from __future__ import annotations

import os
import shutil
import sys

CURRICULO_SRC = "/home/user/Downloads/curriculo.pdf"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.database import engine, SessionLocal, apply_lightweight_migrations  # noqa: E402
from app.models.entities import User, CandidateProfile, SearchPreferences  # noqa: E402

PROFILE = {
    "headline": "Desenvolvedor Backend Python | Django | APIs REST",
    "summary": (
        "Estudante de Análise e Desenvolvimento de Sistemas (Unipê, 2026-2027). "
        "Experiência prática com Python e Django: aplicações web, integração com APIs REST, "
        "modelagem de bancos relacionais, autenticação, controle de acesso e testes automatizados. "
        "Projeto full-stack de catálogo de livros (Django, SQLite, Open Library API) com CRUD, "
        "isolamento de dados por usuário, proteção CSRF e testes unitários/de integração. "
        "Interesse em IA, desenvolvimento de software e aprendizado por projetos práticos."
    ),
    "years_experience": 1,
    "seniority": "junior",
    "skills": [
        "Python",
        "Django",
        "Django ORM",
        "APIs REST",
        "SQLite",
        "SQL",
        "HTML5",
        "Bootstrap",
        "Git",
        "GitHub",
        "Linux",
        "Docker",
        "Testes Unitários",
        "Testes de Integração",
        "Modelagem Relacional",
        "12-Factor App",
    ],
    "roles": [
        "Desenvolvedor Python Júnior",
        "Desenvolvedor Backend Júnior",
        "Desenvolvedor de Software Júnior",
        "Estagiário de Desenvolvimento de Software",
        "Estágio em TI",
        "Junior Python Developer",
        "Desenvolvedor Backend",
    ],
    "languages": ["Português (Nativo)", "Inglês (Intermediário - Leitura técnica)"],
}

PREFS = {
    "desired_roles": PROFILE["roles"],
    "mandatory_keywords": ["python", "django"],
    "preferred_keywords": PROFILE["skills"][:10],
    "excluded_keywords": [],
    "seniority_levels": ["estagio", "trainee", "junior"],
    "locations": ["João Pessoa, PB", "Paraíba", "Remoto", "Brasil"],
    "regions": ["Paraíba", "Nordeste", "Brasil"],
    "cities": ["João Pessoa"],
    "areas": ["Tecnologia", "Desenvolvimento de Software"],
    "work_modes": ["remoto", "hibrido", "presencial"],
    "minimum_salary": None,
    "maximum_salary": None,
    "employment_types": ["estagio", "trainee", "clt", "pj"],
    "preferred_companies": [],
    "excluded_companies": [],
    "max_job_age_days": 60,
    "minimum_match_score": 60,
    "search_frequency_minutes": 60,
    "enabled_sources": [
        "gupy",
        "linkedin",
        "remoteok",
        "vagas",
        "ciee",
        "greenhouse",
        "remotive",
        "getonbrd",
        "weworkremotely",
        "jobicy",
    ],
    "telegram_enabled": True,
    "discord_enabled": False,
    "email_enabled": False,
    "email_digest_mode": "immediately",
}


def main() -> None:
    apply_lightweight_migrations(engine)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).order_by(User.id).limit(1))
        if not user:
            user = User(
                name="Paulo Germano",
                email="impaulogermano@gmail.com",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.name = "Paulo Germano"
            user.email = "impaulogermano@gmail.com"
            db.commit()

        profile = db.scalar(
            select(CandidateProfile).where(CandidateProfile.user_id == user.id)
        )
        if not profile:
            profile = CandidateProfile(user_id=user.id)
            db.add(profile)

        # Currículo: copia o PDF para uploads/ e extrai o texto como a API faria.
        upload_dir = os.path.join(REPO_ROOT, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        dest = os.path.join(upload_dir, "curriculo-paulo-germano.pdf")
        if os.path.exists(CURRICULO_SRC):
            shutil.copyfile(CURRICULO_SRC, dest)
        resume_text = ""
        if os.path.exists(dest):
            try:
                from app.services.resume import extract_text_from_upload

                resume_text = extract_text_from_upload(dest, "application/pdf")[:20000]
            except Exception as e:  # noqa: BLE001
                print(f"[seed] aviso: falha ao extrair texto do PDF: {e}")

        for k, v in PROFILE.items():
            setattr(profile, k, v)
        profile.resume_file_path = dest
        profile.resume_text = resume_text

        prefs = db.scalar(
            select(SearchPreferences).where(SearchPreferences.user_id == user.id)
        )
        if not prefs:
            prefs = SearchPreferences(user_id=user.id)
            db.add(prefs)
        for k, v in PREFS.items():
            setattr(prefs, k, v)

        db.commit()
        print(f"[seed] user id={user.id} email={user.email}")
        print(f"[seed] headline={profile.headline}")
        print(f"[seed] seniority={profile.seniority} years={profile.years_experience}")
        print(f"[seed] skills={len(profile.skills)} roles={len(profile.roles)}")
        print(f"[seed] resume={profile.resume_file_path} ({len(profile.resume_text)} chars)")
        print(f"[seed] sources={prefs.enabled_sources}")
        print(f"[seed] min_score={prefs.minimum_match_score} freq={prefs.search_frequency_minutes}min")
    finally:
        db.close()


if __name__ == "__main__":
    main()
