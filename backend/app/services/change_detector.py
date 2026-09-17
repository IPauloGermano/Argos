from __future__ import annotations
from typing import Optional


def detect_job_changes(existing_job, new_job_data: dict) -> list[dict]:
    """
    Compara uma vaga já existente no banco com a nova versão coletada.
    Retorna lista de alterações significativas para o JobChangelog.
    """
    changes = []

    # 1. Mudança de Salário Mínimo ou Máximo
    old_min = existing_job.salary_min
    new_min = new_job_data.get("salary_min")
    if old_min != new_min and (old_min is not None or new_min is not None):
        changes.append({
            "field_name": "salary_min",
            "old_value": str(old_min) if old_min is not None else None,
            "new_value": str(new_min) if new_min is not None else None,
            "change_type": "salary_update"
        })

    old_max = existing_job.salary_max
    new_max = new_job_data.get("salary_max")
    if old_max != new_max and (old_max is not None or new_max is not None):
        changes.append({
            "field_name": "salary_max",
            "old_value": str(old_max) if old_max is not None else None,
            "new_value": str(new_max) if new_max is not None else None,
            "change_type": "salary_update"
        })

    # 2. Mudança no Modelo de Trabalho (remoto, híbrido, presencial)
    old_mode = (existing_job.work_mode or "").strip().lower()
    new_mode = (new_job_data.get("work_mode") or "").strip().lower()
    if old_mode and new_mode and old_mode != new_mode:
        changes.append({
            "field_name": "work_mode",
            "old_value": old_mode,
            "new_value": new_mode,
            "change_type": "work_mode_update"
        })

    # 3. Mudança na Localização
    old_loc = (existing_job.location or "").strip().lower()
    new_loc = (new_job_data.get("location") or "").strip().lower()
    if old_loc and new_loc and old_loc != new_loc:
        changes.append({
            "field_name": "location",
            "old_value": existing_job.location,
            "new_value": new_job_data.get("location"),
            "change_type": "location_update"
        })

    # 4. Mudança de Status (ex: de fechada para reaberta)
    old_status = getattr(existing_job, "status", "active")
    new_status = new_job_data.get("status", "active")
    if old_status != new_status:
        changes.append({
            "field_name": "status",
            "old_value": old_status,
            "new_value": new_status,
            "change_type": "status_update"
        })

    # 5. Mudança Significativa na Descrição (tamanho ou conteúdo essencial)
    old_desc = (existing_job.description or "").strip()
    new_desc = (new_job_data.get("description") or "").strip()
    if old_desc and new_desc and old_desc != new_desc:
        len_diff = abs(len(new_desc) - len(old_desc))
        # Se alterou mais de 20% do tamanho ou mais de 80 caracteres
        if len_diff > 80 or (len_diff / max(len(old_desc), 1)) > 0.20:
            changes.append({
                "field_name": "description",
                "old_value": f"Tamanho anterior: {len(old_desc)} caracteres",
                "new_value": f"Novo tamanho: {len(new_desc)} caracteres",
                "change_type": "description_update"
            })

    # 6. Mudança na Data de Publicação
    old_pub = getattr(existing_job, "published_at", None)
    new_pub = new_job_data.get("published_at")
    if old_pub and new_pub and old_pub != new_pub:
        changes.append({
            "field_name": "published_at",
            "old_value": str(old_pub),
            "new_value": str(new_pub),
            "change_type": "date_update"
        })

    return changes


def is_critical_update(changes: list[dict]) -> bool:
    """
    Avalia se as alterações justificam enviar nova notificação ao usuário.
    Ex: salário alterado, modelo alterado para remoto, ou reabertura de vaga.
    """
    for ch in changes:
        if ch["change_type"] in ("salary_update", "status_update", "work_mode_update"):
            return True
    return False
