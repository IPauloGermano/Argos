# PRODUCT.md — Hermes Job Hunter 2.0

## O que é
Assistente pessoal de busca de empregos. O Hermes monitora plataformas de vagas,
compara oportunidades com o perfil do usuário e apresenta as que merecem atenção.

## Princípio
**O Hermes procura. O usuário decide.** Nada de candidatura automática.

## Para quem
Candidatos (foco atual: devs BR, júnior→sênior, remoto/híbrido) que não querem
varrer sites de vagas todo dia.

## O que o usuário quer (e a UI deve responder)
1. "Quais vagas valem minha atenção agora?" → Home e Vagas
2. "Por que esta vaga combina comigo?" → análise por vaga
3. "Como me candidato rápido?" → link direto para a fonte (1 CTA claro)
4. "Avisem-me das novas" → Alertas (Telegram/Discord)
5. "O que o Hermes sabe sobre mim?" → Perfil + Preferências

## O que o usuário NÃO quer ver
crawler, scraping, circuit breaker, deduplicação, pipeline, engines,
"jobs processados", métricas internas, .env, match score como jargão.
Técnica aparece só onde ajuda: "última verificação", "plataformas de olho".

## Mapa atual
- `/` Início — estado + melhores vagas + controle do monitoramento
- `/jobs` Vagas — catálogo com busca e filtros
- `/jobs/[id]` — análise da vaga + candidatura
- `/profile` — Sobre mim + O que procuro (abas)
- `/preferences` — regras avançadas (keywords, empresas, plataformas)
- `/notifications` — Alertas: canais + teste + histórico
- `/settings` — Conta + credenciais de entrega (Telegram/Discord)
- Onboarding em 3 passos no primeiro acesso

## Fontes de verdade (não expor como jargão)
Backend expõe `sources`, `last_search`, `next_search`, `frequency_minutes`,
scores e reasoning por vaga. Frontend traduz para linguagem humana.
