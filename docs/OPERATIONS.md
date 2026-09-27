# Operações — Backup/Restore, Migrações, Garantias

## Subir (mínimo)
```bash
docker compose up -d --build
docker compose ps            # 6 serviços Up (postgres, redis, backend Healthy, worker, scheduler, frontend)
curl -m 10 http://localhost:8000/health/ready   # {"status":"ok","database":"ok","redis":"ok"}
curl -m 10 http://localhost:8000/health/live    # {"status":"ok"} (mesmo com DB fora)
curl -s -X POST http://localhost:8000/api/agent/run  # {"triggered":true,"mode":"celery","task_id":...}
docker logs hermes-worker-1 | grep "succeeded"   # task_id <-> run_id correlacionados no result
```
## Config (nomes canônicos — iguais em local/compose/CI)
`DATABASE_URL`, `REDIS_URL` (broker+backend do Celery, sem `CELERY_*` separado),
`POSTGRES_USER/PASSWORD/DB`, `CORS_ORIGINS`, `AGENT_API_TOKEN` (equivale ao
`ADMIN_TOKEN` genérico), `TELEGRAM_WEBHOOK_SECRET`, `ENABLE_BUILTIN_SCHEDULER=false`
no compose (scheduler oficial = Celery Beat; APScheduler só local).

## Backup / Restore (PostgreSQL) — validado em 2026-09-27
```bash
# backup
docker exec argos-pg-test pg_dump -U hermes hermes > /tmp/opencode/argos_backup.sql
# destroy (teste)
psql -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
# restore
docker exec -i argos-pg-test psql -U hermes hermes < /tmp/opencode/argos_backup.sql
# compatibilidade
DATABASE_URL="postgresql+psycopg://hermes:hermes@localhost:5433/hermes" alembic -c backend/alembic.ini check
```
Evidência: dump 38K ok; restore ok; `users/jobs/job_matches/search_runs` = 1/1/1/1 preservados;
`alembic check` = `No new upgrade operations detected`, `current` = `b350663a6a02 (head)`.

## Migrações
- Novas instalações: `alembic -c backend/alembic.ini upgrade head` (13 tabelas, 33 constraints, 56 índices).
- Bancos antigos (pré-outbox): `apply_lightweight_migrations()` restaura colunas + `discard_ledger`;
  depois `alembic stamp head` + `alembic upgrade head` (0002 cria `uq_notifications_logical` + `ix_notif_outbox`;
  0003 cria `lock_skipped/provider_zero_results/provider_failures` em JSONB).
- Produção (Postgres): lifespan tenta `alembic upgrade head` primeiro, fallback lightweight.
  Worker NUNCA executa DDL.
- Repetição: `upgrade head` idempotente; `check` limpo (validado fresh + restaurado).

## Garantias explícitas
- Lock: Redis `SET NX EX` + payload `run_id/token`; release/renew via Lua compare-and-delete
  (apenas dono). TTL 600s (renovado a cada 50 jobs). Sem Redis: fallback `threading.Lock`
  (processo único, NÃO distribuído). Restart do Redis sem volume libera o lock (recuperação);
  com volume+AOF o lock sobrevive até o TTL (limitado, sem deadlock permanente).
- Outbox: at-least-once + dedupe lógica `UNIQUE(user,job,channel,event_type)`.
  `pending→sending→sent/failed(next_attempt_at, backoff)`. Exactly-once NÃO alegado
  (Telegram/Discord/SMTP sem idempotency key; caso `provider recebeu + DB falhou` gera retry duplicado).
- Worker restart: `task_acks_late=True` + prefetch 1 → task morta mid-run é reentregue
  (reexecuta o ciclo; idempotência de hash/changelog/notificação suprime duplicatas lógicas).
  Restart validado: worker reconecta, `inspect ping` ok, Beat continua despachando.
- Webhook Telegram: `POST /api/telegram/webhook` com `TELEGRAM_WEBHOOK_SECRET` configurado
  exige `X-Telegram-Bot-Api-Secret-Token` (401 sem ele); sem secret (dev) permite local.
  Comandos `/pausar|/retomar` por chat autenticado via secret; teste de regressão cobre 401/200.
- Vagas.com: slug em inglês retorna HTTP 200 com 0 cards → fallback PT `desenvolvedor`
  (1 tentativa) antes de `empty`; `empty` ≠ falha (sem `record_failure`).
- Lever: suporte PARCIAL explícito (`lever_partial=True`); boards verificados 2026-09-27:
  só `spotify` responde 200; 404 de board = skip sem `record_failure` (não polui breaker).
- Fuzzy dedup: narrowing por tokens de empresa (índice invertido, cap 40/ciclo-vaga);
  100 incoming × 300 recentes: 30000 → ~0-45 comparações (medido); recall 20/20 em
  duplicatas reais. Sem falsos negativos além de abreviações totais sem token comum
  (ex: IBM vs nome extenso — o próprio fuzzy >=90 também não pegaria).
- `notified` do SearchRun conta vagas acima do score mínimo, não envios confirmados
  (com canais desabilitados, `notifications` fica vazia e `notified>0`). Métrica de
  threshold, não de entrega — envios reais em `notifications.status=sent`.
