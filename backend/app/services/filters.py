from __future__ import annotations


def _norm_list(items) -> list[str]:
    return [(i or "").strip().lower() for i in (items or []) if i]


def apply_hard_filters(job: dict, prefs: dict) -> tuple[bool, str]:
    """Filtros determinísticos ANTES do LLM (economia de tokens). Retorna (passou, motivo)."""
    title = (job.get("title") or "").lower()
    company = (job.get("company") or "").lower()
    desc = (job.get("description") or "").lower()
    blob = f"{title} {desc}"

    excluded = _norm_list(prefs.get("excluded_keywords"))
    if any(k and k in blob for k in excluded):
        return False, "excluded_keyword"

    excluded_companies = _norm_list(prefs.get("excluded_companies"))
    if company and any(c and c in company for c in excluded_companies):
        return False, "excluded_company"

    levels = _norm_list(prefs.get("seniority_levels"))
    if levels and (job.get("seniority") or "").lower() not in levels:
        return False, "seniority"

    modes = _norm_list(prefs.get("work_modes"))
    if modes and (job.get("work_mode") or "").lower() not in modes:
        return False, "work_mode"

    emp_types = _norm_list(prefs.get("employment_types"))
    if emp_types and job.get("employment_type"):
        type_equivalents = {
            "clt": {"clt", "full_time", "full-time", "efetivo", "tempo integral"},
            "pj_contrato": {"pj", "pj_contrato", "contract", "freelance", "prestador", "contractor"},
            "pj": {"pj", "pj_contrato", "contract", "freelance", "prestador", "contractor"},
            "estagio": {"estagio", "estágio", "internship", "intern", "trainee"},
            "trainee": {"trainee", "estagio", "internship", "intern"},
            "full_time": {"clt", "full_time", "full-time", "efetivo"},
            "contract": {"pj", "pj_contrato", "contract", "freelance"},
            "internship": {"estagio", "estágio", "internship", "intern", "trainee"},
        }
        allowed = set(emp_types)
        for pt in emp_types:
            allowed.update(type_equivalents.get(pt, set()))
        j_type = (job.get("employment_type") or "").lower().strip()
        if j_type not in allowed and not any(pt in j_type or j_type in pt for pt in allowed):
            return False, "employment_type"

    min_sal = prefs.get("minimum_salary")
    if min_sal and job.get("salary_max"):
        try:
            if float(job["salary_max"]) < float(min_sal):
                return False, "salary_below_minimum"
        except (ValueError, TypeError):
            pass

    max_sal = prefs.get("maximum_salary")
    if max_sal and job.get("salary_min"):
        try:
            if float(job["salary_min"]) > float(max_sal):
                return False, "salary_above_maximum"
        except (ValueError, TypeError):
            pass

    return True, "ok"
