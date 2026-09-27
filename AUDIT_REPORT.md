# ARGOS JOB HUNTER 2.0
## RELATÓRIO DE AUDITORIA TÉCNICA

> **Escopo:** branch `dev` @ `1ce4e0d` — `/home/user/projects/Argos`
> **Data:** 2026-09-27. **Método:** leitura integral do código + execução real.
> **Execuções próprias (evidência primária):** `pytest backend/tests` → **98 passed / 10,97s**;
> `tsc --noEmit` frontend → exit 0; ciclo real `run_search_sync` com 10 fontes →
> `found=108, valid=0, dedup=28, discarded=80, errors=[]`; smoke `mock` → 10 coletadas /
> 10 descartadas `example_or_mock_job`; ranking spot-check (Estágio Python=99,
> Backend Júnior=100, Senior Java descartada+15); API boot (`/health` ok, redis offline;
> `/api/profile`, `/api/preferences` servindo dados semeados); conectividade
> (remoteok/remotive/gupy HTTP 200); Gupy por termo (`Python`=12 itens, termos com
> cargo=0); `docker compose config` → exit 0.
> **NÃO executado:** `docker compose up` completo (build pesado + serviços externos) →
> boot da stack em produção = **NÃO VALIDADO**; PostgreSQL em runtime = **NÃO VALIDADO**;
> scan de CVE = **NÃO VALIDADO**.
> **Convenção:** FATO = lido no código ou medido em execução. INFERÊNCIA = marcado como tal.

### 1. Resumo Executivo

O Argos é um projeto **real e substancial** (~100 arquivos backend + frontend Next.js),
não um esqueleto: pipeline fim-a-fim executa de verdade contra a internet
(108 vagas coletadas, 0 erros), 98 testes passam, `tsc` limpo, API serve dados.
**Porém o sistema hoje NÃO cumpre a promessa 24/7 confiável nem entregaria valor
contínuo sem intervento:** com filtros realistas o ciclo produz **0 vagas válidas**;
o changelog duplica a cada ciclo (B-01); uma vaga envenenada aborta o ciclo sem
telemetria (B-02); 3 executores de ciclo coexistem sem lock (B-04); API sem
autenticação + CORS `.*` com credentials (B-06); circuit breaker é só-memória com
tabela órfã no banco; pesos de ranking documentados/configurados são ignorados
pelo código; `docker compose up` nunca foi provado nesta auditoria; CI inexistente.

### 2. Estado Real do Projeto

| Afirmação do README/docs | Estado real | Evidência |
|---|---|---|
| 12 fontes plug & play | 13 registradas; 1 mock; 1 desativada (indeed); 1 ausente (lever) | `factory.py:20-34`; `config.py:27` |
| 38 testes | **98 testes, todos passando** (doc desatualizada) | execução 10,97s |
| Ranking Cargo 25/Skills 30/Senioridade 15/Loc 10/Sal 10/Rec 10 | **FALSO no código:** 30/30/20/15/5, sem salário | `ranking.py:227-233` |
| Pesos configuráveis via env | **Ignorados** (`MATCH_WEIGHT_*` sem uso) | grep: zero usos fora `config.py` |
| Circuit breaker por fonte | Só-memória; tabela `circuit_breakers` órfã | `circuit_breaker.py:6`; `entities.py:202-212` |
| Scheduler 24/7 resiliente | 3 executores, sem lock, sem catch-up | `scheduler.py`; `celery_app.py:11-16`; `agent.py:162-172` |
| `GET /api/agent/metrics` | Existe | `agent.py:224-265` |
| Ciclos a cada 5/15/30min | UI só 1h/4h/24h; prefs aceitam 5–1440 | `profile/page.tsx:20-24`; `schemas:113` |
| Wellfound como fonte | Sem conector | `Argos Job Hunter.md:3` vs `providers/jobs/` |
| Deduplicação multi-camada + stemming | Parcial: sem stemming real; threshold hardcoded | `dedup.py`; `pipeline.py:390` |
| "Nunca inventa datas" | **Verdadeiro** (verificado) | `ghost_detector.py:31-32`; providers usam `unknown_date` |
| Verificação de link ativo | Flag morta (`VERIFY_JOB_URL_HEALTH` sem chamador) | grep zero chamadas |

### 3. Arquitetura

- **Estrutura pretendida vs real:** camadas existem
  (`providers/jobs/`, `services/`, `models/`, `schemas/`, `api/routes/`,
  `workers/`, frontend). **Desvios:** `repositories/__init__.py` vazio (0 linhas) —
  acesso a dados direto nas rotas/services; `services/matching.py:1-33` é shim que
  reexporta `ranking.py` (não é segundo engine); `services/filters.py:8` é **código
  morto no pipeline** (só importado em testes) e **diverge** de `validation.py`
  (ex: `filters.py:23-25` rejeita senioridade fora da lista vs `validation.py:217-219`
  só barra diretoria). `services/` tem ainda `telegram_bot.py` (lógica de bot
  dentro de services, deveria estar em providers). Severidade: média.
- **Acoplamento:** `pipeline.py` importa providers, todos os services e models —
  coordenador god-object aceitável para o porte, mas sem interfaces injetáveis
  (factory concreta). Sem dependências circulares detectadas (boot do uvicorn OK).
- **Gargalos arquiteturais:**
  1. `pipeline.py:298-299` carrega **TODAS** as URLs e external_ids do banco em
     memória por ciclo — O(N); com 1M de vagas, estouro/ lentidão (alta).
  2. Commit por vaga (`pipeline.py:488`) + fuzzy contra 300 recentes por vaga —
     O(ciclo × 300) chamadas rapidfuzz (média; teste de 500 dedups <2s existe).
  3. Sem fila entre coleta e processamento: tudo síncrono num único
     `run_search_sync` (média; Celery chama a mesma função monolítica).
  4. Três executores de ciclo (APScheduler + Celery beat 300s + `/run` manual)
     sem lock distribuído (alta — B-04).

### 4. Pipeline

**Ordem real no código** (`pipeline.py:286-542`): purge expiradas+exemplo (antes da
coleta) → collect (fontes em paralelo, cap 8s/fonte) → carrega 300 recentes →
por vaga: ghost (`365`) → dedup memória+hash+fuzzy (`377-394`) → change+alts
(`401-419`) → validate (`428`) → rank (`437`) → insert+flush+commit (`472-495`) →
notify (`501`) → commit lote (`515`, exceção engolida com rollback silencioso) →
SearchRun (`524-542`, só no sucesso).

- **Ordem questionável (não-bug):** ghost e dedup (fuzzy, caro) rodam **antes** da
  validação — rapidfuzz processa lixo que seria descartado depois
  (`pipeline.py:364-394` vs `428`). Otimização: validar antes de deduplicar.
- **Pode quebrar (B-02):** loop por vaga (`348-512`) **sem try/except**; exceção em
  `validate/rank/detect/db.flush` propaga, pula `SearchRun` e cai no `finally:561`
  (só limpa redis+close). **1 vaga envenenada aborta o ciclo e apaga a telemetria.**
- **Dados perdidos:** vagas descartadas não são persistidas — só contadores em
  `SearchRun.discard_reasons` (`539`). "Por que a vaga X não apareceu?" **não é
  respondível por vaga** (só agregado).
- **Exceção por fonte contida:** `_fetch_source` + `asyncio.wait_for(min(timeout,8s))`
  + `return_exceptions=True` (`pipeline.py:162-212`) — 1 fonte não aborta. OK.
- **Idempotência de vagas:** `content_hash` UNIQUE (`entities.py:86,120`) +
  pré-carga de hashes + `except IntegrityError → rollback, deduplicated+=1`
  (`pipeline.py:472-495`). Razoável; sem upsert (valores novos nunca atualizam a
  linha — causa B-01).
- **Notify após commit** (`488` antes de `501`): falha no Telegram **não** desfaz a
  vaga. OK por design.
