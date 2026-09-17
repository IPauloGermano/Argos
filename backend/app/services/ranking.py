from __future__ import annotations
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.config import settings

_SENIORITY_RANK = {
    "estagio": 0, "intern": 0, "junior": 1, "jr": 1, "trainee": 1,
    "mid": 2, "pleno": 2, "pl": 2, "senior": 3, "sr": 3,
    "lead": 4, "staff": 4, "principal": 5
}

TECH_ROLE_TERMS = [
    "desenvolvedor", "developer", "software", "python", "django", "backend", "front-end", "frontend",
    "full stack", "fullstack", "programador", "engenharia de software", "engenheiro de software",
    "dados", "data", "devops", "cloud", "api", "rest", "estágio em ti", "estágio de software"
]


def _rank(s: str) -> int:
    return _SENIORITY_RANK.get((s or "").strip().lower(), 2)


def calculate_role_score(job: dict, profile: dict, prefs: dict) -> tuple[int, list[str]]:
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    blob = f"{title} {desc}"
    reasons = []

    candidates = [*(prefs.get("desired_roles") or []), *(profile.get("roles") or [])]
    if not candidates:
        return 65, ["Cargo compatível com perfil geral"]

    # 1. Correspondência exata de cargo no título
    for c in candidates:
        if not c:
            continue
        c_low = c.lower()
        if c_low in title:
            reasons.append(f"🎯 Cargo exato '{c}' no título")
            return 100, reasons

    # 2. Foco específico em Python / Django no título
    if "python" in title or "django" in title:
        reasons.append("🐍 Vaga com foco direto em Python/Django no título")
        return 96, reasons

    # 3. Estágio em Tecnologia / Software no título
    if ("estagio" in title or "estágio" in title) and any(t in title for t in ["ti", "dev", "software", "computação", "sistemas", "tecnologia"]):
        reasons.append("🎓 Oportunidade de Estágio na área de Tecnologia")
        return 95, reasons

    # 4. Cargos de Engenharia / Desenvolvimento no título
    tech_title_hits = [t for t in ["desenvolvedor", "developer", "software", "backend", "devops", "engenheiro de software", "programador"] if t in title]
    if tech_title_hits:
        reasons.append(f"💻 Cargo de Engenharia/Desenvolvimento: {', '.join(tech_title_hits)}")
        return 88, reasons

    # 5. Correspondência nos termos do cargo na descrição
    for c in candidates:
        if not c:
            continue
        if c.lower() in desc:
            reasons.append(f"Cargo '{c}' citado no escopo da vaga")
            return 72, reasons

    # 6. Se o título for claramente fora de tecnologia, penaliza severamente
    has_tech = any(t in title for t in TECH_ROLE_TERMS) or any(t in blob for t in ["python", "django", "software", "desenvolvedor"])
    if not has_tech:
        return 0, ["Título não pertence à área de Tecnologia/Software"]

    return 45, ["Título não coincide diretamente com os cargos desejados"]


def calculate_skills_score(job: dict, profile: dict, prefs: dict) -> tuple[int, list[str]]:
    pskills = {(s or "").strip().lower() for s in (profile.get("skills") or []) if s}
    preferred = {(s or "").strip().lower() for s in (prefs.get("preferred_keywords") or []) if s}
    all_target_skills = pskills.union(preferred)
    reasons = []

    if not all_target_skills:
        return 60, ["Sem lista de tecnologias específicas"]

    blob = f"{job.get('title', '')} {job.get('description', '')} {' '.join(job.get('requirements') or [])}".lower()
    hits = [s for s in all_target_skills if s in blob]

    # Pontuação ponderada: Python e Django são diferenciais fundamentais
    score = 0
    if "python" in blob:
        score += 40
        reasons.append("🐍 Requisito essencial atendido: Python")
    if "django" in blob:
        score += 25
        reasons.append("⚡ Framework desejado atendido: Django")
    if any(k in blob for k in ["rest", "api", "apis rest"]):
        score += 15
    if any(k in blob for k in ["sql", "postgresql", "sqlite"]):
        score += 10
    if any(k in blob for k in ["git", "docker", "linux"]):
        score += 10

    # Adiciona proporção de outras tecnologias
    other_hits = [h for h in hits if h not in ("python", "django")]
    if other_hits:
        score += min(20, len(other_hits) * 5)

    reqs = {(r or "").strip().lower() for r in (job.get("requirements") or []) if r}
    if reqs and reqs.issubset(all_target_skills):
        score = max(score, 100)
        reasons.append("🎯 Todos os requisitos técnicos da vaga atendidos")

    final_score = max(0, min(100, score))
    if hits and not ("python" in blob or "django" in blob):
        reasons.append(f"Tecnologias encontradas: {', '.join(sorted(hits)[:4])}")
    elif not hits:
        reasons.append("Nenhuma das tecnologias preferidas identificada")

    return final_score, reasons


