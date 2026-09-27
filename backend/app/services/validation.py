from __future__ import annotations
import re
from typing import Optional

SPAM_PATTERNS = [
    r"\bganhe\s+dinheiro\s+(f[aá]cil|sem\s+sair\s+de\s+casa)\b",
    r"\brenda\s+extra\s+(garantida|f[aá]cil|imediata)\b",
    r"\btrabalhe\s+\d+\s+horas?\s+por\s+dia\s+e\s+ganhe\b",
    r"\bpague\s+uma\s+taxa\s+para\s+(se\s+candidatar|come[cç]ar)\b",
    r"\btaxa\s+de\s+(inscri[cç][aã]o|cadastro)\s+de\s+r\$\b",
    r"\bmarketing\s+multin[ií]vel\b|\bmmn\b",
    r"\bpir[aâ]mide\s+financeira\b",
    r"\bcripto\s+lucro\s+garantido\b",
    r"\bclique\s+no\s+link\s+para\s+resgatar\s+seu\s+pr[eê]mio\b",
]


def _norm_list(items) -> list[str]:
    return [(i or "").strip().lower() for i in (items or []) if i]


def is_spam_or_scam(title: str, description: str) -> tuple[bool, str]:
    """Identifica spam, golpes ou anúncios fraudulentos de emprego."""
    blob = f"{title or ''} {description or ''}".lower()
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, blob):
            return True, f"spam_pattern_detected: {pattern}"
    return False, "ok"


# Padrões de cargos claramente fora da área de Tecnologia/Software
NON_TECH_CAREERS_RE = re.compile(
    r"\b(atendente|gar[çc]om|cozinheir[oa]|enfermeir[oa]|enfermagem|t[ée]cnic[oa] de enfermagem|m[ée]dic[oa]|"
    r"vendedor(a)?|seminovos|avicultura|agricultura|motorista|frentista|recepcionista|limpeza|"
    r"servi[çc]os de loja|servi[çc]os gerais|servi[çc]os ao cliente|promotor(a)? de vendas|"
    r"gerente de loja|gerente de ciclo|gerente de p[óo]s-vendas|balconista|repositor|"
    r"operador(a)? de caixa|vigilante|porteiro|copeir[oa]|zelador(a)?|fisioterapeuta|"
    r"nutricionista|farmac[êe]utic[oa]|psic[óo]log[oa]|esteticista|manicure|mec[âa]nic[oa]|"
    r"almoxarife|estoquista|sinistros|constru[çc][ãa]o civil|pedreiro|auxiliar administrativo|"
    r"assistente administrativo|secret[áa]ri[oa]|administra[çc][ãa]o|direito|advocacia|advogad[oa]|"
    r"jur[íi]dic[oa]|cont[áa]bil|contabilidade|financeir[oa]|recursos humanos|\brh\b|psicologia|"
    r"elevador(es)?|manuten[çc][ãa]o de elevadores|farm[áa]cia|log[íi]stica|pedagogia|marketing|"
    r"publicidade|compras|centro de opera[çc][õo]es)\b",
    re.IGNORECASE
)

TECH_REGEX = re.compile(
    r"\b(desenvolvedor[a-z]*|developer|software|python|django|backend|front-end|frontend|"
    r"full stack|fullstack|programador[a-z]*|engenharia de software|engenheir[oa] de software|"
    r"devops|cloud|api|apis|rest|sql|postgres|postgresql|sqlite|git|docker|linux|"
    r"computa[çc][ãa]o|sistemas de informa[çc][ãa]o|an[áa]lise e desenvolvimento|"
    r"dados|data|ci[êe]ncia de dados|an[áa]lise de dados|analista de dados|engenharia de dados|"
    r"est[áa]gio em (ti|tecnologia|software|desenvolvimento|programa[çc][ãa]o|sistemas|dados|computa[çc][ãa]o|python|backend|frontend|devops|cloud|qa)|"
    r"est[áa]gio de (ti|software|desenvolvimento|dados)|est[áa]gio ti|estagi[áa]rio de ti|"
    r"qa|qa engineer|tester|cybersecurity|"
    r"seguran[çc]a da informa[çc][ãa]o|intelig[êe]ncia artificial|machine learning|tech lead|"
    r"tecnologia da informa[çc][ãa]o|\bti\b|genai|ia generativa)\b",
    re.IGNORECASE
)

