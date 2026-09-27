from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.core.database import SessionLocal, get_redis_client
from app.core.distributed_lock import acquire_pipeline_lock, release_pipeline_lock
from app.core.logging import log_event
from app.models.entities import (
    User, CandidateProfile, SearchPreferences, Job, JobMatch,
    JobChangelog, SearchRun
)
from app.services.dedup import (
    content_hash, dedup_key, normalize_title, normalize_company,
    normalize_location, are_jobs_duplicate
)
from app.services.ghost_detector import evaluate_job_freshness
from app.services.validation import validate_job
from app.services.ranking import rank_job_relevance
from app.services.change_detector import detect_job_changes, is_critical_update


def _get_or_create_user(db: Session) -> User:
    user = db.scalar(select(User).order_by(User.id).limit(1))
    if user:
        # Garante perfil e preferências
        if not user.profile:
            db.add(CandidateProfile(
                user_id=user.id, headline="Desenvolvedor de Software",
                summary="Desenvolvedor focado em tecnologias modernas e backend",
                skills=["Python", "FastAPI", "SQL", "Docker"],
                roles=["Backend Developer", "Desenvolvedor Python"],
                languages=["Português"]
            ))
            db.commit()
        if not user.preferences:
            db.add(SearchPreferences(
                user_id=user.id,
                desired_roles=["Backend Developer", "Desenvolvedor Python", "Software Engineer"],
                mandatory_keywords=[],
                preferred_keywords=["Python", "FastAPI", "PostgreSQL", "Docker"],
                excluded_keywords=[],
                seniority_levels=["junior", "mid", "senior", "estagio", "trainee"],
                locations=["Brasil", "Remoto"],
                work_modes=["remote", "hybrid", "onsite"],
                employment_types=["clt", "estagio", "trainee", "pj_contrato"],
                max_job_age_days=60,
                minimum_match_score=70,
                search_frequency_minutes=60,
                enabled_sources=["gupy", "linkedin", "remoteok", "vagas", "ciee", "greenhouse", "remotive", "getonbrd", "weworkremotely", "jobicy"],
                telegram_enabled=False,
                discord_enabled=False,
                email_enabled=False
            ))
            db.commit()
        return user

    user = User(name="Candidato Hermes", email="candidato@hermes.local")
    db.add(user)
    db.commit()
    db.refresh(user)

    db.add(CandidateProfile(
        user_id=user.id,
        headline="Desenvolvedor de Software",
        summary="Desenvolvedor focado em soluções escaláveis",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Git"],
        roles=["Backend Developer", "Software Engineer", "Desenvolvedor"],
        languages=["Português", "Inglês"]
    ))
    db.add(SearchPreferences(
        user_id=user.id,
        desired_roles=["Backend Developer", "Software Engineer", "Desenvolvedor"],
        mandatory_keywords=[],
        preferred_keywords=["Python", "FastAPI", "PostgreSQL", "Docker"],
        excluded_keywords=[],
        seniority_levels=["junior", "mid", "senior", "estagio", "trainee"],
        locations=["Brasil", "Remoto"],
        work_modes=["remote", "hybrid", "onsite"],
        employment_types=["clt", "estagio", "trainee", "pj_contrato"],
        max_job_age_days=60,
        minimum_match_score=70,
        search_frequency_minutes=60,
        enabled_sources=["gupy", "linkedin", "remoteok", "vagas", "ciee", "greenhouse", "remotive", "getonbrd", "weworkremotely", "jobicy"],
        telegram_enabled=False,
        discord_enabled=False,
        email_enabled=False
    ))
    db.commit()
    return user


def _profile_dict(p: CandidateProfile) -> dict:
    return {
        "headline": p.headline, "summary": p.summary,
        "years_experience": p.years_experience, "seniority": p.seniority,
        "skills": p.skills or [], "roles": p.roles or [],
        "languages": p.languages or []
    }