def calculate_seniority_score(job: dict, profile: dict, prefs: dict) -> tuple[int, list[str]]:
    job_sen = (job.get("seniority") or "").strip().lower()
    prof_sen = (profile.get("seniority") or "junior").strip().lower()
    title = (job.get("title") or "").lower()
    pref_levels = [s.lower() for s in (prefs.get("seniority_levels") or [])]

    is_entry_hunter = prof_sen in ("junior", "estagio", "intern") or (
        pref_levels and not any(s in ("senior", "pleno", "mid", "lead") for s in pref_levels)
    )

    if is_entry_hunter:
        # Se usuário busca Estágio / Júnior
        if any(w in title for w in ["sênior", "senior", "sr.", "lead", "staff", "principal", "especialista"]):
            return 25, ["Nível Sênior/Lead (acima da faixa inicial)"]
        if job_sen in ("senior", "staff", "lead", "principal"):
            return 25, ["Nível Sênior (acima da faixa inicial)"]
        if "estagio" in job_sen or "intern" in job_sen or "estágio" in title or "estagio" in title or "trainee" in job_sen:
            return 100, ["🎓 Nível Estágio ideal para seu momento acadêmico"]
        if "junior" in job_sen or "júnior" in title or "junior" in title or "trainee" in title:
            return 100, ["🌱 Nível Júnior perfeitamente compatível"]
        if job_sen in ("pleno", "mid") or "pleno" in title:
            return 55, ["Nível Pleno (exige experiência intermediária)"]
        if not job_sen:
            return 80, ["Nível aberto / acessível para início de carreira"]

    diff = abs(_rank(job_sen) - _rank(prof_sen))
    score = {0: 100, 1: 75, 2: 40}.get(diff, 15)
    return score, [f"Nível de senioridade ({job_sen or 'não especificado'})"]


def calculate_location_score(job: dict, prefs: dict) -> tuple[int, list[str]]:
    pref_locs = [(l or "").strip().lower() for l in (prefs.get("locations") or []) if l]
    mode = (job.get("work_mode") or "").lower()
    loc = (job.get("location") or "").lower()

    if not pref_locs:
        return 80, ["Localização flexível"]

    # Extrai localidades específicas configuradas pelo usuário (desconsiderando termos genéricos)
    specific_locs = [
        p for p in pref_locs
        if p not in ("brasil", "brazil", "remoto", "remote")
    ]

    # 1. Correspondência direta na cidade/estado prioritário configurado pelo candidato
    if specific_locs:
        for p in specific_locs:
            city_part = p.split(",")[0].split("-")[0].strip()
            if (p in loc or (len(city_part) >= 3 and city_part in loc)):
                return 100, [f"📍 Oportunidade na sua localização prioritária ({job.get('location')})"]

    # 2. Vaga 100% Remota
    if mode in ("remote", "remoto") or "remoto" in loc:
        return 100, ["🌐 Oportunidade 100% Remota"]

    # 3. Presencial no exterior (quando o candidato busca no Brasil/Remoto)
    if any(foreign in loc for foreign in ["estados unidos", "united states", "usa", "malaysia", "uk", "canada", "chile", "israel", "germany"]):
        return 0, [f"⚠️ Presencial no exterior ({job.get('location')})"]

    # 4. Presencial em outro estado/região fora das localidades prioritárias
    if mode in ("onsite", "presencial") and specific_locs:
        return 35, [f"Presencial fora da sua região ({job.get('location')})"]

    if any(p in loc for p in pref_locs):
        return 80, [f"Localização compatível: {job.get('location')}"]

    return 50, ["Localização ampla"]


