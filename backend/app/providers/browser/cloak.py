"""Leitura de paginas via CloakBrowser (Chromium anti-deteccao).

Uso restrito e intencional:
- Apenas GET de paginas PUBLICAS de listagem de vagas.
- Sem login, sem formularios, sem submissao, sem interacao com CAPTCHA.
- Se a pagina exigir interacao humana (challenge persistente, login),
  desiste e retorna vazio — nunca tenta contornar.

E usado como fallback pelos conectores cujo HTTP simples e bloqueado
(403/Cloudflare/RSS extinto). Cada chamada abre e fecha o browser;
o volume e baixo (1 pagina por chamada, poucas paginas por ciclo).
"""
from __future__ import annotations
from app.core.config import settings


def cloak_available() -> bool:
    """True se o fallback via browser esta habilitado e instalado."""
    if not settings.CLOAK_ENABLED:
        return False
    try:
        import cloakbrowser  # noqa: F401
        return True
    except Exception:
        return False


async def fetch_rendered_html(url: str, *, wait_ms: int = 4000,
                              timeout_s: float | None = None) -> str:
    """Carrega a URL em Chromium headless e devolve o HTML renderizado."""
    from cloakbrowser import launch_async

    timeout_ms = int((timeout_s or settings.CLOAK_TIMEOUT_SECONDS) * 1000)
    browser = await launch_async(headless=settings.CLOAK_HEADLESS)
    try:
        page = await browser.new_page()
        await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        await page.wait_for_timeout(wait_ms)
        return await page.content()
    finally:
        await browser.close()
