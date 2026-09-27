"""Rate limiting simples baseado em Redis com fallback em memória.

Protege endpoints sensíveis (trigger manual, teste de notificações,
admin, upload) contra abuso. Usa janela fixa por chave.
"""
from __future__ import annotations
import time
from collections import defaultdict
from fastapi import Request, HTTPException, status

_MEM_BUCKETS: dict[str, list[float]] = defaultdict(list)


def _redis_client():
    try:
        from app.core.database import get_redis_client
        r = get_redis_client()
        r.ping()
        return r
    except Exception:
        return None


def check_rate_limit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Retorna (allowed, retry_after_seconds)."""
    now = time.time()
    r = _redis_client()
    if r is not None:
        try:
            redis_key = f"hermes:ratelimit:{key}"
            pipe = r.pipeline()
            pipe.incr(redis_key)
            pipe.ttl(redis_key)
            count, ttl = pipe.execute()
            if count == 1:
                r.expire(redis_key, window_seconds)
                ttl = window_seconds
            if count > limit:
                return False, int(ttl if ttl and ttl > 0 else window_seconds)
            return True, 0
        except Exception:
            pass
    # Fallback em memória (processo único / testes)
    bucket = _MEM_BUCKETS[key]
    cutoff = now - window_seconds
    _MEM_BUCKETS[key] = [t for t in bucket if t > cutoff]
    if len(_MEM_BUCKETS[key]) >= limit:
        oldest = min(_MEM_BUCKETS[key]) if _MEM_BUCKETS[key] else now
        retry = int(window_seconds - (now - oldest)) + 1
        return False, max(retry, 1)
    _MEM_BUCKETS[key].append(now)
    return True, 0


def rate_limit(limit: int = 10, window_seconds: int = 60, key_prefix: str = "global"):
    """Factory de dependência FastAPI para rate limiting."""
    async def _dep(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        route = request.url.path
        key = f"{key_prefix}:{client_ip}:{route}"
        allowed, retry_after = check_rate_limit(key, limit, window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"error": {"code": "RATE_LIMITED", "message": f"Muitas requisições. Tente novamente em {retry_after}s."}},
                headers={"Retry-After": str(retry_after)},
            )
        return True
    return _dep


# Limites pré-configurados para endpoints sensíveis
limit_manual_trigger = rate_limit(limit=5, window_seconds=300, key_prefix="trigger")
limit_notify_test = rate_limit(limit=10, window_seconds=300, key_prefix="notify_test")
limit_admin = rate_limit(limit=30, window_seconds=60, key_prefix="admin")
limit_upload = rate_limit(limit=10, window_seconds=300, key_prefix="upload")