- **Exceções genéricas:** zero `except:` bare no projeto (bom); `except Exception`
  disseminado (~25 arquivos) — adequado em providers (contenção), perigoso em
  `pipeline.py:515-518` (rollback silencioso sem log) e `getonbrd.py:111-117`
  (falha silenciosa de lookup).
### 5. Providers

Taxonomia usada: OK / FRÁGIL / PARCIAL / QUEBRADO / AUSENTE / MOCK / NÃO VALIDADO.
Fatos transversais: **todos usam `httpx`** (nenhum `requests`/`tenacity` — grep);
**nenhum tem retry/backoff**; pipeline impõe teto `min(src.timeout, 8.0)s`
(`pipeline.py:165-167`); `pages_crawled/last_status` atualizados; exceções contidas
(`return []`) exceto mock. `max_pages` **ignorado** em gupy, linkedin, vagas,
glassdoor, remotive, remoteok.

| Provider | Estado | Evidência |
|---|---|---|
| gupy | FRÁGIL | Real (`__NEXT_DATA__`, `gupy.py:116-214`); live: 12 itens isolado, **0 sob concorrência de 10 fontes** (flaky SSR); só termo `Python` retorna dados (termos com cargo=0, medido); 1 GET/termo, sem paginação (`PAGE_SIZE=12` declarada, loop offset ausente `166`); `seniority=""` fixo (`104`); sem data inventada (`86-94`) |
| linkedin | FRÁGIL | Real (guest API, `linkedin.py:18-201`); live: 7 itens; `start=0` fixo sem offset (`82-86`); `employment="clt"` hardcoded (`167-184`); delay 0,3s/6 targets (`16,66,188`); 429/999 com `break` (`95-101`) |
| remoteok | FRÁGIL→OK funcional | Real 1 GET (`remoteok.py:69-149`); live: 11 itens, status ok; `sleep(1.0)`; sem retry; datas epoch verificadas ou `unknown` |
| remotive | FRÁGIL | Real, loop `roles[:3]` limit=20 (`remotive.py:28-95`); live: 36 itens; `raise_for_status`→`except` genérico sem branch 429/403 (`44,84-86`); sem sleep; `_infer_seniority` nunca retorna vazio (default `mid`, `10-18`) |
| weworkremotely | FRÁGIL | Real RSS 3 feeds (`weworkremotely.py:38-142`); live: 33 itens; `max_pages` reaproveitado como nº de feeds (`50`) |
| jobicy | FRÁGIL | Real (`jobicy.py:37-165`); live: 21 itens; senioridade default `mid`; paginação por tags, ok |
| getonbrd | FRÁGIL (live 0 itens, status ok) | Real com paginação `terms[:3]×min(max_pages,2)` (`getonbrd.py:67-68`); **N+1 lookups de empresa por vaga** com cache e `except: pass` silencioso (`104-117`) — risco de estourar os 8s do pipeline |
| vagas | FRÁGIL (live 0 itens, status ok) | Scraping real (`vagas.py:19-146`, timeout 6s); até 2 URLs; `seniority=""` e `published_at=None+unknown` **sempre** (`108-126`) |
| ciee | FRÁGIL (live 0 itens, status ok) | Real (`web.ciee.org.br/api/vagas/publicas`); **único com paginação real** `1..max_pages` (`ciee.py:31`); `seniority="estagio"` fixo (`102-119`) — correto para o nicho |
| greenhouse | PARCIAL | Só Greenhouse (`boards-api.greenhouse.io`); **Lever ausente apesar do nome** (`greenhouse_lever.py:18-108`); boards = `preferred_companies` ou 2 defaults (`25`); `!=200→continue` **sem** `record_failure` (`41-45`, inconsistente com 429 que registra) |
| glassdoor | NÃO VALIDADO (nunca executado aqui; fora do default) | Real 1 GET (`glassdoor.py:17-102`); 403/429→`record_failure`; **sem sleep/retry**; `max_pages=2` hardcoded na factory (`factory.py:69`); "proteção rate-limit" do README = só early-return |
| indeed | QUEBRADO/DESATIVADO | Registrado (`factory.py:26,60-61`) mas fora do `JOB_SOURCES` default; RSS (`br.indeed.com/rss`, 1 pág. máx `67,178`) com falhas **silenciosas sem `record_failure`** (`79-85`) — fura o breaker; fallback browser é o **único** usuário de `cloak.py` (`indeed.py:172-190`) com `wait 4s` vs cap 8s do pipeline |
| mock | MOCK | Determinístico (`mock.py:26-65`); corretamente filtrado como `example_or_mock_job` (`validation.py:112-121`); só instanciado se `MOCK_JOBS_COUNT>0` (`factory.py:50-51`) |
| browser/cloak | PARCIAL/quase-morto | `cloak.py:28-41` abre/fecha Chromium por chamada; só indeed usa; `CLOAK_ENABLED=True` default mas `cloakbrowser` pode nem estar instalado (Dockerfile faz `install || true` silencioso); **cap 8s do pipeline vs `CLOAK_TIMEOUT 45s`** (`config.py:37`) = fallback sempre abortado fora do indeed |

**Pode um provider derrubar o pipeline?** Não por exceção (contidos + `return_exceptions`).
Sim por **tempo**: getonbrd N+1 e gupy 4 termos concorrem dentro dos 8s; um provider
lento não trava os demais (gather), mas suas vagas se perdem silenciosamente
(`status` registra, sem alerta).

### 6. Deduplicação — PARCIAL (funciona, com falsos ± conhecidos)

- URL: `dedup.py:65-75` remove **toda** query+fragmento+lowercase (não só UTM) —
  **agressivo**: `?id=123` distintos colidem (falso positivo). Severidade média.
- Empresa: sufixos LTDA/SA/ME/EPP/grupo/Brasil/tecnologia (`dedup.py:30-34,84-90`). OK.
- Título: sinônimos dev/developer/programador, jr/pl/sr, estágio→estagio
  (`36-54`); remove pontuação, tokens ≤1 char e stopwords (`93-101`).
  **Sem stemming morfológico real** (só mapa fixo) — README exagera. Baixa/média.
- Fuzzy: `token_sort_ratio/100` (`dedup.py:212-214`); pipeline fixa **0.88 hardcoded**
  (`pipeline.py:390`) — `settings.DEDUPLICATION_SIMILARITY_THRESHOLD` **existe mas
  não é lido** (mesmo valor por coincidência). Títulos curtos ("Dev Python" vs
  "Dev Python Jr") ficam no limiar — FP/FN plausíveis, sem medição (NÃO VALIDADO).
- `content_hash` (`dedup.py:126-137`): `external_id→ext:{id}` **sem source** — mesmo
  id numérico em 2 portais colide (B-08, média). Senão URL normalizada, senão
  título|empresa|localização.
- Cross-provider: anexa `alternative_sources[{source,url}]` sem duplicar
  (`pipeline.py:415-419`). OK.
- Janela de corrida checagem→insert existe, resolvida por UNIQUE+IntegrityError. OK.
- **Limite:** fuzzy só contra 300 `status!='closed'` recentes (`pipeline.py:323-325`);
  exato via hash cobre tudo (`340`). Risco adicional: substring de empresa
  (`dedup.py:181`, "Tech"⊂"Tech Solutions") e "qualquer lado remoto = compatível"
  (`194-200`) — FP.
- Como verificar correção: seed com pares rotulados (duplicatas reais + quase-duplicatas)
  e medir precisão/recall do threshold; teste `test_29` (500 dedups <2s) já garante teto.

### 7. Ghost Detection — IMPLEMENTADO E FUNCIONAL (com 2 ressalvas)

- `published_at=None → unknown_date`, **nunca inventa data**: `ghost_detector.py:31-32`;
  todos os providers auditados usam `None+unknown` quando sem data. Confirmado.
