from datetime import datetime, timezone, timedelta
from app.services.circuit_breaker import CircuitBreaker


def test_circuit_breaker_cycle():
    cb = CircuitBreaker("test_provider", failure_threshold=2, recovery_seconds=2)
    assert cb.can_execute() is True
    assert cb.info["state"] == "CLOSED"

    # 1ª falha
    cb.record_failure("HTTP 500")
    assert cb.can_execute() is True
    assert cb.info["state"] == "CLOSED"

    # 2ª falha -> atinge threshold e abre o circuito
    cb.record_failure("HTTP 500")
    assert cb.info["state"] == "OPEN"
    assert cb.can_execute() is False

    # Simula passagem do tempo de cooldown
    cb.info["cooldown_until"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert cb.can_execute() is True
    assert cb.info["state"] == "HALF_OPEN"

    # Sucesso na tentativa -> volta para CLOSED
    cb.record_success()
    assert cb.info["state"] == "CLOSED"
    assert cb.info["failure_count"] == 0
