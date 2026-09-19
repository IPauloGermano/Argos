# AGENTS.md — Argos Job Hunter 2.0

## Regra principal
**Todas as alterações vão para a branch `dev`. Nunca commitar direto na `main`.**
Fluxo: trabalhar na `dev` → testar → PR/merge para `main` só com aprovação do dono.

## O que é
Radar pessoal de vagas 24/7. Monitora fontes, deduplica, filtra, calcula
compatibilidade com o perfil e notifica (Telegram/Discord/e-mail).
**Nunca implemente candidatura automática** — o usuário decide onde se candidatar.

## Stack
- Backend: FastAPI + SQLAlchemy + Celery + APScheduler (`backend/app`)
- Fontes de vagas: `backend/app/providers/jobs/` (gupy, linkedin, indeed,
  remoteok, vagas, ciee, greenhouse, remotive, getonbrd, weworkremotely, jobicy, mock, glassdoor)
- Browser fallback (anti-bot, só leitura): `backend/app/providers/browser/`
- Frontend: Next.js 14 + Tailwind (`frontend/`)
- Banco: Postgres (docker) ou SQLite (local). Fila: Redis.

## Comandos
- `make test` — suíte backend (usa `.venv`, SQLite em /tmp)
- `./.venv/bin/python -m pytest backend/tests -q` — direto
- `cd frontend && ./node_modules/.bin/tsc --noEmit` — checagem do frontend
- Execução local: `scripts/run_local.sh` · Docker: `docker compose up --build`

## Convenções
- `.env` nunca vai para o git (segredos). Usar `.env.example` como referência.
- `requirements.txt` é o contrato de deps do Docker; `.venv` local deve espelhá-lo.
- Conectores: só leitura (GET), sem login, sem CAPTCHA, com circuit breaker.
- Frontend consome `NEXT_PUBLIC_API_URL`; não quebrar contratos da API.
- Antes de finalizar: pytest verde + tsc limpo + (se mexer em conector) teste
  ao vivo mostrando `found > 0`.
- Não inventar bugs; relatar apenas o que foi verificado com evidência.
