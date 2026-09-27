from __future__ import annotations
import json
import threading
from datetime import datetime, timezone
from typing import Tuple, Optional
from app.core.database import get_redis_client
from app.core.logging import log_event

_LOCAL_LOCK = threading.Lock()
_LOCAL_LOCK_INFO: Optional[dict] = None
LOCK_KEY = "hermes:pipeline:distributed_lock"
DEFAULT_TTL_SECONDS = 600


def acquire_pipeline_lock(run_uuid: str, initiator: str = "pipeline", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> Tuple[bool, Optional[dict]]:
    """
    Tenta adquirir o lock distribuído de execução do pipeline.
    Usa Redis SET NX + EX para coordenação segura entre múltiplos workers/processos.
    O payload carrega run_id como token único do dono; a liberação exige
    compare-and-delete (apenas o dono libera). Possui fallback seguro para
    ambiente de processo único (threading.Lock).
    """
    payload = {
        "run_id": run_uuid,
        "token": run_uuid,
        "initiator": initiator,
        "acquired_at": datetime.now(timezone.utc).isoformat()
    }
    payload_str = json.dumps(payload)

    try:
        r = get_redis_client()
        r.ping()
        # SET key value NX EX <ttl>
        acquired = r.set(LOCK_KEY, payload_str, nx=True, ex=ttl_seconds)
        if acquired:
            return True, payload

        # Não conseguiu adquirir: lê quem é o dono atual
        current_val = r.get(LOCK_KEY)
        current_info = {}
        if current_val:
            try:
                current_info = json.loads(current_val)
            except Exception:
                current_info = {"raw": str(current_val)}
        return False, current_info

    except Exception:
        # Fallback local se o Redis estiver offline (ex: desenvolvimento local / testes)
        global _LOCAL_LOCK, _LOCAL_LOCK_INFO
        acquired = _LOCAL_LOCK.acquire(blocking=False)
        if acquired:
            _LOCAL_LOCK_INFO = payload
            return True, payload
        return False, _LOCAL_LOCK_INFO or {"initiator": "local_process"}


def release_pipeline_lock(run_uuid: str) -> bool:
    """
    Libera o lock distribuído com verificação de posse (evita liberar lock alheio).
    Usa script Lua compare-and-delete quando disponível para atomicidade.
    """
    released = False
    try:
        r = get_redis_client()
        r.ping()
        # Compare-and-delete atômico via Lua: só deleta se run_id/token bater
        try:
            lua = """
            local cur = redis.call('GET', KEYS[1])
            if not cur then return 0 end
            if string.find(cur, ARGV[1], 1, true) then
                return redis.call('DEL', KEYS[1])
            else
                return 0
            end
            """
            res = r.eval(lua, 1, LOCK_KEY, run_uuid)
            released = bool(res)
        except Exception:
            # Fallback: leitura + verificação + delete (melhor esforço)
            current_val = r.get(LOCK_KEY)
            if current_val:
                try:
                    current_info = json.loads(current_val)
                    if current_info.get("run_id") == run_uuid or current_info.get("token") == run_uuid:
                        r.delete(LOCK_KEY)
                        released = True
                except Exception:
                    # Payload ilegível: não deleta por segurança (pode ser de outro dono)
                    pass
    except Exception:
        pass

    global _LOCAL_LOCK, _LOCAL_LOCK_INFO
    if _LOCAL_LOCK.locked() and _LOCAL_LOCK_INFO and _LOCAL_LOCK_INFO.get("run_id") == run_uuid:
        _LOCAL_LOCK_INFO = None
        _LOCAL_LOCK.release()
        released = True

    return released


def renew_pipeline_lock(run_uuid: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
    """Renova o TTL do lock (lease renewal) somente se o chamador for o dono."""
    try:
        r = get_redis_client()
        r.ping()
        try:
            lua = """
            local cur = redis.call('GET', KEYS[1])
            if not cur then return 0 end
            if string.find(cur, ARGV[1], 1, true) then
                return redis.call('EXPIRE', KEYS[1], ARGV[2])
            else
                return 0
            end
            """
            return bool(r.eval(lua, 1, LOCK_KEY, run_uuid, ttl_seconds))
        except Exception:
            cur = r.get(LOCK_KEY)
            if cur and run_uuid in cur:
                return bool(r.expire(LOCK_KEY, ttl_seconds))
            return False
    except Exception:
        return False