def _prefs_dict(p: SearchPreferences) -> dict:
    return {
        "desired_roles": p.desired_roles or [],
        "mandatory_keywords": p.mandatory_keywords or [],
        "preferred_keywords": p.preferred_keywords or [],
        "excluded_keywords": p.excluded_keywords or [],
        "seniority_levels": p.seniority_levels or [],
        "locations": p.locations or [],
        "regions": p.regions or [],
        "cities": p.cities or [],
        "areas": p.areas or [],
        "work_modes": p.work_modes or [],
        "minimum_salary": p.minimum_salary,
        "maximum_salary": p.maximum_salary,
        "employment_types": p.employment_types or [],
        "preferred_companies": p.preferred_companies or [],
        "excluded_companies": p.excluded_companies or [],
        "max_job_age_days": p.max_job_age_days or 60,
        "minimum_match_score": p.minimum_match_score or 70,
        "enabled_sources": p.enabled_sources or []
    }


def _job_to_dict(nj) -> dict:
    from app.providers.jobs.base import infer_seniority

    title = nj.title or ""
    return {
        "external_id": nj.external_id,
        "source": nj.source,
        "url": nj.url,
        "title": title,
        "company": nj.company,
        "location": nj.location,
        "work_mode": nj.work_mode,
        # Conectores raramente trazem senioridade: infere do titulo para
        # que o filtro de senioridade e a validacao funcionem.
        "seniority": nj.seniority or infer_seniority(title, nj.description or ""),
        "employment_type": nj.employment_type,
        "area": getattr(nj, "area", "Tecnologia") or "Tecnologia",
        "description": nj.description,
        "salary_min": nj.salary_min,
        "salary_max": nj.salary_max,
        "currency": nj.currency,
        "requirements": nj.requirements or [],
        "nice_to_have": nj.nice_to_have or [],
        "published_at": nj.published_at,
        "date_status": getattr(nj, "date_status", "unknown_date") or "unknown_date",
        "raw_data": getattr(nj, "raw_data", {}) or {}
    }


async def _collect_from_sources(query: dict, enabled_sources: list[str] = None) -> tuple[list, list[str], dict, int]:
    from app.providers.jobs.factory import get_job_sources

    sources = get_job_sources(enabled_sources)
    if not sources:
        return [], [], {}, 0

    async def _fetch_source(src):
        src_pages = 0
        src_found = 0
        timeout_limit = min(src.timeout, 8.0)
        try:
            found = await asyncio.wait_for(src.search(query), timeout=timeout_limit)
            items = found or []
            src_pages = getattr(src, "pages_crawled", 1)
            src_found = len(items)
            return {
                "name": src.name,
                "items": items,
                "error": None,
                "stats": {
                    "pages": src_pages,
                    "found": src_found,
                    "status": "ok"
                },
                "pages": src_pages
            }
        except asyncio.TimeoutError:
            err_msg = f"{src.name}: Timeout ({timeout_limit}s excedido)"
            return {
                "name": src.name,
                "items": [],
                "error": err_msg,
                "stats": {
                    "pages": getattr(src, "pages_crawled", 0),
                    "found": 0,
                    "status": "timeout",
                    "error": err_msg
                },
                "pages": getattr(src, "pages_crawled", 0)
            }
        except Exception as e:
            err_msg = f"{src.name}: {type(e).__name__} ({str(e)[:100]})"
            return {
                "name": src.name,
                "items": [],
                "error": err_msg,
                "stats": {
                    "pages": getattr(src, "pages_crawled", 0),
                    "found": 0,
                    "status": "error",
                    "error": err_msg
                },
                "pages": getattr(src, "pages_crawled", 0)
            }

    # Coleta todas as fontes em paralelo com asyncio.gather
    results = await asyncio.gather(*[_fetch_source(src) for src in sources], return_exceptions=True)

    collected: list = []
    errors: list[str] = []
    source_stats: dict = {}
    total_pages_crawled = 0

    for res in results:
        if isinstance(res, Exception):
            errors.append(f"collector_error: {type(res).__name__} ({str(res)[:100]})")
            continue
        if not res:
            continue
        collected.extend(res["items"])
        if res["error"]:
            errors.append(res["error"])
        source_stats[res["name"]] = res["stats"]
        total_pages_crawled += res["pages"]

    return collected, errors, source_stats, total_pages_crawled