TECH_TITLE_REGEX = re.compile(
    r"\b(desenvolvedor[a-z]*|developer|software|python|django|backend|frontend|fullstack|"
    r"programador[a-z]*|devops|cloud|dados|data|eng|engenheir[oa]|"
    r"est[áa]gio em (ti|software|desenvolvimento|sistemas|dados|computa[çc][ãa]o|python|backend|frontend|devops|cloud|qa)|"
    r"est[áa]gio de (ti|software|desenvolvimento|dados)|est[áa]gio ti|"
    r"tech|\bti\b)\b",
    re.IGNORECASE
)

SENIOR_TITLE_RE = re.compile(
    r"\b(s[êe]nior|senior|sr\.?|lead|staff|principal|especialista|head of|diretor|gerente de engenharia)\b",
    re.IGNORECASE
)

FOREIGN_LOCATION_RE = re.compile(
    r"(estados unidos|united states|seattle|san francisco|los angeles|california|new york|nova york|nova iorque|texas|"
    r"virginia|maryland|austin|denver|colorado|ohio|boston|massachusetts|malaysia|kuala lumpur|"
    r"united kingdom|london|israel|canada|germany|deutschland|singapore|australia|"
    r"chile|santiago|paraguai|paraguay|asuncion|asunci[óo]n|uruguay|uruguai|argentina|buenos aires|colombia|bogota|peru|lima|mexico|poland|polonia|thailand|bangkok)",
    re.IGNORECASE
)