- `MAX_JOB_AGE_DAYS` aplicado em **2 lugares**: filtro no pipeline (`pipeline.py:365`)
  e delete em `cleanup.py:19-48` (protege favoritos `40`, cascata `64-68`, limpa
  `excluded_jobs` `72-77`). Evidência live: descartes `published_135/79/832/866_days_ago`.
- `CLOSED_INDICATORS` em título+descrição (`ghost_detector.py:7-19,104-106`). OK.
- Ressalva 1: **datas futuras nunca são ghost** — `age>max` falso p/ futuro
  (`ghost_detector.py:43`) e ranking dá **score 100** p/ futuro (`ranking.py:203`).
  Vaga com data errada p/ frente ganha boost. Baixa/média.
- Ressalva 2: `check_url_liveness` (`ghost_detector.py:61-81`) e
  `VERIFY_JOB_URL_HEALTH` (`config.py:51`) **sem nenhum chamador** — flag morta.
  Se ligada um dia: fetcha URL arbitrária da vaga (SSRF), HEAD→GET,
  `follow_redirects=True`, timeout 5s, fail-open (`81`). Documentar antes de ligar.
- `cleanup.py:46-48` usa `discovered_at` como fallback só p/ purge. OK.

### 8. Validação — IMPLEMENTADA E FUNCIONAL

- `validation.py:84-238`: **todos** os caminhos retornam `(bool, reason)` estável
  (`missing_or_invalid_title`, `invalid_url`, `missing_company_name`,
  `example_or_mock_job`, `excluded_keyword: kw`, `missing_mandatory_keyword: [...]`,
  `no_tech_or_software_relevance`, etc.). Auditoria agregada OK.
- Regras: integridade (título/URL/empresa) → mock → spam/fraude (regex taxa, MMN,
  pirâmide — `22-28`) → status closed/ghost → excluded → carreira não-tech
  (`NON_TECH_CAREERS_RE` + `TECH_TITLE_REGEX`, `32-68`) → sinal tech mínimo →
  mandatory (OR, `170-174`) → work_mode/employment_type com equivalências
  (`198-214`) → só diretoria barrada por senioridade (`217-219`) → salário min/max.
- Evidência live: 69 `missing_mandatory_keyword`, 6 `no_tech`, 5 fantasmas —
  **amostragem mostrou descartes corretos** (`Remote Office Assistant`,
  `Inside Sales Contractor`). Sem falsos negativos observados.
- Lacunas: descarte **não** registra provider/timestamp/id da vaga (só agregado no
  SearchRun); `mandatory_keywords` usa OR sobre `title+desc` apenas (ignora
  `requirements` — vaga com Python só em requirements é descartada; média);
  `excluded_keywords` com substring pode morder demais (ex: excluir "java" mata
  "javascript" — `138` usa `in`; média/baixa).

### 9. Ranking — IMPLEMENTADO, MAS FRÁGIL (doc e config divergem do código)

- Pesos reais: `0.30 role + 0.30 skills + 0.20 seniority + 0.15 location + 0.05 recency
  = 1.00` (`ranking.py:227-233`). Clamp 0–100 (`234`). Sem divisão por zero
  (única divisão `fuzz/100` em dedup; `change_detector.py:72` usa `max(len,1)`).
- **Divergências (FATO):** README diz 25/30/15/10/10/10 com salário; código usa
  30/30/20/15/5 **sem salário**; `MATCH_WEIGHT_*` do `.env`/config **ignorados**
  (grep zero usos). Score mínimo 60/70 do usuário respeitado no notify?
  (pipeline filtra por `prefs.minimum_match_score` — `pipeline.py:498`.)
- **Bugs de dados:** `salary_score = rec` — cópia do recency (`ranking.py:274`),
  gravada em `JobMatch.salary_score` (`pipeline.py:485`) = **coluna fictícia**;
  `jobs.py:190` expõe `"recency": m.salary_score` (rótulo errado; valor coincide por
  acidente). Média.
- Freios atômicos existem: cap 50 p/ sênior quando entry-hunter (`242-245`), cap 60
  p/ presencial distante (`252-258`). Reasoning exclui recency e trunca `[:6]`
  (`260-275`); caso divergente: role 100 + remoto 100 mas freio corta p/ 50 com texto
  "compatível" (cosmético).
- Spot-checks live com perfil júnior Python: Estágio=99, Backend Júnior=100,
  Senior Java=descartada+15. Cálculo correto nos casos testados.
- Como verificar correção: teste parametrizado com 5 vagas canônicas
  (junior-python-remota-recente / senior-java / presencial-exterior / fantasma /
  sem skills) assertando faixas de score — hoje só 2 testes de ranking existem.

### 10. Change Detection — IMPLEMENTADO, MAS COM BUG (B-01)

- `change_detector.py:5-91` + `pipeline.py:401-411`: detecta diffs e insere
  `JobChangelog` **sem checar duplicata prévia**; agravante: o pipeline **nunca
  escreve os novos valores no job existente** (só `last_checked_at/last_updated_at/
  alternative_sources`). Consequência: o mesmo diff (ex: salário) é re-detectado e
  **duplica 1 linha por ciclo por vaga alterada** — crescimento ilimitado.
  Correção: UPDATE dos campos no job + unique `(job_id, field_name, new_value)` ou
  checagem de último changelog igual. Verificação: rodar 2 ciclos e contar
  `JobChangelog` por job (deve ser 0 novos no 2º).
- `JobChangelog` sem unique/índice além de (job, created) (`entities.py:127-142`).
- `notified` existe mas o pipeline de notificação de changelog não foi confirmado
  (NÃO VALIDADO se changelog dispara alerta).
### 11. Banco de Dados — BEM MODELADO, COM LACUNAS DE INTEGRIDADE E ESCALA

- Models (`entities.py`): PKs em todos; FKs com `CASCADE`; `delete-orphan` em
  profile/preferences/changelogs; uniques em email, content_hash
  (`uq_jobs_content_hash:86,120`), (job,profile) em JobMatch (`148`),
  (user,job) em Favorite (`218`) e Feedback (`235`), run_id (`185`),
  source_name (`205`); índices em source/discovered/company/status/uuid/run/score.
- **Ausências:** `Notification` **sem** `UniqueConstraint(user_id,job_id,channel)`
  (`165-176`, só índices) → B-05; `JobChangelog` sem unique (B-01);
  `Job.uuid` com índice mas **sem unique** (`91`) — duplicável em teoria;
  `Notification.channel` sem índice; `published_at` **sem índice** embora
  `cleanup.py:45-48` filtre por ele (purge full-scan em tabelas grandes).
- **Timezone:** `DateTime(timezone=True)+server_default=func.now()` em tudo.
  `ghost_detector.py:35-38` e `ranking.py:195-198` tratam naive→UTC. **Frágil:**
  `agent.py:47-51`, `cleanup.py:46-47`, `telegram_bot.py:278-282` comparam coluna
  (naive no SQLite) com cutoff aware — no SQLite vira comparação texto; sem crash
  observado, semântica NÃO VALIDADA no Postgres.
- **SQLite↔PG:** `JSON().with_variant(JSONB(),postgresql)` (`entities.py:12`) —
  sem operadores PG no ORM (grep `->>`,`::jsonb`,`ARRAY` zero fora DDL). Default
  `'[]'` do ALTER SQLite vira TEXT (leitura via tipo JSON NÃO VALIDADA).
  Nenhuma query com sintaxe exclusiva encontrada. Risco residual: semântica de TZ.
- **Migrations:** sem Alembic/pasta migrations (AUSENTE). `apply_lightweight_migrations`
  = `create_all` + `ALTER ADD COLUMN excluded_jobs` (`database.py:33-58`), exceções
  engolidas com print. **Race:** lifespan do backend (`main.py:14`) e
  `worker_ready` do Celery (`celery_app.py:25-31`) executam DDL juntos.
