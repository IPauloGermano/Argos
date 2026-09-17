from __future__ import annotations
from datetime import datetime, timezone
import httpx
from app.core.config import settings


class DiscordProvider:
    def __init__(self, webhook_url: str = "", timeout: int = 15):
        self.webhook_url = webhook_url or settings.DISCORD_WEBHOOK_URL
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    async def send_job_notification(self, job: dict, score: int, reasoning: list[str]) -> None:
        if not self.enabled:
            raise RuntimeError("Discord não configurado (webhook_url vazio)")

        pub = job.get("published_at")
        pub_str = pub.strftime("%d/%m/%Y") if isinstance(pub, datetime) else (str(pub)[:10] if pub else "Não informada")

        # Cor do embed baseada no score: Verde (>=85), Azul (>=70), Laranja (<70)
        color = 0x2ecc71 if score >= 85 else (0x3498db if score >= 70 else 0xe67e22)

        fields = [
            {"name": "Empresa", "value": job.get("company", "N/A"), "inline": True},
            {"name": "Área", "value": job.get("area", "Tecnologia"), "inline": True},
            {"name": "Localização", "value": job.get("location", "Brasil"), "inline": True},
            {"name": "Modelo", "value": (job.get("work_mode") or "N/A").capitalize(), "inline": True},
            {"name": "Tipo", "value": (job.get("employment_type") or "N/A").upper(), "inline": True},
            {"name": "Fonte", "value": (job.get("source") or "Web").capitalize(), "inline": True},
            {"name": "Data de Publicação", "value": pub_str, "inline": True},
            {"name": "Score de Relevância", "value": f"**{score}/100**", "inline": True},
        ]

        if reasoning:
            bullets = "\n".join(f"• {r}" for r in reasoning[:4])
            fields.append({"name": "Destaques", "value": bullets, "inline": False})

        embed = {
            "title": f"🎯 {job.get('title', 'Nova Oportunidade')}",
            "url": job.get("url", ""),
            "color": color,
            "fields": fields,
            "footer": {"text": "Hermes Job Hunter • Agente 24/7"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        payload = {
            "content": f"🚨 **Nova Oportunidade Encontrada!** Match: **{score}%**",
            "embeds": [embed]
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(self.webhook_url, json=payload)
            r.raise_for_status()