def validate_job(job: dict, prefs: dict) -> tuple[bool, str]:
    """
    Validação completa da vaga contra requisitos de integridade, filtros do usuário e anti-spam.
    Retorna (is_valid, discard_reason).
    NUNCA descarta silenciosamente: sempre retorna motivo específico.
    """
    title = (job.get("title") or "").strip()
    company = (job.get("company") or "").strip()
    url = (job.get("url") or "").strip()
    desc = (job.get("description") or "").strip()

    # 0. Vagas Descartadas/Ignoradas pelo Usuário
    excluded_jobs = prefs.get("excluded_jobs") or []
    if job.get("id") and job.get("id") in excluded_jobs:
        return False, "user_excluded_job"

    # 1. Integridade mínima de dados
    if not title or len(title) < 3:
        return False, "missing_or_invalid_title"

    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False, "invalid_url"

    if not company:
        # Rejeita oportunidade anônima sem empresa identificada
        return False, "missing_company_name"

    # 2. Detecção de Vagas de Exemplo / Teste / Mock
    if (
        job.get("source") == "mock"
        or "/jobs/mock" in url
        or "-demo.gupy.io" in url
        or "[teste]" in title.lower()
        or "[mock]" in title.lower()
        or "empresa alpha" in company.lower()
        or "vagas testes" in company.lower()
    ):
        return False, "example_or_mock_job"

    # 3. Detecção de Spam / Golpes
    is_spam, spam_reason = is_spam_or_scam(title, desc)
    if is_spam:
        return False, spam_reason

    # 3. Status Fantasma / Encerrada
    status = job.get("status", "active")
    if status in ("closed", "potential_ghost"):
        return False, f"status_{status}"

    reqs = " ".join(job.get("requirements") or []).lower()
    nice = " ".join(job.get("nice_to_have") or []).lower()
    blob = f"{title.lower()} {desc.lower()} {reqs} {nice}"

    # 4. Palavras-chave Proibidas (Hard Filter com word-boundary para evitar falsos positivos como java -> javascript)
    excluded_keywords = _norm_list(prefs.get("excluded_keywords"))
    for kw in excluded_keywords:
        if kw:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, title, flags=re.IGNORECASE) or re.search(pattern, blob, flags=re.IGNORECASE):
                return False, f"excluded_keyword: {kw}"

    # 5. Empresas Proibidas
    excluded_companies = _norm_list(prefs.get("excluded_companies"))
    company_lower = company.lower()
    for comp in excluded_companies:
        if comp and (comp in company_lower or company_lower in comp):
            return False, f"excluded_company: {comp}"

    # 6. Alinhamento de Carreira / Domínio de Tecnologia
    # Se o usuário busca cargos de tecnologia/software, rejeita profissões não relacionadas
    desired_roles = _norm_list(prefs.get("desired_roles"))
    preferred_keywords = _norm_list(prefs.get("preferred_keywords"))
    is_tech_profile = not desired_roles or any(
        any(tk in r for tk in ("desenvolvedor", "developer", "software", "backend", "python", "ti", "estágio em ti", "estágio de software", "estágio em desenvolvimento"))
        for r in desired_roles
    )
    if is_tech_profile:
        if NON_TECH_CAREERS_RE.search(title) and not TECH_TITLE_REGEX.search(title):
            return False, f"unrelated_career_domain: {title}"

        # Exige ao menos um sinal explícito de tecnologia ou match nos cargos/skills desejados
        has_tech_signal = (
            bool(TECH_REGEX.search(blob))
            or any(r in blob for r in desired_roles)
            or any(kw in blob for kw in preferred_keywords)
        )
        if not has_tech_signal:
            return False, "no_tech_or_software_relevance"

    # 7. Palavras-chave Obrigatórias (considera título, descrição e requisitos estruturados)
    mandatory_keywords = _norm_list(prefs.get("mandatory_keywords"))
    if mandatory_keywords:
        has_mandatory = any(
            re.search(rf"\b{re.escape(kw)}\b", blob, flags=re.IGNORECASE)
            for kw in mandatory_keywords if kw
        )
        if not has_mandatory:
            return False, f"missing_mandatory_keyword: {mandatory_keywords}"

    # 8. Modelo de Trabalho (remoto, híbrido, presencial)
    pref_modes = _norm_list(prefs.get("work_modes"))
    job_mode = (job.get("work_mode") or "").strip().lower()
    norm_job_mode = "remote" if job_mode in ("remote", "remoto") else ("hybrid" if job_mode in ("hybrid", "hibrido") else "onsite")
    if pref_modes and job_mode:
        norm_pref_modes = [
            "remote" if m in ("remote", "remoto") else ("hybrid" if m in ("hybrid", "hibrido") else "onsite")
            for m in pref_modes
        ]
        if norm_job_mode not in norm_pref_modes:
            return False, f"work_mode_mismatch: {job_mode} not in {pref_modes}"

    # 9. Localização Geográfica e Bloqueio de Vagas Presenciais no Exterior
    pref_locs = _norm_list(prefs.get("locations"))
    job_loc = (job.get("location") or "").lower()
    has_foreign_pref = any(FOREIGN_LOCATION_RE.search(loc) for loc in pref_locs)
    if not has_foreign_pref and norm_job_mode != "remote":
        if FOREIGN_LOCATION_RE.search(job_loc):
            return False, f"foreign_onsite_location_mismatch: {job.get('location')}"

    # 10. Tipo de Oportunidade (estágio, CLT, trainee, PJ, etc.)
    pref_types = _norm_list(prefs.get("employment_types"))
    job_type = (job.get("employment_type") or "").strip().lower()
    if pref_types and job_type:
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
        allowed = set(pref_types)
        for pt in pref_types:
            allowed.update(type_equivalents.get(pt, set()))
        if job_type not in allowed and not any(pt in job_type or job_type in pt for pt in allowed):
            return False, f"employment_type_mismatch: {job_type} not in {pref_types}"

    # 11. Senioridade: Rejeita apenas cargos executivos de diretoria/alta gestão
    EXECUTIVE_MGMT_RE = re.compile(r"\b(diretor(a)?|head of|vp of|vice presidente|gerente executiv[oa])\b", re.IGNORECASE)
    if EXECUTIVE_MGMT_RE.search(title):
        return False, f"executive_management_mismatch: {title}"

    # 12. Salário
    min_sal = prefs.get("minimum_salary")
    if min_sal and job.get("salary_max"):
        try:
            if float(job["salary_max"]) < float(min_sal):
                return False, f"salary_below_minimum: max={job['salary_max']} < min_required={min_sal}"
        except (ValueError, TypeError):
            pass

    max_sal = prefs.get("maximum_salary")
    if max_sal and job.get("salary_min"):
        try:
            if float(job["salary_min"]) > float(max_sal):
                return False, f"salary_above_maximum: min={job['salary_min']} > max_required={max_sal}"
        except (ValueError, TypeError):
            pass

    return True, "valid"

