# Hermes Job Hunter

Um agente de IA que roda continuamente em Docker, monitora fontes de vagas e envia para o usuário apenas as oportunidades que correspondem ao seu perfil e aos seus filtros.

O objetivo é eliminar a necessidade de ficar entrando diariamente em LinkedIn, Indeed, Gupy, Wellfound e outros sites procurando vagas.

## Como funciona

### 1. Criar o perfil

O usuário fornece:

* Currículo
* Cargo(s) desejado(s)
* Senioridade:

  * Júnior
  * Pleno
  * Sênior
* Skills e tecnologias
* Experiências profissionais
* Localização
* Regiões de interesse
* Modelo de trabalho:

  * Remoto
  * Híbrido
  * Presencial
* Tipo de contrato
* Pretensão salarial
* Idiomas
* Empresas de interesse

O Hermes transforma essas informações em um perfil estruturado para fazer o matching das vagas.

### 2. Configurar os filtros

O usuário pode definir regras como:

```text
Cargo:
Backend Developer
Python Developer
Software Engineer

Senioridade:
Júnior / Pleno

Localização:
Brasil

Modelo:
Remoto
Híbrido

Salário mínimo:
R$ 6.000

Tecnologias:
Python
FastAPI
Django
Docker
PostgreSQL

Excluir:
Estágio
Presencial
PJ
```

Os filtros podem ser alterados a qualquer momento.

### 3. Pesquisa contínua

O Hermes roda em intervalos configuráveis:

```text
A cada 15 minutos
A cada 30 minutos
A cada 1 hora
A cada 3 horas
```

Ele consulta as fontes configuradas, coleta novas vagas e normaliza os dados.

### 4. Inteligência de matching

A IA analisa cada vaga encontrada e compara com o perfil do usuário.

Exemplo:

```text
Backend Developer — Empresa X

Match: 94%

✓ Python
✓ FastAPI
✓ PostgreSQL
✓ Docker
✓ Pleno
✓ Remoto

⚠ AWS — desejável, mas não obrigatório

Localização:
Remoto — Brasil

Salário:
R$ 8.000 — R$ 11.000
```

Apenas vagas que ultrapassarem o score mínimo configurado são enviadas.

### 5. Entrega das vagas

O usuário escolhe como quer receber:

**Telegram**

```text
🚨 NOVA VAGA — 94% MATCH

Backend Developer
🏢 Empresa X
🌎 Remoto
💼 Pleno
💰 R$ 8k–11k

Skills:
Python • FastAPI • PostgreSQL • Docker

Por que combina:
✓ 4/4 skills principais
✓ Senioridade compatível
✓ Trabalho remoto
✓ Faixa salarial compatível

🔗 Ver vaga
```

Ou:

**E-mail**

O Hermes envia um resumo periódico, por exemplo:

> 7 novas vagas encontradas nas últimas 3 horas.

Com as vagas organizadas por relevância.

---

# Dashboard

O frontend serve para configurar e acompanhar o sistema.

### Dashboard

* Vagas encontradas
* Vagas filtradas
* Vagas enviadas
* Melhor match do dia
* Fontes monitoradas
* Última execução do agente

### Vagas

Lista de todas as vagas encontradas:

```text
94%  Backend Developer
91%  Python Developer
88%  Software Engineer
84%  DevOps Engineer
```

Com filtros e busca.

### Perfil

Visualização e edição do perfil profissional extraído do currículo.

### Preferências

Configuração dos filtros de busca e das notificações.

### Notificações

Configuração:

```text
☑ Telegram
☑ E-mail

Frequência:
○ Imediatamente
● A cada 1 hora
○ Resumo diário

Enviar somente:
Score >= 80%
```

---

# Arquitetura

```text
                    ┌──────────────┐
                    │   Frontend   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   FastAPI    │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Postgres │ │  Redis   │ │ Scheduler│
        └──────────┘ └──────────┘ └────┬─────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │ Hermes Agent │
                                └──────┬───────┘
                                       │
                         ┌─────────────┼─────────────┐
                         ▼             ▼             ▼
                    Job Sources    Job Parser    Matcher
                         │             │             │
                         └─────────────┼─────────────┘
                                       ▼
                                ┌──────────────┐
                                │ Notification │
                                └──────┬───────┘
                                       │
                              ┌────────┴────────┐
                              ▼                 ▼
                          Telegram           E-mail
```

## Princípio do produto

**O Hermes procura. A IA filtra e entende. O usuário recebe.**

Ele não precisa se candidatar automaticamente, preencher formulários ou tomar decisões pelo usuário.

A função principal é ser um **radar pessoal de oportunidades**, funcionando 24/7 e reduzindo centenas de vagas encontradas para algumas oportunidades realmente relevantes.