def calculate_recency_score(job: dict) -> tuple[int, list[str]]:
    published_at = job.get("published_at")
    if not published_at:
        return 50, ["Data de publicação recente"]

    if published_at.tzinfo is None:
        pub_utc = published_at.replace(tzinfo=timezone.utc)
    else:
        pub_utc = published_at.astimezone(timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - pub_utc

    if diff <= timedelta(hours=24):
        return 100, ["Publicada nas últimas 24 horas"]
    if diff <= timedelta(days=3):
        return 90, [f"Publicada há {diff.days} dias"]
    if diff <= timedelta(days=7):
        return 80, [f"Publicada há {diff.days} dias"]
    if diff <= timedelta(days=14):
        return 65, [f"Publicada há {diff.days} dias"]
    return 40, [f"Publicada há {diff.days} dias"]


def rank_job_relevance(job: dict, profile: dict, prefs: dict) -> dict:
    """
    Classifica a vaga por relevância (0 a 100) com atomicidade de perfil:
    Role: 30%, Skills: 30%, Seniority: 20%, Location: 15%, Recency: 5%.
    Aplica freio de senioridade (Sênior nunca supera Júnior/Estágio) e de distância física.
    """
    rs, rs_reasons = calculate_role_score(job, profile, prefs)
    ss, ss_reasons = calculate_skills_score(job, profile, prefs)
    sns, sns_reasons = calculate_seniority_score(job, profile, prefs)
    ls, ls_reasons = calculate_location_score(job, prefs)
    rec, rec_reasons = calculate_recency_score(job)

    # Cálculo ponderado conforme as 5 dimensões atômicas
    total = (
        0.30 * rs
        + 0.30 * ss
        + 0.20 * sns
        + 0.15 * ls
        + 0.05 * rec
    )
    final_score = int(round(max(0, min(100, total))))

    title = (job.get("title") or "").lower()
    job_sen = (job.get("seniority") or "").strip().lower()
    prof_sen = (profile.get("seniority") or "junior").strip().lower()
    is_entry_hunter = prof_sen in ("junior", "estagio", "intern")

    # Freio Atômico 1: Se o usuário é Júnior/Estagiário, vaga Sênior/Lead/Staff é limitada a 50%
    if is_entry_hunter:
        is_senior = any(w in title for w in ["sênior", "senior", "sr.", "lead", "staff", "principal", "especialista"]) or job_sen in ("senior", "staff", "lead", "principal")
        if is_senior:
            final_score = min(final_score, 50)

    # Freio Atômico 2: Presencial distante fora das cidades prioritárias do candidato
    mode = (job.get("work_mode") or "").lower()
    loc = (job.get("location") or "").lower()
    pref_locs = [(l or "").strip().lower() for l in (prefs.get("locations") or []) if l]
    specific_locs = [p for p in pref_locs if p not in ("brasil", "brazil", "remoto", "remote")]
    if specific_locs and mode in ("onsite", "presencial"):
        has_local_hit = any(
            (p in loc or (len(p.split(",")[0].strip()) >= 3 and p.split(",")[0].strip() in loc))
            for p in specific_locs
        )
        if not has_local_hit:
            final_score = min(final_score, 60)

    reasoning = [
        *rs_reasons,
        *ss_reasons,
        *sns_reasons,
        *ls_reasons,
    ]

    return {
        "score": final_score,
        "role_score": rs,
        "skills_score": ss,
        "seniority_score": sns,
        "location_score": ls,
        "recency_score": rec,
        "salary_score": rec,
        "reasoning": reasoning[:6]
    }

