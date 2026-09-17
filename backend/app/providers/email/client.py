from __future__ import annotations
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings


class EmailProvider:
    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.from_addr = settings.SMTP_FROM
        self.use_tls = settings.SMTP_USE_TLS

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.from_addr)

    def _send(self, to: str, subject: str, html: str) -> None:
        if not self.enabled:
            raise RuntimeError("SMTP não configurado")
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(self.host, self.port, timeout=settings.SMTP_TIMEOUT_SECONDS) as server:
            if self.use_tls:
                server.starttls()
            if self.username:
                server.login(self.username, self.password)
            server.sendmail(self.from_addr, [to], msg.as_string())

    async def send_job_notification(self, to: str, job: dict, score: int, reasoning: list[str]) -> None:
        bullets = "".join(f"<li>{r}</li>" for r in (reasoning or [])[:6])
        html = (f"<h2>🚨 {job.get('title','')}</h2>"
                f"<p><b>{job.get('company','')}</b> — {job.get('location','')} "
                f"({job.get('work_mode','')} / {job.get('seniority','')})</p>"
                f"<p>⭐ Match: <b>{score}%</b></p>"
                f"<ul>{bullets}</ul>"
                f"<p><a href=\"{job.get('url','')}\">Ver vaga</a></p>")
        self._send(to, f"[Hermes {score}%] {job.get('title','')} @ {job.get('company','')}", html)

    async def send_digest(self, to: str, items: list[dict], period: str) -> None:
        rows = "".join(
            f"<li><b>{it['job'].get('title')}</b> @ {it['job'].get('company')} — "
            f"{it['score']}% — <a href=\"{it['job'].get('url')}\">ver</a></li>"
            for it in items[:30]
        )
        html = f"<h2>Hermes — resumo {period} ({len(items)} vagas)</h2><ul>{rows}</ul>"
        self._send(to, f"[Hermes] Resumo {period}: {len(items)} vagas", html)