- **Queries pesadas:** `existing_urls/external_ids` = **todas** as linhas em memória
  (`pipeline.py:298-299`) — O(N), quebra em ~1M (alta). `cleanup.py:40,54`
  carrega todos os favorite_ids + expired_ids (deleção em batch 500, mas SELECT
  total). Listagem `/api/jobs` sem `count(*)` (bom) mas **sem total** p/ UI (ruim);
  sem N+1 na listagem (1 outerjoin, `jobs.py:59,105`).
- Repositories: `repositories/__init__.py` vazio — camada inexistente (débito, baixa).

### 12. Scheduler 24/7 — PARCIAL (agenda, mas sem garantias de continuidade)

- Implementação: `AsyncIOScheduler` **só-memória**, sem jobstore/persistência, sem
  `max_instances/coalesce/misfire_grace_time/timezone` (`scheduler.py:41,60-66`).
  Recriado no lifespan (`main.py:17-20`); `start_scheduler` com job id fixo faz
  `reschedule` (não duplica — `scheduler.py:45-58`; `preferences.py:57-60`).
- **Pause é só flag** `_is_paused` (`scheduler.py:75-84`); job continua agendado.
- **Respostas às perguntas:**
  - *Backend morre 10min e volta?* Ciclos perdidos, **sem catch-up**; agendamento
    recriado do zero; histórico passado persiste em `SearchRun`. Sem heartbeat.
  - *Provider trava 20min?* Cortado em ≤8s/fonte (`pipeline.py:165-167`); demais
    fontes prosseguem; registrado em `source_stats`+`errors`, sem alerta.
  - *Dois ciclos simultâneos?* **Possível e sem lock**: flag redis
    `hermes:agent:is_running` (ex 600, `pipeline.py:272,562-564`) é **só display**
    (`agent.py:40-41`) — scheduler (`scheduler.py:18-21`, flag em memória) e Celery
    (`tasks.py:17-44`) **não a leem**. Resolução só via UNIQUE+IntegrityError.
- **Três executores ativos por padrão no compose** (B-04): APScheduler embutido
  (`ENABLE_BUILTIN_SCHEDULER=true`), Celery beat `periodic-search-if-due` 300s
  (`celery_app.py:11-16`) + digests, e `/api/agent/run` (tenta `celery.delay()`,
  fallback `asyncio.to_thread(run_search_sync)` que **pendura o request HTTP por
  minutos** — `agent.py:162-172`, `scheduler.py:87-90`). Overlap plausível,
  NÃO VALIDADO em runtime.
- `SearchRun` nunca persiste `running` (só `completed/partial_error`, `pipeline.py:521`),
  mas `agent.py:46-54` consulta `status='running'` — **checagem morta**.

### 13. Circuit Breakers — IMPLEMENTADO, MAS FRÁGIL

- Transições CLOSED→OPEN→HALF_OPEN→CLOSED existem (`circuit_breaker.py:48-83`);
  thresholds de settings (`3`/`300s`, `config.py:54-55`); teste unitário puro passa.
- **Estado só em memória** (`_CIRCUIT_STATE: dict`, `circuit_breaker.py:6`).
  `CircuitBreakerRecord` (`entities.py:202-212`) **órfã**: só lida p/ display
  (`telegram_bot.py:344`), nenhum insert/update. **Restart zera bloqueios** —
  fonte em surto de 429 volta a ser martelada após deploy. Média/alta.
- Sem lock (gather concorrente; risco baixo em loop único; inter-processos NÃO VALIDADO).
- Cobertura furada: RSS do indeed não registra falha (`indeed.py:79-85`);
  Greenhouse `!=200` não registra (`greenhouse_lever.py:44-45`). Padronizar.
- Como verificar correção: derrubar 1 fonte 4× seguidas, assertar OPEN; restartar e
  assertar OPEN persistido (após fix); checar `last_error`/`cooldown_until` coerentes.

### 14. API — IMPLEMENTADA E FUNCIONAL, SEM AUTH

- 30 endpoints em 10 routers, **todos implementados** (nenhum stub): jobs (5:
  listagem c/ 12 filtros + `limit≤200`/`offset`, cleanup-expired, detalhe c/
  changelog, dismiss/undismiss), agent (7: status/run/start/pause/runs/metrics/
  dashboard), profile (get/put/upload), preferences, users, notifications
  (histórico + **teste que envia mensagem real**), telegram (webhook+simulate),
  favorites, reports/weekly, feedback. Listagem sem N+1 e **sem total** (`jobs.py:59-107`).
- **Sem autenticação/autorização em nenhum endpoint** (zero Depends de auth; usuário
  = `order_by(id).limit(1)`). Sozinho é design single-user; combinado com CORS =
  B-06.
- Validação: `email_digest_mode` restrito (`preferences.py:36-37`); ranges no schema
  (`schemas:111-113`); `telegram/simulate` faz `int(chat_id)` **sem try → 500**
  (`telegram.py:20-52`, baixa).
