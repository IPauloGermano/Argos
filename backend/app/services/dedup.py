from __future__ import annotations
import hashlib
import re
import unicodedata
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from typing import Optional

try:
    from rapidfuzz import fuzz
except ImportError:
    # Fallback caso rapidfuzz não esteja disponível
    class fuzz:  # type: ignore
        @staticmethod
        def token_sort_ratio(s1: str, s2: str) -> float:
            set1 = set(s1.split())
            set2 = set(s2.split())
            if not set1 or not set2:
                return 0.0
            intersection = set1.intersection(set2)
            union = set1.union(set2)
            return (len(intersection) / len(union)) * 100.0


TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "refid", "trackingid", "position", "pagenum", "origin", "midtoken",
    "trk", "trkinfo", "f_tpr", "currentjobid", "eBP", "ref_id", "fbclid", "gclid"
}

COMPANY_SUFFIXES = [
    r"\bltda\b", r"\bs/?a\b", r"\bme\b", r"\bepp\b", r"\binc\b", r"\bllc\b",
    r"\bcorp\b", r"\bcorporation\b", r"\bgrupo\b", r"\bgroup\b", r"\bbrasil\b",
    r"\bbrazil\b", r"\btecnologia\b", r"\bservicos\b", r"\bsolucoes\b"
]

SYNONYM_REPLACEMENTS = [
    (r"\bpessoa\s+desenvolvedora\b", "dev"),
    (r"\bpessoa\s+engenheira\b", "eng"),
    (r"\bpessoa\s+estagiaria\b", "estagio"),
    (r"\bestagi[aá]ri[oa]s?\b", "estagio"),
    (r"\best[aá]gio(s)?\b", "estagio"),
    (r"\bdesenvolv\w*\b", "dev"),
    (r"\bdeveloper(s)?\b", "dev"),
    (r"\bdevelop(ing|ment)?\b", "dev"),
    (r"\bprogramad[oa]r(a)?(es)?\b", "dev"),
    (r"\bengenheir[oa](s)?\b", "eng"),
    (r"\bengineer(s|ing)?\b", "eng"),
    (r"\banalyst(s)?\b", "analista"),
    (r"\bj[uú]nior(es)?\b", "jr"),
    (r"\bpleno(s)?\b", "pl"),
    (r"\bs[eê]nior(es)?\b", "sr"),
    (r"\btecnologia da informacao\b", "ti"),
    (r"\binformation technology\b", "ti"),
]



