from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.config import settings

_CIRCUIT_STATE: dict[str, dict] = {}


class CircuitBreaker:
    """
    Controlador de Circuit Breaker por fonte para evitar sobrecarga e bloqueio de IPs.
    Estados: CLOSED (normal), OPEN (em quarentena após falhas), HALF_OPEN (teste).
    """
    def __init__(
        self,
        source_name: str,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_seconds: int = settings.CIRCUIT_BREAKER_RECOVERY_SECONDS,
        recovery_timeout: Optional[int] = None
    ):
        self.source_name = source_name
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_timeout if recovery_timeout is not None else recovery_seconds
        if source_name not in _CIRCUIT_STATE:
            _CIRCUIT_STATE[source_name] = {
                "state": "CLOSED",
                "failure_count": 0,
                "success_count": 0,
                "last_failure_at": None,
                "last_success_at": None,
                "cooldown_until": None,
                "last_error": ""
            }

    @property
    def info(self) -> dict:
        return _CIRCUIT_STATE[self.source_name]

    @property
    def state(self) -> str:
        return self.info["state"]

    def can_execute(self) -> bool:
        data = self.info
        state = data["state"]
        now = datetime.now(timezone.utc)

        if state == "CLOSED":
            return True

        if state == "OPEN":
            cooldown = data.get("cooldown_until")
            if cooldown and now >= cooldown:
                # Transiciona para HALF_OPEN para realizar teste
                data["state"] = "HALF_OPEN"
                return True
            return False

        if state == "HALF_OPEN":
            return True

        return True

    def record_success(self):
        data = self.info
        now = datetime.now(timezone.utc)
        data["state"] = "CLOSED"
        data["failure_count"] = 0
        data["success_count"] += 1
        data["last_success_at"] = now
        data["cooldown_until"] = None
        data["last_error"] = ""

    def record_failure(self, error_message: str = ""):
        data = self.info
        now = datetime.now(timezone.utc)
        data["failure_count"] += 1
        data["last_failure_at"] = now
        data["last_error"] = error_message[:250]

        if data["state"] == "HALF_OPEN" or data["failure_count"] >= self.failure_threshold:
            data["state"] = "OPEN"
            data["cooldown_until"] = now + timedelta(seconds=self.recovery_seconds)


def get_all_circuit_breakers() -> list[dict]:
    result = []
    for name, data in _CIRCUIT_STATE.items():
        result.append({
            "source_name": name,
            "state": data["state"],
            "failure_count": data["failure_count"],
            "success_count": data["success_count"],
            "last_failure_at": data["last_failure_at"],
            "last_success_at": data["last_success_at"],
            "cooldown_until": data["cooldown_until"],
            "last_error": data["last_error"]
        })
    return result
