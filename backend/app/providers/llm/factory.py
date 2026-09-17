from __future__ import annotations
from functools import lru_cache
from app.core.config import settings
from .base import LLMProvider
from .mock import MockLLMProvider


@lru_cache(maxsize=1)
def get_llm_provider() -> LLMProvider:
    if settings.LLM_API_KEY:
        from .openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
    return MockLLMProvider()