def run_search_sync() -> dict:
    """
    Pipeline 24/7 de Alta Precisão e Cobertura:
    Collect (multi-fontes + paginação + circuit breaker)
    -> Normalização
    -> Filtro de Vagas Fantasmas / Antigas (>60 dias)
    -> Deduplicação Avançada (exata + fuzzy de títulos e empresas + links alternativos)
    -> Validação Estrita (integridade + anti-spam + filtros do usuário)
    -> Detecção de Alterações (histórico de modificações)
    -> Relevance Ranking Explicável (0-100)
    -> Persistência Transacional & Telemetria
    -> Notificação Multi-canal Isolada (Telegram, Discord, Email).
    """
    from app.services.notifications import notify_job

    started = datetime.now(timezone.utc)
    run_uuid = str(uuid4())

    # Lock Distribuído anti-sobreposição (B-04)
    lock_acquired, lock_info = acquire_pipeline_lock(run_uuid, initiator="sync_search")
    if not lock_acquired:
        log_event("SEARCH_SKIPPED_ALREADY_RUNNING", run_id=run_uuid, active_lock=lock_info)
        return {
            "status": "skipped",
            "reason": "already_running",
            "run_id": run_uuid,
            "active_lock": lock_info
        }

    db: Session = SessionLocal()

    stats = {
        "run_id": run_uuid,
        "pages_crawled": 0,
        "found": 0,
        "valid": 0,
        "deduplicated": 0,
        "discarded": 0,
        "discard_reasons": {},
        "new": 0,
        "updated": 0,
        "notified": 0,
        "errors": [],
        "source_stats": {}
    }

    # Inicializa SearchRun no início do ciclo com status 'running' (B-02 telemetria)
    try:
        search_run = SearchRun(
            run_id=run_uuid,
            started_at=started,
            status="running",
            pages_crawled=0,
            jobs_found=0,
            valid_count=0,
            duplicates_count=0,
            discarded_count=0,
            new_count=0,
            updated_count=0,
            notified_count=0,
            errors=[],
            source_stats={},
            discard_reasons={}
        )
        db.add(search_run)
        db.commit()
    except Exception as init_err:
        log_event("SEARCH_RUN_INIT_ERROR", error=str(init_err))
        db.rollback()

    r_client = None
    try:
        r_client = get_redis_client()
        r_client.set("hermes:agent:is_running", "1", ex=600)
    except Exception:
        r_client = None

    cycle_crashed = False

    try:
        log_event("SEARCH_STARTED", run_id=run_uuid)
        user = _get_or_create_user(db)
        profile = user.profile
        prefs = user.preferences
        assert profile and prefs

        p_dict = _profile_dict(profile)
        prefs_dict = _prefs_dict(prefs)

        # 0. Limpeza automática de vagas expiradas (> max_job_age_days) e vagas de exemplo/teste
        try:
            from app.services.cleanup import purge_expired_jobs, purge_example_jobs
            purged = purge_expired_jobs(db, max_age_days=prefs.max_job_age_days or 60)
            if purged > 0:
                stats["purged_expired"] = purged
            purged_examples = purge_example_jobs(db)
            if purged_examples > 0:
                stats["purged_examples"] = purged_examples
        except Exception as e:
            log_event("PURGE_EXPIRED_JOBS_ERROR", error=str(e))

        # Otimização O(N): carrega apenas identificadores das vagas recentes
        recent_cutoff = started - timedelta(days=prefs.max_job_age_days or 60)
        existing_urls = set(db.scalars(select(Job.url).where(Job.discovered_at >= recent_cutoff)).all())
        existing_external_ids = set(db.scalars(select(Job.external_id).where(Job.external_id != "", Job.discovered_at >= recent_cutoff)).all())

        query = {
            "desired_roles": prefs.desired_roles or profile.roles or ["Backend Developer"],
            "preferred_companies": prefs.preferred_companies or [],
            "locations": prefs.locations or ["Brasil"],
            "work_modes": prefs.work_modes or [],
            "seniority_levels": prefs.seniority_levels or [],
            "max_job_age_days": prefs.max_job_age_days or 60,
            "known_urls": existing_urls,
            "known_ids": existing_external_ids,
        }

        # 1. Coleta com Conectores Modulares
        collected, errors, source_stats, pages_count = asyncio.run(
            _collect_from_sources(query, prefs.enabled_sources)
        )
        stats["errors"] = list(errors) if errors else []
        stats["source_stats"] = source_stats
        stats["pages_crawled"] = pages_count
        stats["found"] = len(collected)
        log_event("JOBS_FOUND", count=len(collected), pages=pages_count)

        # Carrega vagas recentes do banco para comparação fuzzy de deduplicação
        recent_db_jobs = db.scalars(
            select(Job).where(Job.status != "closed").order_by(Job.id.desc()).limit(300)
        ).all()

        # Otimização de I/O: Pré-carrega todos os hashes existentes no banco em uma única query
        all_incoming_hashes = set()
        for nj in collected:
            try:
                ch = content_hash(
                    getattr(nj, "title", "") or "",
                    getattr(nj, "company", "") or "",
                    getattr(nj, "location", "") or "",
                    getattr(nj, "url", "") or "",
                    getattr(nj, "external_id", "") or "",
                    source=getattr(nj, "source", "") or ""
                )
                all_incoming_hashes.add(ch)
            except Exception:
                pass
        existing_jobs_by_hash = {}
        if all_incoming_hashes:
            for ej in db.scalars(select(Job).where(Job.content_hash.in_(all_incoming_hashes))).all():
                existing_jobs_by_hash[ej.content_hash] = ej

        seen_hashes: set[str] = set()
        seen_keys: set[str] = set()

        now_utc = datetime.now(timezone.utc)

        # Loop por vaga com isolamento estrito de erros (B-02: vaga envenenada não aborta ciclo)
        for nj in collected:
            try:
                jd = _job_to_dict(nj)
                title = jd["title"]
                company = jd["company"]
                location = jd["location"]

                norm_t = normalize_title(title)
                norm_c = normalize_company(company)
                norm_l = normalize_location(location)
                jd["normalized_title"] = norm_t
                jd["normalized_company"] = norm_c

                ch = content_hash(title, company, location, jd["url"], jd["external_id"], source=jd["source"])
                jd["content_hash"] = ch
                key = dedup_key(title, company, location)

                # 2. Eliminação de Vagas Fantasmas ou Antigas (> 60 dias)
                freshness = evaluate_job_freshness(jd, max_age_days=prefs.max_job_age_days or 60)
                jd["status"] = freshness["status"]
                jd["date_status"] = freshness["date_status"]
                jd["status_reason"] = freshness.get("ghost_reason", "")

                if freshness["is_ghost"]:
                    stats["discarded"] += 1
                    reason = freshness.get("ghost_reason") or "ghost_vacancy"
                    stats["discard_reasons"][reason] = stats["discard_reasons"].get(reason, 0) + 1
                    continue

                # 3. Deduplicação em Memória (dentro da mesma execução)
                if ch in seen_hashes or key in seen_keys:
                    stats["deduplicated"] += 1
                    continue

                # 4. Deduplicação no Banco (Exact Hash em memória ou query)
                existing_db_job = existing_jobs_by_hash.get(ch)

                # 5. Deduplicação no Banco (Fuzzy Matching de Título e Empresa)
                if not existing_db_job:
                    sim_threshold = getattr(settings, "DEDUPLICATION_SIMILARITY_THRESHOLD", 0.88)
                    for active_job in recent_db_jobs:
                        is_dup, dup_reason = are_jobs_duplicate(
                            {"title": title, "company": company, "location": location, "url": jd["url"]},
                            {"title": active_job.title, "company": active_job.company, "location": active_job.location, "url": active_job.url},
                            similarity_threshold=sim_threshold
                        )
                        if is_dup:
                            existing_db_job = active_job
                            break

                if existing_db_job:
                    stats["deduplicated"] += 1
                    if existing_db_job.id in (prefs.excluded_jobs or []):
                        continue
                    # Detecção e persistência real de Alterações (B-01)
                    changes = detect_job_changes(existing_db_job, jd)
                    if changes:
                        real_changes_applied = 0
                        for chg in changes:
                            fn = chg["field_name"]
                            new_val = chg["new_value"]

                            # Idempotência: verifica se o último changelog gravado já possui este valor
                            last_chg = db.scalar(
                                select(JobChangelog)
                                .where(JobChangelog.job_id == existing_db_job.id, JobChangelog.field_name == fn)
                                .order_by(JobChangelog.id.desc())
                                .limit(1)
                            )
                            if last_chg and last_chg.new_value == new_val:
                                continue

                            # Persiste os novos valores na tabela jobs
                            if fn == "salary_min":
                                existing_db_job.salary_min = jd.get("salary_min")
                            elif fn == "salary_max":
                                existing_db_job.salary_max = jd.get("salary_max")
                            elif fn == "work_mode":
                                existing_db_job.work_mode = jd.get("work_mode")
                            elif fn == "location":
                                existing_db_job.location = jd.get("location")
                            elif fn == "status":
                                existing_db_job.status = jd.get("status")
                            elif fn == "description":
                                existing_db_job.description = jd.get("description")
                            elif fn == "published_at":
                                existing_db_job.published_at = jd.get("published_at")

                            db.add(JobChangelog(
                                job_id=existing_db_job.id,
                                field_name=fn,
                                old_value=chg["old_value"],
                                new_value=new_val,
                                change_type=chg["change_type"]
                            ))
                            real_changes_applied += 1

                        if real_changes_applied > 0:
                            stats["updated"] += 1
                            existing_db_job.last_updated_at = now_utc

                    # Associação de fonte alternativa caso encontrada em outro portal
                    if jd["source"] and jd["source"] != existing_db_job.source:
                        alts = list(existing_db_job.alternative_sources or [])
                        if not any(a.get("url") == jd["url"] for a in alts):
                            alts.append({"source": jd["source"], "url": jd["url"], "discovered_at": now_utc.isoformat()})
                            existing_db_job.alternative_sources = alts

                    existing_db_job.last_checked_at = now_utc
                    continue

                seen_hashes.add(ch)
                seen_keys.add(key)

                # 6. Validação Estrita (Filtros de Exclusão, Mandatórios, Spam, Integridade)
                is_valid, discard_reason = validate_job(jd, prefs_dict)
                if not is_valid:
                    stats["discarded"] += 1
                    stats["discard_reasons"][discard_reason] = stats["discard_reasons"].get(discard_reason, 0) + 1
                    continue

                stats["valid"] += 1

                # 7. Relevance Ranking Engine (0-100)
                ranking_result = rank_job_relevance(jd, p_dict, prefs_dict)
                score = ranking_result["score"]
                reasoning = ranking_result["reasoning"]

                # 8. Persistência da Nova Oportunidade
                new_job = Job(
                    uuid=str(uuid4()),
                    external_id=jd["external_id"],
                    source=jd["source"],
                    url=jd["url"],
                    title=jd["title"],
                    normalized_title=norm_t,
                    company=jd["company"],
                    normalized_company=norm_c,
                    location=jd["location"],
                    work_mode=jd["work_mode"],
                    seniority=jd["seniority"],
                    employment_type=jd["employment_type"],
                    area=jd["area"],
                    description=jd["description"],
                    salary_min=jd["salary_min"],
                    salary_max=jd["salary_max"],
                    currency=jd["currency"],
                    requirements=jd["requirements"],
                    nice_to_have=jd["nice_to_have"],
                    published_at=jd["published_at"],
                    date_status=jd["date_status"],
                    discovered_at=now_utc,
                    last_checked_at=now_utc,
                    status=jd["status"],
                    status_reason=jd.get("status_reason", ""),
                    content_hash=ch,
                    alternative_sources=[],
                    raw_data=jd.get("raw_data", {})
                )
                try:
                    db.add(new_job)
                    db.flush()

                    # Salva correspondência e pontuação
                    db.add(JobMatch(
                        job_id=new_job.id,
                        profile_id=profile.id,
                        score=score,
                        skills_score=ranking_result.get("skills_score", 0),
                        seniority_score=ranking_result.get("seniority_score", 0),
                        location_score=ranking_result.get("location_score", 0),
                        role_score=ranking_result.get("role_score", 0),
                        salary_score=ranking_result.get("salary_score", 0),
                        reasoning=reasoning[:8]
                    ))
                    db.commit()
                    stats["new"] += 1
                    recent_db_jobs.append(new_job)
                    existing_jobs_by_hash[ch] = new_job
                except IntegrityError:
                    db.rollback()
                    stats["deduplicated"] += 1
                    continue

                # 9. Notificação Multi-canal se ultrapassar score mínimo
                min_score = prefs.minimum_match_score or 70
                if score >= min_score:
                    try:
                        asyncio.run(notify_job(
                            db,
                            user=user,
                            job_dict=jd,
                            job_id=new_job.id,
                            score=score,
                            reasoning=reasoning,
                            prefs=prefs
                        ))
                        stats["notified"] += 1
                    except Exception as e:
                        stats["errors"].append(f"notify:{type(e).__name__}")

            except Exception as job_exc:
                # Isolamento estrito de erro por vaga (B-02)
                err_source = getattr(nj, "source", None) or "unknown"
                err_url = getattr(nj, "url", None) or ""
                err_ext_id = getattr(nj, "external_id", None) or ""
                err_msg = f"{type(job_exc).__name__}: {str(job_exc)}"
                err_entry = {
                    "source": err_source,
                    "url": err_url,
                    "external_id": err_ext_id,
                    "error": err_msg
                }
                stats["errors"].append(err_entry)
                log_event(
                    "JOB_PROCESSING_ERROR",
                    run_id=run_uuid,
                    source=err_source,
                    external_id=err_ext_id,
                    url=err_url,
                    error=err_msg
                )
                continue

        # Salva em lote alterações em vagas existentes (B-06: com log estruturado de erro)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            err_msg = f"batch_commit_error:{type(e).__name__}:{str(e)}"
            stats["errors"].append(err_msg)
            log_event("BATCH_COMMIT_ERROR", run_id=run_uuid, error=str(e))

        finished = datetime.now(timezone.utc)
        status_str = "partial_error" if stats["errors"] else "completed"

        log_event("SEARCH_COMPLETED", **stats)
        return {
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            **stats,
            "status": status_str
        }

    except Exception as exc:
        cycle_crashed = True
        stats["errors"].append(f"cycle_crash:{type(exc).__name__}:{str(exc)}")
        log_event("SEARCH_CYCLE_CRASH", run_id=run_uuid, error=str(exc))
        raise

    finally:
        finished = datetime.now(timezone.utc)
        final_status = "failed" if cycle_crashed else ("partial_error" if stats["errors"] else "completed")

        # Atualiza SearchRun no banco de dados com estado garantido (running -> completed/partial_error/failed)
        try:
            sr = db.scalar(select(SearchRun).where(SearchRun.run_id == run_uuid))
            if sr:
                sr.finished_at = finished
                sr.status = final_status
                sr.pages_crawled = stats["pages_crawled"]
                sr.jobs_found = stats["found"]
                sr.valid_count = stats["valid"]
                sr.duplicates_count = stats["deduplicated"]
                sr.discarded_count = stats["discarded"]
                sr.new_count = stats["new"]
                sr.updated_count = stats["updated"]
                sr.notified_count = stats["notified"]
                sr.errors = stats["errors"]
                sr.source_stats = stats["source_stats"]
                sr.discard_reasons = stats["discard_reasons"]
                db.commit()
        except Exception as sr_err:
            log_event("SEARCH_RUN_FINALIZE_ERROR", error=str(sr_err))

        # Atualiza estado no Redis para o dashboard
        try:
            r = get_redis_client()
            r.set("hermes:agent:last_run", finished.isoformat())
            r.set("hermes:agent:last_stats", json.dumps(stats, default=str))
        except Exception:
            pass

        # Libera lock distribuído
        release_pipeline_lock(run_uuid)

        if r_client:
            try:
                r_client.delete("hermes:agent:is_running")
            except Exception:
                pass
        db.close()
