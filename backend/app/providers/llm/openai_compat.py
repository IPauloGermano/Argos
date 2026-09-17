from __future__ import annotations
import json
import httpx
from .base import LLMProvider

MATCHING_SYSTEM = """Você é o agente de matching do Hermes Job Hunter.
Recebe CANDIDATE PROFILE, JOB DESCRIPTION e USER PREFERENCES.
Responda SOMENTE JSON válido com as chaves:
{"score": int 0-100, "skills_score": int, "role_score": int, "seniority_score": int,
 "location_score": int, "salary_score": int, "reasoning": [str, ...]}
Regras: não invente experiência; não assuma skills fora do perfil;
diferencie requisito obrigatório de desejável; considere senioridade,
localização e modelo de trabalho; explique por que combina; aponte gaps importantes."""

RESUME_SYSTEM = """Extraia o currículo para JSON válido com as chaves:
{"headline": str, "summary": str, "years_experience": int, "seniority": str (intern|junior|mid|senior|staff),
 "skills": [str], "roles": [str], "languages": [str]}. Responda SOMENTE JSON."""


class OpenAICompatProvider(LLMProvider):
    """Qualquer API OpenAI-compatible (OpenAI, OpenRouter, Ollama, etc)."""

    def __init__(self, api_key: str, model: str, base_url: str, timeout: int = 30):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _chat(self, system: str, user: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]

    @staticmethod
    def _safe_json(raw: str, fallback: dict) -> dict:
        try:
            return json.loads(raw)
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(raw[start:end + 1])
                except Exception:
                    pass
            return fallback

    async def analyze_job(self, job: dict, profile: dict, preferences: dict) -> dict:
        from app.services.matching import deterministic_scores

        base = deterministic_scores(job, profile, preferences)
        user = f"CANDIDATE PROFILE:\n{json.dumps(profile, ensure_ascii=False)[:4000]}\n\nJOB DESCRIPTION:\n{json.dumps(job, ensure_ascii=False)[:6000]}\n\nUSER PREFERENCES:\n{json.dumps(preferences, ensure_ascii=False)[:2000]}"
        try:
            raw = await self._chat(MATCHING_SYSTEM, user)
            llm = self._safe_json(raw, {})
            # Combina: média ponderada 60% determinístico + 40% LLM para o score final,
            # evitando score arbitrário puro do LLM.
            out = dict(base)
            reasoning = llm.get("reasoning") or base.get("reasoning") or []
            for k in ("skills_score", "role_score", "seniority_score", "location_score", "salary_score"):
                if isinstance(llm.get(k), int):
                    out[k] = int(round(0.6 * base[k] + 0.4 * max(0, min(100, llm[k]))))
            llm_score = llm.get("score")
            if isinstance(llm_score, int):
                out["score"] = int(round(0.6 * base["score"] + 0.4 * max(0, min(100, llm_score))))
            out["reasoning"] = (reasoning or [])[:6]
            return out
        except Exception:
            # Falha do LLM não quebra o pipeline: usa determinístico + reasoning heurístico.
            reasons = base.get("reasoning") or ["Match determinístico (LLM indisponível)"]
            return {**base, "reasoning": reasons}

    async def parse_resume(self, resume_text: str) -> dict:
        fallback = {"headline": "Software Engineer", "summary": resume_text[:500],
                    "years_experience": 0, "seniority": "mid", "skills": [],
                    "roles": ["Software Engineer"], "languages": []}
        try:
            raw = await self._chat(RESUME_SYSTEM, resume_text[:8000])
            data = self._safe_json(raw, fallback)
            return {**fallback, **data}
        except Exception:
            return fallback