- Upload: valida tamanho/extensão (`resume.py:96-109`); sanitiza só `/`
  (`profile.py:67`) — `..` e `\` passam (traversal contido no Linux pelo `/`,
  NÃO VALIDADO no Windows; baixa/média); `.doc` permitido sem extrator dedicado;
  falha de extração → 400; parse LLM com `except` genérico → fallback determinístico.
- Sem rate limiting (grep slowapi zero); sem exception handler global; formatos de
  resposta inconsistentes (`{"status":"ok"}` vs listas nuas).
- `/health`+`/api/health`: SELECT 1 + redis ping; banco cai → HTTP 200
  `degraded` (`main.py:52-73`) — **200 com banco fora** engana monitor externo
  (média; healthcheck do compose sempre "healthy").
- `/api/agent/metrics` e `/dashboard` existem (`224-268`); `/metrics` Prometheus AUSENTE.

### 15. Frontend — IMPLEMENTADO E FUNCIONAL (com ressalvas de UX/erro)

- Rotas: `/` dashboard (onboarding se sem perfil), `/jobs` + `/jobs/[id]`,
  `/profile` (+upload), `/preferences`, `/notifications`, `/settings`
  (**órfã**: fora do `Nav.tsx`, só URL direta).
- `lib/api.ts:1-13`: base `NEXT_PUBLIC_API_URL` → hostname:8000 → 127.0.0.1:8000;
  **sem timeout/retry/AbortController**; único fallback 1 tentativa a proxy `/api/*`.
- **Todos os endpoints consumidos existem no backend** (cruzamento feito);
  backend nunca usado pela UI: `GET /runs`, `GET /metrics`, `POST /cleanup-expired`,
  `/weekly*`, `/webhook`, `/simulate` (oportunidade de observabilidade perdida).
- Loading/spinners e empty-states existem; **API offline vira `null/[]` silencioso**
  ("Ainda não encontramos vagas", zeros) — enganoso, sem banner offline (só
  `AgentControl.tsx:119-121` mostra erro). Baixa/média.
- UI envia quase todos os filtros da API (menos `company,area,offset`; `limit=200`
  fixo); abas favorites/ignored filtram client-side; **sem paginação por offset**.
- XSS: `dangerouslySetInnerHTML` **zero**; descrição como texto
  (`JobCard.tsx:238-240`). Sem auth (coerente com backend). Zero `ts-ignore`;
  `tsc` limpo (verificado). Sem testes (jest/vitest ausentes, `package.json` sem
  script test).

### 16. Notificações — IMPLEMENTADAS, SEM RETRY, SEM DUPLA-GARANTIA

- Telegram/Discord/SMTP implementados; despacho **após commit**, isolado por canal
  com try/except (`notifications.py:70-106`); `record_notification` commita por envio.
  **Falha no Telegram NÃO impede a vaga salva** (resposta à pergunta-chave: não).
- **Sem retry/backoff** em nenhum canal; timeout 15s cada. Token vazio checado
  (`telegram/client.py:85-88`); chat_id vazio → RuntimeError.
- Idempotência fraca: checa `was_already_notified(status='sent')` (`33-43`) mas
  **sem unique** no banco → check-then-insert com race (B-05). Teste `test_10`
  prova 10× idempotente com Telegram mockado (`call_count==1`) — em processo único.
- Celery dá retry 2× do **pipeline inteiro** (`tasks.py:6-13`), não do canal —
  reenvio em janela de crash pode duplicar (mesma race).
- Discord embeds e SMTP TLS implementados (lidos); teste live de envio **NÃO VALIDADO**
  (sem tokens neste ambiente). Telegram formata e escapa HTML (teste `test_full_qa:659-683`).
### 17. Segurança

| # | Achado | Arquivo:linha | Severidade |
|---|---|---|---|
| S-01 | CORS `allow_origin_regex=".*"` + `allow_credentials=True` + métodos/headers `*`, com **zero auth** em 30 endpoints (qualquer site controla o agente) | `main.py:43-49` | **CRÍTICA** |
| S-02 | Tokens SMTP/Telegram/Discord em texto claro no banco (`SearchPreferences`) e `.env`; sem log de secrets (grep zero) — risco é roubo de backup/banco, não vazamento em log | `entities.py:73-78`; `config.py:66-79` | Média |
| S-03 | Upload sanitiza só `/` (`..`, `\` passam); sem `StaticFiles` (PDFs **não** servidos via HTTP — mitiga) | `profile.py:67`; grep StaticFiles zero | Baixa/média |
| S-04 | `POST /api/telegram/simulate` aceita `chat_id` arbitrário e dá 500 se não-numérico; `/notifications/test` dispara envio real autenticado-por-nada (spam via CSRF se exposto) | `telegram.py:20-52`; `notifications.py:40-76` | Média (dado S-01) |
| S-05 | Containers rodam **root** (sem `USER`); backend `.dockerignore` não exclui `.env/hermes.db` (mitigado: `COPY app` só leva `app/`) | `backend/Dockerfile:1-20`; `.dockerignore` | Média/baixa |
| S-06 | Healthcheck do compose sem timeout (`urlopen` pode pendurar) | `docker-compose.yml:47-52` | Baixa |
| S-07 | SSRF: `check_url_liveness` (HEAD→GET, redirects, 5s, fail-open) existe mas **sem chamadores** — risco latente, não ativo; scrapers (indeed/cloak) fetcham URLs externas sem allowlist | `ghost_detector.py:61-81`; `indeed.py:183`; `cloak.py:28-41` | Baixa (latente) |
| — | SQL injection: só `SELECT 1`, `PRAGMA` e DDL com nomes fixos | `main.py:58`; `database.py:46-54` | OK |
| — | Secrets hardcoded: nenhum (`sk-/ghp_` zero); `.env` untracked + em `.gitignore` | git `ls-files` | OK |

### 18. Resiliência (cenários)

| Cen. | Comportamento atual | Risco | Esperado / correção |
|---|---|---|---|
| A 429 | `record_failure` (exceto indeed-RSS e greenhouse-!=200); breaker abre após 3 | Médio | Padronizar registro; retry com backoff+jitter antes de contar falha |
| B provider offline | `[]` + erro em `source_stats`; ciclo completa `partial_error`/`completed` | Baixo | OK; adicionar alerta após N ciclos falhos |
| C Postgres cai | Pipeline crash (SQLAlchemy levanta fora de try? `SessionLocal` em `run_search_sync` sem wrapping total); `/health` retorna **200 degraded** | Alto | `/health` → 503 quando `database=error`; retry de conexão; teste de boot sem banco |
| D Redis cai | Pipeline sobrevive (try/except); Celery morto; `/run` cai no fallback síncrono (trava HTTP) | Médio | Fila de fallback ou 429/503 explícito no `/run` sem broker |
| E Telegram cai | Exceção isolada por canal; vaga salva; sem retry = alerta perdido | Médio | Outbox ou retry com backoff + repositório de pendentes |
| F Discord 500 | Idem E | Médio | Idem E |
| G SMTP falha | Idem E | Médio | Idem E |
| H morte no meio do pipeline | Sem SearchRun (só no sucesso); jobs já commitados permanecem; notificações parciais sem registro de posição | Alto | SearchRun `running` no início + `finally` atualizando status; checkpoint por vaga |
| I 2 instâncias do backend | Overlap total (sem lock); duplicatas contidas por UNIQUE; notificações podem duplicar (B-05); DDL duplo no boot | Alto | Lock distribuído (redis `SET NX` / advisory lock PG) + `restart: unless-stopped` única réplica |
| J vaga em 3 providers | 1 linha + `alternative_sources`, sem re-notificar (verificado no código `415-419` + `was_already_notified`) | Baixo | OK |
| K muda salário | **Changelog duplicado todo ciclo** (B-01); valor novo nunca persistido | Alto | UPDATE + unique anti-duplicata |
| L vaga encerrada | Ghost detecta sinais/`closed`; purge remove (protege favoritos) | Baixo | OK |
| M API externa muda formato | `_parse_page` retorna `([],0)`; fonte fica "ok vazia" silenciosamente | Médio | Alerta quando fonte historicamente produtiva zera (`found==0` após N ciclos com `found>0`) |

### 19. Performance

- Fontes em paralelo (`asyncio.gather`) — bom; teto 8s/fonte.
- Por vaga: 1 fuzzy × 300 recentes + insert+flush+commit individual — teste de 500
  dedups <2s (`test_29`) sugere teto confortável até ~10k vagas/dia em SQLite local.
- **Paredes de escala:** `existing_urls/external_ids` O(N) em memória (`pipeline.py:298-299`)
  — 1M de vagas ≈ centenas de MB + GC; purge filtra `published_at` **sem índice**;
  `Notification` sem índice por job+channel; listagem sem `count` (bom p/ não travar).
  100k armazenadas: OK com folga; 1M: `existing_urls` vira o gargalo nº 1, seguido de
  fuzzy O(n×300) e purge full-scan.
- Celery `concurrency=2` no compose; `task_time_limit=600` (`celery_app.py`) —
  ciclo >10min morre no worker mas APScheduler embutido continuaria (duplo).
- Memória de descrições: `_clean_html` limita 2k chars; `resume_text` 20k — OK.

### 20. Observabilidade — PARCIAL

- Logs JSON em stdout (`{"event":...}`, `logging.py:12-18`); só nível info; `run_id`
  só quando o chamador passa (scheduler não passa — `scheduler.py:27,30`).
- `SearchRun` persiste found/valid/dedup/discarded/new/updated/notified/errors/
  `source_stats`/`discard_reasons` (agregados) — bom p/ telemetria de ciclo.
- `GET /api/agent/metrics|dashboard|runs` existem; `/metrics` Prometheus AUSENTE.
- **"Por que a vaga X não apareceu?" NÃO é respondível**: descartes não persistem por
  vaga (só contadores). Correção: tabela `discarded_jobs` (url_hash, reason, source,
  run_id, TTL curto) ou log estruturado por descarte com sampling.
- Health cobre backend/pg/redis no compose; frontend sem healthcheck.

### 21. Testes — BONS EM VOLUME, COM LACUNAS REAIS

- **98 passed / 10,97s**, 16 arquivos (33 no `test_full_qa_battery`). Todos mockados
  onde há rede (`patch httpx.AsyncClient.get`, `MockJobSource`, `TestClient`+sqlite) —
  **nenhum teste bate na internet** (determinístico, não-flaky). Qualidade real:
  idempotência 10× (`test_10`), threads 10× (`test_20`), determinismo 50×
  (`test_14`), carga 500 dedups (`test_29`), SQLi+XSS (`test_28`).
- **Sem teste:** Postgres; overlap de schedulers; notificações reais; `POST /resume`
  via HTTP; `POST /jobs/cleanup-expired`; `/reports/weekly`; double-run do pipeline
  contra mesmo banco (idempotência fim-a-fim); gupy/linkedin/vagas/indeed/glassdoor/
  remoteok/remotive/greenhouse/jobicy com fixtures gravadas (só mocks manuais);
  frontend (zero testes); `.env` de exemplo validado contra `config.py`.
- Deveriam existir: teste de ciclo-duplo (B-01/B-05 travariam), teste de vaga
  envenenada no meio do lote (B-02), teste de contrato frontend×backend (endpoints
  usados), teste de `compose config` + `Dockerfile` build no CI (CI AUSENTE —
  sem `.github/`).

### 22. Docker/DevOps — CONFIG VÁLIDA, PRODUÇÃO NÃO PROVADA

- `docker compose config` → exit 0 (verificado). Serviços: postgres:16-alpine,
  redis:7-alpine, backend, worker (`concurrency=2`), scheduler (beat), frontend.
- **Ausentes:** `restart:` em todos (24/7 sem auto-restart — B-20);
  `networks:` (usa default `hermes_default`, ok); resource limits; healthcheck de
  frontend/worker/scheduler; CI.
- Backend healthcheck `/health` sempre 200 mesmo degradado (S: C) — compose nunca
  marca unhealthy por banco fora.
- `./backend/app:/code/app:z` montado sobre a imagem em **produção** — rollback
  exige git, não só imagem; dev×prod divergem silenciosamente. Média.
- `DATABASE_URL`/`REDIS_URL` hardcoded `hermes/hermes@postgres|redis` no compose
  (`35-36,59-60,77-78`) — **`POSTGRES_*` do `.env` ignorados pelo backend**
  (só o serviço postgres os usa). Surpresa de configuração. Média.
- Frontend Dockerfile: sem lock no build (`COPY package.json` sem
  `package-lock.json` existente no repo — nondeterminístico); sem
  `output:standalone`; `NEXT_PUBLIC_API_URL` bakeado no `npm run build` mas
  injetado via ENV de runtime (troca exige rebuild). Sem `USER` (root).
- Backend Dockerfile: `python:3.12-slim` (confere com `.venv` local); `cloakbrowser
  install || true` silencioso = fallback pode não existir; sem `USER`.
- Scripts: `run_local.sh` mata portas com `fuser -k` (mata processo alheio),
  `sleep 2` sem healthcheck (frágil), mas com trap cleanup; `run_tests.sh` usa
  `backend/test.db` divergindo do Makefile (`/tmp/hermes_test.db`); `run_docker.sh`
  copia `.env.example` se faltar `.env` (comportamento correto).
- `BACKEND_PORT` só mapeia host (`compose:38`; interna fixa 8000);
  `COMPOSE_PROJECT_NAME` sem efeito (sem `name:`); `CORS_ORIGINS` ignorado
  (`main.py` usa regex `.*`).

### 23. Configuração

| Variável | Obrigatória | Default | Onde usada | Problema |
|---|---|---|---|---|
| DATABASE_URL | Não | sqlite ./hermes.db | config, compose (hardcoded pg p/ backend) | Compose ignora `.env` p/ backend |
| REDIS_URL | Não | localhost:6379 | config, celery, health | OK |
| BACKEND_PORT/FRONTEND_PORT | Não | 8000/3000 | só host-map compose | Interna backend fixa 8000 |
| CORS_ORIGINS | Não | localhost:3000 | **não consumida** (`main.py` usa `.*`) | Falsa sensação de restrição |
| ENVIRONMENT | Não | development | **não consumida** (grep zero) | Morta |
| ENABLE_BUILTIN_SCHEDULER | Não | true | lifespan | OK (cuidado c/ beat) |
| DEFAULT_SEARCH_FREQUENCY_MINUTES | Não | 60 | scheduler | OK |
| MAX_CONCURRENT_SOURCE_CRAWLS | Não | 4 | **não consumida** | Morta |
| JOB_SOURCES | Não | sem indeed/glassdoor/mock | factory+pipeline | OK; example inclui `mock` (diverge) |
| SOURCE_TIMEOUT/MAX_PAGES/RATE_DELAY | Não | 30/5/1.0 | timeout sim; **max_pages ignorado em 6 providers**; rate_delay só em alguns | Parcial |
| MOCK_JOBS_COUNT | Não | **0** (config) vs **10** (example) | factory (`>0`) | Divergência confusa |
| CLOAK_* | Não | true/true/45 | só indeed; cap 8s anula 45s | Parcial |
| MAX_JOB_AGE_DAYS | Não | 60 | pipeline+cleanup | OK |
| DEDUPLICATION_SIMILARITY_THRESHOLD | Não | 0.88 | **não lida** (hardcoded 0.88) | Morta (valor coincide) |
| MINIMUM_MATCH_SCORE | Não | 70 | só fallback; pipeline usa prefs | OK confuso |
| VERIFY_JOB_URL_HEALTH | Não | false | **sem chamadores** | Morta (bem que morta — SSRF) |
| CIRCUIT_* | Não | 3/300 | breaker | OK |
| MATCH_WEIGHT_* | Não | 25/30/15/10/10/10 | **ignorados** | Morta + README diverge |
| LLM_* | Não | vazio/gpt-4o-mini | resume parse (`get_llm_provider`) | OK (fallback determinístico) |
| TELEGRAM_/DISCORD_/SMTP_* | P/ alertas | vazios | clients | OK; sem validação de formato |
| NEXT_PUBLIC_API_URL | P/ front | localhost:8000 | build-time bake | Rebuild p/ trocar |
| POSTGRES_* | P/ compose | hermes | só serviço postgres | Ignorados pelo backend |
| COMPOSE_PROJECT_NAME | Não | hermes | nada (sem `name:`) | Morta |
| UPLOAD_DIR | Não | `<repo>/uploads` | `profile.py:13` via `os.environ` | **Não documentada** (ausente de config+example) |
### 24. Bugs Críticos

```
ID: B-01
Severidade: ALTA (corrupção progressiva de dados)
Arquivo: backend/app/services/pipeline.py:401-411 + change_detector.py:5-91
Problema: changelog inserido a cada ciclo para o mesmo diff; valores novos nunca
  gravados no Job (só last_checked_at/last_updated_at).
Como reproduzir: seed 1 vaga, rode run_search_sync 3× com a fonte retornando a
  mesma vaga com salário diferente do banco; conte JobChangelog por job (3 linhas).
Causa: falta de UPDATE + falta de checagem anti-duplicata.
Impacto: tabela cresce 1 linha/ciclo/vaga alterada; UI de changelog vira spam.
Correção: UPDATE dos campos no existing job + UniqueConstraint(job_id,field_name,
  new_value,created_date) ou checar último changelog igual antes de inserir.
Verificação: 2º ciclo consecutivo gera 0 changelogs novos.
```
```
ID: B-02
Severidade: ALTA (ciclo abortado + telemetria perdida)
Arquivo: backend/app/services/pipeline.py:348-512
Problema: loop por vaga sem try/except; exceção em 1 vaga pula SearchRun (524)
  e cai no finally que só limpa redis/fecha sessão.
Como reproduzir: injetar job com description=None que quebre _clean/rank no meio
  do lote (ou simular IntegrityError fora do flush tratado); observar ausência de
  SearchRun para o run_id logado no STARTED.
Causa: contenção só por fonte, não por item.
Impacto: ciclo parcial sem registro; "rodou mas não sei o que aconteceu".
Correção: try/except por vaga → errors[] + SearchRun parcial; SearchRun 'running'
  no início + finally atualizando status.
Verificação: ciclo com vaga envenenada completa com status partial_error e errors preenchido.
```
```
ID: B-03
Severidade: ALTA (alertas duplicados sob concorrência/crash)
Arquivo: backend/app/models/entities.py:165-176 + notifications.py:33-43
Problema: Notification sem UniqueConstraint(user_id,job_id,channel); idempotência
  é check-then-insert com race; retry 2× do pipeline inteiro (tasks.py:6-13)
  reexecuta envios.
Como reproduzir: 2 run_search_sync concorrentes com 1 vaga válida e Telegram
  mockado com delay; contar Notification sent (2 em vez de 1).
Causa: falta de constraint + lock.
Impacto: spam de alertas (o oposto da promessa "sem reenvio").
Correção: UniqueConstraint(user_id,job_id,channel,status?) + insert com
  tratamento de IntegrityError como "já enviado".
Verificação: teste de corrida resulta em 1 linha sent.
```
```
ID: B-04
Severidade: ALTA (ciclos sobrepostos; fura 24/7)
Arquivo: backend/app/services/scheduler.py + celery_app.py:11-16 +
  api/routes/agent.py:162-172 + docker-compose.yml:31-85
Problema: 3 executores (APScheduler embutido + Celery beat 300s + /run manual)
  sem lock distribuído; flag redis é só display.
Como reproduzir: compose up padrão + POST /api/agent/run durante ciclo agendado;
  observar 2 run_ids concorrentes nos logs.
Causa: guardas locais (memória) ou inexistentes.
Impacto: dobra carga nas fontes (rate-limit/ban), notificações duplicadas (B-03),
  writes concorrentes.
Correção: UM executor por deploy (ex: beat como padrão no compose +
  ENABLE_BUILTIN_SCHEDULER=false) + lock redis SET NX com TTL no início do ciclo.
Verificação: disparos simultâneos resultam em 1 ciclo + 1 skip logado.
```
```
ID: B-05
Severidade: CRÍTICA (segurança)
Arquivo: backend/app/main.py:43-49 (+ ausência total de auth)
Problema: CORS .* + credentials + 30 endpoints sem autenticação (inclui POST
  /run, /cleanup-expired, /notifications/test que envia mensagens reais).
Como reproduzir: hospedar página em origem qualquer chamando
  http://<host>:8000/api/agent/run com fetch credentials:include.
Causa: allow_origin_regex r".*" + allow_credentials True + design sem auth.
Impacto: CSRF/controle total por qualquer site visitado na mesma rede.
Correção: whitelist explícita (CORS_ORIGINS de verdade) + token admin via header
  (ex: AGENT_API_TOKEN) em endpoints mutáveis; documentar "não exponha :8000".
Verificação: request de origem não-listada sem token → 401/403.
```
```
ID: B-06
Severidade: ALTA (perda silenciosa)
Arquivo: backend/app/services/pipeline.py:515-518
Problema: commit de lote com except que dá rollback sem log nem errors[].
Como reproduzir: forçar falha no flush final (ex: constraint) e checar que
  stats.errors está vazio e nenhum log registra.
Causa: except genérico silencioso.
Impacto: perda de dados invisível à observabilidade.
Correção: logar exceção em errors[] + log_event("BATCH_COMMIT_ERROR").
```

### 25. Débito Técnico

**Crítico (impede 24/7 confiável):** B-01..B-06 acima.
**Alto:** breaker só-memória + tabela órfã (`circuit_breaker.py:6`); scheduler sem
catch-up/lock/jobstore; `existing_urls` O(N) em memória (`pipeline.py:298-299`);
gupy sem retry + flaky sob concorrência; `POSTGRES_*` ignorados pelo backend;
compose sem `restart:`; `/health` 200 com banco fora; `salary_score` fictício +
rótulo `recency` errado (`ranking.py:274`; `jobs.py:190`); pesos/MATCH_WEIGHT mortos
+ README divergente; `max_pages` ignorado em 6 providers.
**Médio:** dedup URL agressiva (`?id=` colide); hash `ext:{id}` sem source;
fuzzy só 300 recentes; threshold hardcoded; datas futuras com boost; mandatory só
em title+desc (ignora requirements); `excluded_keywords` por substring;
getonbrd N+1; glassdoor sem sleep; greenhouse/indeed sem `record_failure` em
ramos; Lever ausente; uploads sanitização parcial; simulate 500; formatos de erro
inconsistentes; frontend sem timeout/retry, offline silencioso, sem paginação
offset, endpoints úteis não consumidos (`/metrics`, `/runs`, `/weekly`);
`published_at` sem índice; `uuid` sem unique; `check_url_liveness` morto (manter
morto até endurecer SSRF); `filters.py` morto e divergente; `repositories` vazio;
`run_tests.sh` vs Makefile divergem no path do banco; frontend Dockerfile sem lock
+ `NEXT_PUBLIC` bakeado + root; backend root; healthcheck sem timeout; sem CI.
**Baixo:** pause só-flag; `PAGE_SIZE` declarada sem uso; `.doc` sem extrator;
reasoning truncado exclui recency; `COMPOSE_PROJECT_NAME` sem efeito; `settings/`
órfã no frontend; `MOCK_JOBS_COUNT` 0-vs-10 confuso; logs só-info sem níveis.

### 26. Pontos Fortes

- Pipeline real fim-a-fim com contenção por fonte + teto 8s (prova live: 108/0 erros).
- Honestidade de datas: `unknown_date` em todos os providers, sem invenção (raro e correto).
- Validação com motivos estáveis + evidência live de acerto nos descartes.
- Dedup com hash UNIQUE + IntegrityError como rede de segurança (correto o desenho em camadas).
- Notify após commit + isolamento por canal (falha de alerta não perde vaga).
- Testes com substância (idempotência 10×, threads, determinismo 50×, carga, SQLi/XSS) — acima da média de projetos do porte.
- Frontend sem `dangerouslySetInnerHTML`, `tsc` limpo, zero `ts-ignore`, estados de loading/vazio.
- Segredos: nenhum hardcoded; `.env` fora do git; sem SQLi; uploads fora do servido HTTP.
- Degradação graciosa sem Redis (health `offline`, pipeline segue).
- Docs extensas (mesmo com divergências, dão contexto real).

### 27. Matriz de Funcionalidades

| Funcionalidade | Estado | Evidência | Arquivo | Sev. |
|---|---|---|---|---|
| Coleta multi-fonte | OK (com fragilidades por fonte) | live 108, 0 erros | pipeline.py:313 | — |
| Gupy | FRÁGIL | flaky concorrência; sem retry/paginação | gupy.py:116-214 | Alta |
| LinkedIn | FRÁGIL | live 7; sem offset; employment fixo | linkedin.py:82-86,167 | Média |
| RemoteOK/Remotive/WWR/Jobicy | FRÁGIL | live OK; sem retry/backoff | respectivos | Média |
| Vagas/CIEE/GetOnBrd | FRÁGIL | código real; live 0 itens (causa aberta) | vagas.py; ciee.py; getonbrd.py | Alta |
| Greenhouse | PARCIAL | só Greenhouse; Lever ausente | greenhouse_lever.py | Baixa |
| Glassdoor | NÃO VALIDADO | nunca executado; fora do default | glassdoor.py | Média |
| Indeed | QUEBRADO | RSS extinto; cloak ausente; off default | indeed.py:41-190 | Baixa |
| Mock | MOCK | determinístico; filtrado depois | mock.py; validation.py:112 | — |
| Normalização | PARCIAL | seniority `""` em 8/12; employment hardcoded aqui/ali | providers | Média |
| Ghost detection | OK | unknown_date; purge dupla; prova live | ghost_detector.py; cleanup.py | — |
| Deduplicação | PARCIAL | camadas OK; FP/FN + threshold hardcoded | dedup.py; pipeline.py:390 | Alta |
| Validação | OK | motivos estáveis; acerto live | validation.py:84-238 | — |
| Ranking | FRÁGIL | matemática OK; pesos mortos; doc diverge; salary fictício | ranking.py:227-274 | Alta |
| Change detection | QUEBRADO | duplica por ciclo (B-01) | change_detector.py; pipeline.py:401 | Alta |
| Persistência | OK | UNIQUE+orphan-cascade; sem upsert | entities.py; pipeline.py:472 | — |
| Notificações TG/Discord/SMTP | PARCIAL | enviam; sem retry; sem unique (B-03) | notifications.py | Alta |
| API (30 endpoints) | OK | todos implementados; sem auth (B-05) | api/routes/ | Crítica |
| Dashboard | OK | 7 rotas; contratos conferem; offline silencioso | frontend/app | Média |
| Scheduler 24/7 | FRÁGIL | agenda; sem lock/catch-up; triplo executor | scheduler.py; celery_app.py | Alta |
| Circuit breaker | FRÁGIL | transições OK; só-memória; furos | circuit_breaker.py | Alta |
| Workers Celery | PARCIAL | tasks+beat OK; duplica c/ embutido | workers/ | Alta |
| Observabilidade | PARCIAL | logs+SearchRun agregados; sem per-vaga | logging.py; agent.py:224 | Média |
| Testes | OK | 98 pass; lacunas reais (PG, corrida, e2e) | backend/tests/ | Média |
| Docker/Compose | PARCIAL | config válida; up NÃO VALIDADO; sem restart | docker-compose.yml | Alta |
| Segurança | FRÁGIL | S-01..S-07; sem secrets hardcoded | main.py:43-49 | Crítica |
| CI/CD | AUSENTE | sem `.github/` | — | Média |

### 28. Plano de Correção Priorizado

**FASE 0 — Impeditivos:** B-05 (CORS+auth; `main.py`, risco: baixo p/ localhost,
conclusão: origem estranha bloqueada sem token); B-02 (try por vaga + SearchRun
running/finally; `pipeline.py`, risco: médio; conclusão: ciclo envenenado →
`partial_error` registrado); B-06 (log no batch rollback).
**FASE 1 — Integridade:** B-01 (UPDATE+unique changelog); B-03 (unique
Notification + IntegrityError-como-enviado); lock de ciclo (redis SET NX;
`pipeline.py`+`scheduler.py`+`tasks.py`); teste de ciclo-duplo e de corrida.
**FASE 2 — Providers:** retry por termo no Gupy + paginação (`offset`) e remoção
do flaky (conclusão: 2 runs seguidos com `found>0`); investigar vagas/ciee/
getonbrd/greenhouse zeradas (fixtures gravadas por fonte); `record_failure` no
indeed-RSS e greenhouse-!=200; sleep no glassdoor; decidir Lever (implementar ou
renomear); documentar indeed desativado.
**FASE 3 — Core:** usar `settings` de pesos/threshold no ranking/dedup + corrigir
README; `salary_score` real ou removido; rótulo `recency` (`jobs.py:190`); hash com
source; `mandatory_keywords` incluindo requirements; `published_at` indexado.
**FASE 4 — Scheduler:** UM executor no compose (beat; `ENABLE_BUILTIN_SCHEDULER=false`
no `.env` docker) + catch-up documentado (sem catch-up automático; status mostra
"último ciclo há X"); `max_instances=1`+`coalesce`+`misfire_grace_time`+timezone.
**FASE 5 — Notifications:** retry com backoff + outbox/pendentes; teste e2e com
canal mockado com falha 1× (conclusão: 1 envio após retry, 0 duplicatas).
**FASE 6 — API:** rate limit em `/run|/test|/simulate`; `/health` 503 sem banco;
`total` na listagem; handler global de erros com formato único; validar `chat_id`.
**FASE 7 — Frontend:** timeout+retry no `api.ts`; banner offline; consumir
`/metrics`+`/runs` (observabilidade) ou remover rotas órfãs (`/settings` no Nav);
paginação por offset.
**FASE 8 — Observabilidade:** tabela/log de descartes por vaga (com TTL);
`run_id` em todos os eventos; alerta "fonte produtiva zerou".
**FASE 9 — Testes:** ciclo-duplo, corrida de notify, vaga envenenada, contrato
front×back, fixtures por provider, job de CI (`pytest`+`tsc`+`compose config`).
**FASE 10 — Produção:** `restart: unless-stopped`; HEALTHCHECK com timeout;
`USER` não-root; lock de build do front + `output:standalone`; alinha
`POSTGRES_*` com `DATABASE_URL`; backup do volume pg; `compose up` filmado
(logs backend+1 ciclo) como prova; runbook (o que fazer se: banco cai, redis cai,
fonte zera, spam de alerta).

### 29. Checklist de Produção

- [ ] B-01..B-06 corrigidos com testes que falhariam antes
- [ ] 1 executor de ciclo + lock; overlap impossível por construção
- [ ] CORS whitelist + token em mutáveis; `:8000` nunca exposto sem proxy auth
- [ ] `restart: unless-stopped` em todos; `/health` 503 sem banco
- [ ] Backup `postgres-data` + restore testado; `uploads-data` dimensionado
- [ ] `docker compose up --build` executado limpo + 1 ciclo `completed` logado
- [ ] CI verde (pytest+tsc+compose config) na `dev`; merge p/ `main` só com aprovação
- [ ] Alertas deobservabilidade: fonte zerada, ciclo `partial_error`, breaker OPEN
- [ ] `.env` de produção preenchido (tokens) fora do git; `POSTGRES_*` alinhados
- [ ] Runbook + "por que a vaga X não apareceu" respondível em <5min

### 30. Conclusão Técnica

O Argos **não é vaporware**: coleta, filtra, deduplica, ranqueia, persiste e serve —
tudo comprovado em execução, com 98 testes e frontend funcionais. Mas **não é
confiável em produção**: corrupção progressiva (B-01), ciclos abortáveis sem rastro
(B-02), duplicatas de alerta sob corrida (B-03), executores sobrepostos (B-04),
API aberta ao mundo (B-05) e perdas silenciosas (B-06) impedem o 24/7 prometido.
O caminho é o Plano de Correção (Fases 0–2 destravam confiabilidade; 3–10, produção).
Esforço estimado: Fases 0–1 em dias; 2–4 em 1–2 semanas; restante incremental.

## TOP 20 AÇÕES PARA TORNAR O ARGOS CONFIÁVEL EM PRODUÇÃO

1. Fechar CORS + exigir token em endpoints mutáveis (`main.py:43-49`). 
2. Try/except por vaga + SearchRun `running`→final (`pipeline.py:348-542`).
3. Unique `(user_id,job_id,channel)` em Notification + tratar IntegrityError (B-03).
4. UPDATE do job + anti-duplicata em changelog (B-01).
5. Um executor de ciclo + lock redis SET NX (B-04).
6. Logar rollback do commit em lote (B-06).
7. Retry por termo + paginação no Gupy; investigar fontes zeradas (vagas/ciee/getonbrd/greenhouse).
8. Persistir circuit breaker em `CircuitBreakerRecord` (tabela já existe, órfã).
9. `restart: unless-stopped` + `/health` 503 sem banco + HEALTHCHECK com timeout.
10. Usar `MATCH_WEIGHT_*`/`DEDUP_THRESHOLD` do env no código e corrigir o README (25/30/15… é falso).
11. `salary_score` real ou removido; corrigir rótulo `recency` (`jobs.py:190`).
12. Hash com source (`ext:{source}:{id}`) + revisar strip total de query em URLs.
13. `existing_urls` paginado/streaming (não carregar 1M de strings).
14. Tabela/log de descartes por vaga (TTL) — "por que não apareceu" respondível.
15. Retry com backoff nas 3 notificações + outbox de pendentes.
16. Rate limit em `/run|/test|/simulate` + handler global de erros + `total` na listagem.
17. Alinhar `POSTGRES_*` com `DATABASE_URL`; `USER` não-root; front standalone + lock.
18. CI mínima (pytest + tsc + compose config) — hoje inexistente.
19. Testes: ciclo-duplo, corrida de notify, vaga envenenada, contrato front×back, fixtures por provider.
20. `docker compose up` completo filmado + runbook + merge `dev`→`main` com aprovação do dono.