def strip_accents(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_url(url: str) -> str:
    """Normaliza URLs removendo todas as query strings, fragmentos e barras finais."""
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
        clean = p._replace(query="", fragment="", netloc=p.netloc.lower(), path=p.path.rstrip("/"))
        return urlunparse(clean).lower()
    except Exception:
        return url.strip().lower()



def normalize_text(s: str) -> str:
    """Normalização básica: lower, sem espaços duplos."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def normalize_company(company: str) -> str:
    """Remove sufixos jurídicos e normaliza nome da empresa."""
    text = strip_accents(normalize_text(company))
    for pat in COMPANY_SUFFIXES:
        text = re.sub(pat, "", text)
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str) -> str:
    """Aplica sinônimos, remove caracteres especiais e normaliza tokens do título."""
    text = strip_accents(normalize_text(title))
    for pat, rep in SYNONYM_REPLACEMENTS:
        text = re.sub(pat, rep, text)
    # Remove pontuação
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = [t for t in text.split() if len(t) > 1 and t not in {"em", "de", "da", "do", "para", "com", "e"}]
    return " ".join(tokens)


def sorted_title_tokens(title: str) -> str:
    norm = normalize_title(title)
    tokens = sorted(norm.split())
    return " ".join(tokens)


def normalize_location(location: str) -> str:
    loc = strip_accents(normalize_text(location))
    if any(k in loc for k in ["remoto", "remote", "teletrabalho", "anywhere"]):
        return "remoto"
    if any(k in loc for k in ["hibrido", "hybrid"]):
        return "hibrido"
    # Normaliza estados comuns do Brasil
    loc = re.sub(r"\b(sao paulo|sp)\b", "sp", loc)
    loc = re.sub(r"\b(rio de janeiro|rj)\b", "rj", loc)
    loc = re.sub(r"\b(minas gerais|mg)\b", "mg", loc)
    loc = re.sub(r"\b(parana|pr)\b", "pr", loc)
    loc = re.sub(r"\b(santa catarina|sc)\b", "sc", loc)
    loc = re.sub(r"\b(rio grande do sul|rs)\b", "rs", loc)
    return re.sub(r"[^\w\s]", "", loc).strip()


def content_hash(title: str, company: str, location: str, url: str = "", external_id: str = "", source: str = "") -> str:
    """Gera hash determinístico baseado em identificadores canônicos."""
    if external_id:
        src = (source or "").strip().lower()
        base = f"ext:{src}:{external_id}" if src else f"ext:{external_id}"
    elif url:
        base = f"url:{normalize_url(url)}"
    else:
        norm_t = sorted_title_tokens(title)
        norm_c = normalize_company(company)
        norm_l = normalize_location(location)
        base = f"{norm_t}|{norm_c}|{norm_l}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def dedup_key(title: str, company: str, location: str) -> str:
    norm_t = sorted_title_tokens(title)
    norm_c = normalize_company(company)
    norm_l = normalize_location(location)
    return f"{norm_t}|{norm_c}|{norm_l}"


def are_jobs_duplicate(
    job_a: dict,
    job_b: dict,
    similarity_threshold: float = 0.85
) -> tuple[bool, str]:
    """
    Avalia se job_a e job_b representam a mesma oportunidade.
    Retorna (is_duplicate, motivo).
    """
    # 1. URL canônica idêntica
    url_a = normalize_url(job_a.get("url", ""))
    url_b = normalize_url(job_b.get("url", ""))
    if url_a and url_b and url_a == url_b:
        return True, "exact_url_match"

    # 2. External ID idêntico na mesma fonte
    ext_a = str(job_a.get("external_id", "")).strip()
    ext_b = str(job_b.get("external_id", "")).strip()
    src_a = str(job_a.get("source", "")).strip()
    src_b = str(job_b.get("source", "")).strip()
    if ext_a and ext_b and src_a and src_b and ext_a == ext_b and src_a == src_b:
        return True, "exact_external_id_match"

    # 3. Empresa normalizada
    comp_a = normalize_company(job_a.get("company", ""))
    comp_b = normalize_company(job_b.get("company", ""))
    
    # Se uma não tiver empresa informada, não podemos assegurar similaridade forte sem URL
    if not comp_a or not comp_b:
        return False, "missing_company"

    # Similaridade de empresa
    company_match = (
        comp_a == comp_b or
        (len(comp_a) >= 4 and len(comp_b) >= 4 and (comp_a in comp_b or comp_b in comp_a)) or
        fuzz.token_sort_ratio(comp_a, comp_b) >= 90
    )

    if not company_match:
        return False, "different_company"

    # 4. Localização compatível
    loc_a = normalize_location(job_a.get("location", ""))
    loc_b = normalize_location(job_b.get("location", ""))
    mode_a = str(job_a.get("work_mode", "")).lower()
    mode_b = str(job_b.get("work_mode", "")).lower()

    location_compatible = (
        not loc_a or not loc_b or
        loc_a == loc_b or
        loc_a == "remoto" or loc_b == "remoto" or
        mode_a == "remote" or mode_b == "remote" or
        loc_a in loc_b or loc_b in loc_a
    )

    if not location_compatible:
        return False, "incompatible_location"

    # 5. Similaridade do Título (ex: 'Estágio em Desenvolvimento' vs 'Estagiário de Desenvolvimento')
    norm_title_a = sorted_title_tokens(job_a.get("title", ""))
    norm_title_b = sorted_title_tokens(job_b.get("title", ""))

    if norm_title_a == norm_title_b:
        return True, "exact_title_tokens_match"

    sim_score = fuzz.token_sort_ratio(norm_title_a, norm_title_b) / 100.0
    if sim_score >= similarity_threshold:
        return True, f"fuzzy_title_match ({round(sim_score * 100, 1)}%)"

    return False, "low_title_similarity"
