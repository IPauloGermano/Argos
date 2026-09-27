from __future__ import annotations
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# In-process fallback cache — used when Redis is unavailable
_CIRCUIT_STATE: dict[str, dict] = {}

# Redis key prefix for distributed state
_REDIS_PREFIX = "hermes:cb:"


def _redis_key(source_name: str) -> str:
    return f"{_REDIS_PREFIX}{source_name}"


def _get_redis():
    """Return a Redis client, or None if unavailable."""
    try:
        from app.core.database import get_redis_client
        r = get_redis_client()
        r.ping()
        return r
    except Exception:
        return None


def _serialize(data: dict) -> str:
    """Serialize circuit breaker dict to JSON (datetime → ISO string)."""
    out = {}
    for k, v in data.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return json.dumps(out)


def _deserialize(raw: str) -> dict:
    """Deserialize JSON back to dict (ISO string → datetime)."""
    data = json.loads(raw)
    for field in ("last_failure_at", "last_success_at", "cooldown_until"):
        if data.get(field):
            try:
                dt = datetime.fromisoformat(data[field])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                data[field] = dt
            except Exception:
                data[field] = None
    return data


def _default_state() -> dict:
    return {
        "state": "CLOSED",
        "failure_count": 0,
        "success_count": 0,
        "last_failure_at": None,
        "last_success_at": None,
        "cooldown_until": None,
        "last_error": "",
    }


def _load_state(source_name: str, r) -> dict:
    """Load state from Redis; fall back to in-process dict."""
    if r:
        try:
            raw = r.get(_redis_key(source_name))
            if raw:
                return _deserialize(raw)
        except Exception as exc:
            logger.debug("CB Redis load failed for %s: %s", source_name, exc)

    # In-process fallback
    if source_name not in _CIRCUIT_STATE:
        _CIRCUIT_STATE[source_name] = _default_state()
    return _CIRCUIT_STATE[source_name]


def _save_state(source_name: str, data: dict, r) -> None:
    """Persist state to Redis (TTL 24 h) and update in-process cache."""
    _CIRCUIT_STATE[source_name] = data
    if r:
        try:
            r.setex(_redis_key(source_name), 86400, _serialize(data))
        except Exception as exc:
            logger.debug("CB Redis save failed for %s: %s", source_name, exc)


class CircuitBreaker:
    """
    Controlador de Circuit Breaker por fonte para evitar sobrecarga e bloqueio de IPs.
    Estados: CLOSED (normal), OPEN (em quarentena após falhas), HALF_OPEN (teste).
    Estado persiste no Redis quando disponível (sobrevive a reinicializações).
    Fallback automático para dicionário em memória quando Redis não está acessível.
    """

    def __init__(
        self,
        source_name: str,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_seconds: int = settings.CIRCUIT_BREAKER_RECOVERY_SECONDS,
        recovery_timeout: Optional[int] = None,
    ):
        self.source_name = source_name
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_timeout if recovery_timeout is not None else recovery_seconds
        # Ensure in-process fallback is initialised
        if source_name not in _CIRCUIT_STATE:
            _CIRCUIT_STATE[source_name] = _default_state()

    @property
    def info(self) -> dict:
        """Return live state (Redis preferred, in-process fallback)."""
        r = _get_redis()
        return _load_state(self.source_name, r)

    @property
    def state(self) -> str:
        return self.info["state"]

    def can_execute(self) -> bool:
        r = _get_redis()
        data = _load_state(self.source_name, r)
        state = data["state"]
        now = datetime.now(timezone.utc)

        if state == "CLOSED":
            return True

        if state == "OPEN":
            cooldown = data.get("cooldown_until")
            if cooldown and now >= cooldown:
                # Transition to HALF_OPEN for probe attempt
                data["state"] = "HALF_OPEN"
                _save_state(self.source_name, data, r)
                return True
            return False

        # HALF_OPEN: allow one attempt
        return True

    def record_success(self):
        r = _get_redis()
        data = _load_state(self.source_name, r)
        now = datetime.now(timezone.utc)
        data["state"] = "CLOSED"
        data["failure_count"] = 0
        data["success_count"] = data.get("success_count", 0) + 1
        data["last_success_at"] = now
        data["cooldown_until"] = None
        data["last_error"] = ""
        _save_state(self.source_name, data, r)

    def record_failure(self, error_message: str = ""):
        r = _get_redis()
        data = _load_state(self.source_name, r)
        now = datetime.now(timezone.utc)
        data["failure_count"] = data.get("failure_count", 0) + 1
        data["last_failure_at"] = now
        data["last_error"] = error_message[:250]

        if data["state"] == "HALF_OPEN" or data["failure_count"] >= self.failure_threshold:
            data["state"] = "OPEN"
            data["cooldown_until"] = now + timedelta(seconds=self.recovery_seconds)

        _save_state(self.source_name, data, r)


def get_all_circuit_breakers() -> list[dict]:
    """Return status of all known circuit breakers (Redis + in-process merge)."""
    merged: dict[str, dict] = {}

    # In-process cache is the canonical list of known sources
    for name in _CIRCUIT_STATE:
        merged[name] = _CIRCUIT_STATE[name]

    # Overlay with Redis values (more up-to-date across processes)
    r = _get_redis()
    if r:
        try:
            keys = r.keys(f"{_REDIS_PREFIX}*")
            for key in keys:
                raw = r.get(key)
                if raw:
                    source = key.removeprefix(_REDIS_PREFIX)
                    merged[source] = _deserialize(raw)
        except Exception:
            pass

    result = []
    for name, data in merged.items():
        result.append({
            "source_name": name,
            "state": data.get("state", "CLOSED"),
            "failure_count": data.get("failure_count", 0),
            "success_count": data.get("success_count", 0),
            "last_failure_at": data.get("last_failure_at"),
            "last_success_at": data.get("last_success_at"),
            "cooldown_until": data.get("cooldown_until"),
            "last_error": data.get("last_error", ""),
        })
    return result
