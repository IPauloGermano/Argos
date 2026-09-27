"""Cliente HTTP compartilhado para providers: timeout, retry, backoff, jitter,
tratamento de 429/5xx com Retry-After. Não faz retry em 4xx permanentes."""
from __future__ import annotations
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Optional
import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class ProviderHttpResult:
    status_code: int
    text: str
    headers: dict
    latency_ms: float


async def fetch_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: Optional[float] = None,
    record_failure=None,
    source_name: str = "",
    **kwargs,
) -> httpx.Response:
    """GET/POST com retry apenas em 429/5xx/timeout. Respeita Retry-After."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.request(method, url, **kwargs)
            if resp.status_code in RETRYABLE_STATUS:
                retry_after = resp.headers.get("Retry-After")
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
                if record_failure:
                    try:
                        record_failure(f"HTTP {resp.status_code} attempt {attempt}")
                    except Exception:
                        pass
                if attempt < max_retries:
                    await asyncio.sleep(min(delay, 15.0))
                    continue
            return resp
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last_exc = e
            if record_failure:
                try:
                    record_failure(f"{type(e).__name__} attempt {attempt}")
                except Exception:
                    pass
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(min(delay, 15.0))
                continue
            raise
        except Exception:
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("fetch_with_retry exhausted without response")


def is_private_url(url: str) -> bool:
    """Heurística SSRF: bloqueia hosts privados quando validação externa ligada."""
    import ipaddress
    from urllib.parse import urlparse
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return True
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False
