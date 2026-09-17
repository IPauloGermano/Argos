from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_
from app.models.entities import WeeklyReport, Job, JobMatch, JobChangelog, SearchPreferences, User


def generate_weekly_report(
    db: Session,
    user_id: int,
    top_limit: int = 10,
    force_new: bool = False
) -> dict:
    """
    Gera o Relatório Semanal de 7 Dias para o usuário.
    Consolida métricas, identifica vagas novas vs atualizadas, e seleciona Top N.
    """
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)

    # Busca relatórios anteriores do usuário para identificar vagas já apresentadas
    past_reports = db.scalars(
        select(WeeklyReport)
        .where(WeeklyReport.user_id == user_id)
        .order_by(WeeklyReport.id.desc())
        .limit(10)
    ).all()

    previously_presented = set()
    last_report_date = None
    for rep in past_reports:
        if rep.presented_job_ids:
            previously_presented.update(rep.presented_job_ids)
        if last_report_date is None and rep.created_at:
            last_report_date = rep.created_at

    # Busca preferências para verificar nota mínima
    prefs = db.scalar(select(SearchPreferences).where(SearchPreferences.user_id == user_id))
    min_score = (prefs.minimum_match_score if prefs else 70) or 70

    # Busca vagas ativas dentro da janela de 7 dias (publicadas ou descobertas)
    query = (
        select(Job, JobMatch)
        .outerjoin(JobMatch, and_(JobMatch.job_id == Job.id))
        .where(
            Job.status == "active",
            (Job.published_at >= week_start) | (Job.discovered_at >= week_start)
        )
        .order_by(JobMatch.score.desc().nullslast(), Job.id.desc())
    )
    rows = db.execute(query).all()

    # Deduplicação defensiva na listagem do relatório (garante URLs únicas)
    seen_urls = set()
    valid_jobs = []
    for job, match in rows:
        norm_url = (job.url or "").strip().lower()
        if norm_url and norm_url in seen_urls:
            continue
        if norm_url:
            seen_urls.add(norm_url)
        valid_jobs.append((job, match))

    total_analyzed = len(valid_jobs)
    total_compatible = 0
    total_new = 0
    total_remote = 0
    total_hybrid = 0
    total_onsite = 0
    total_internships = 0

    scored_jobs = []
    for job, match in valid_jobs:
        score = match.score if match else 0
        if score >= min_score:
            total_compatible += 1

        mode = (job.work_mode or "").lower()
        if mode in ("remote", "remoto"):
            total_remote += 1
        elif mode in ("hybrid", "hibrido"):
            total_hybrid += 1
        else:
            total_onsite += 1

        emp = (job.employment_type or "").lower()
        title_low = job.title.lower()
        if "estagio" in emp or "estágio" in emp or "estagio" in title_low or "estagi" in title_low:
            total_internships += 1

        is_already_seen = job.id in previously_presented

        # Verifica se houve alteração desde o último relatório
        has_update = False
        if is_already_seen:
            filters = [JobChangelog.job_id == job.id]
            if last_report_date:
                filters.append(JobChangelog.created_at >= (last_report_date - timedelta(seconds=5)))
            changelog_count = db.scalar(
                select(func.count(JobChangelog.id)).where(and_(*filters))
            ) or 0
            if changelog_count > 0:
                has_update = True

        status_tag = "NOVA" if not is_already_seen else ("ATUALIZADA" if has_update else "ANTERIOR")
        if not is_already_seen:
            total_new += 1

        scored_jobs.append({
            "job_id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "work_mode": job.work_mode,
            "employment_type": job.employment_type,
            "score": score,
            "url": job.url,
            "source": job.source,
            "published_at": job.published_at.isoformat() if job.published_at else None,
            "tag": status_tag,
            "reasoning": (match.reasoning if match else []) or []
        })

    # Ordena decrescente por score
    scored_jobs.sort(key=lambda x: x["score"], reverse=True)

    top_jobs = scored_jobs[:top_limit]
    presented_ids = [j["job_id"] for j in top_jobs]

    # Salva o relatório gerado no banco de dados
    report_record = WeeklyReport(
        user_id=user_id,
        week_start=week_start,
        week_end=now,
        total_jobs_analyzed=total_analyzed,
        total_compatible=total_compatible,
        total_new=total_new,
        total_remote=total_remote,
        total_hybrid=total_hybrid,
        total_onsite=total_onsite,
        total_internships=total_internships,
        top_jobs=top_jobs,
        presented_job_ids=presented_ids
    )
    db.add(report_record)
    db.commit()
    db.refresh(report_record)

    return {
        "report_id": report_record.id,
        "week_start": week_start.isoformat(),
        "week_end": now.isoformat(),
        "summary": {
            "total_analyzed": total_analyzed,
            "compatible": total_compatible,
            "new": total_new,
            "remote": total_remote,
            "hybrid": total_hybrid,
            "onsite": total_onsite,
            "internships": total_internships,
            "minimum_match_score": min_score
        },
        "top_5": top_jobs[:5],
        "top_10": top_jobs[:10],
        "top_20": scored_jobs[:20],
        "top_jobs": top_jobs
    }


def format_weekly_report_telegram(data: dict) -> str:
    """Formata o relatório semanal de 7 dias com visual limpo para o Telegram."""
    summary = data.get("summary", {})
    top_jobs = data.get("top_jobs", [])

    lines = [
        "📊 <b>RELATÓRIO SEMANAL DE VAGAS (7 DIAS)</b>",
        f"<i>Período: Últimos 7 dias</i>\n",
        "📈 <b>Resumo do Mercado:</b>",
        f"• Vagas analisadas: <b>{summary.get('total_analyzed', 0)}</b>",
        f"• Compatíveis com seu perfil: <b>{summary.get('compatible', 0)}</b>",
        f"• Novas descobertas: <b>{summary.get('new', 0)}</b>",
        f"• Remotas: {summary.get('remote', 0)} | Híbridas: {summary.get('hybrid', 0)} | Presenciais: {summary.get('onsite', 0)}",
        f"• Vagas de estágio: <b>{summary.get('internships', 0)}</b>\n",
        f"🏆 <b>Top {len(top_jobs)} Oportunidades Selecionadas:</b>\n"
    ]

    for idx, j in enumerate(top_jobs, 1):
        tag_prefix = ""
        if j.get("tag") == "ATUALIZADA":
            tag_prefix = "🔄 [Atualizada] "
        elif j.get("tag") == "NOVA":
            tag_prefix = "✨ [Nova] "

        score = j.get("score", 0)
        title = j.get("title", "Oportunidade")
        company = j.get("company", "Empresa")
        work_mode = j.get("work_mode", "").capitalize()
        url = j.get("url", "#")

        lines.append(
            f"<b>{idx}. {tag_prefix}{title}</b>\n"
            f"   🏢 {company} | 📍 {work_mode} | 🎯 <b>{score}% Match</b>\n"
            f"   🔗 <a href='{url}'>Ver Vaga Completa</a>\n"
        )

    lines.append("<i>Envie /favoritos para consultar suas vagas salvas ou /ajuda para mais comandos.</i>")
    return "\n".join(lines)
