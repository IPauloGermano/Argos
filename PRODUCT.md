# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Candidatos e profissionais de tecnologia (desenvolvedores backend, frontend, fullstack, engenheiros de software, analistas de dados e estagiários) que buscam oportunidades profissionais reais, qualificadas e com alta aderência, sem o cansaço mental de vasculhar manualmente dezenas de plataformas de recrutamento.

## Product Purpose

O Argos Job Hunter 2.0 é um assistente pessoal contínuo de carreira que monitora em tempo real portais de vagas (LinkedIn, Gupy, Greenhouse, Remotive, Vagas, CIEE, Indeed), filtra ruído e vagas fantasmas, deduplica anúncios entre plataformas e apresenta com clareza as oportunidades que realmente justificam a atenção e candidatura do usuário.

## Positioning

Diferente de agregadores genéricos de emprego ou painéis de controle de engenharia, o Argos se posiciona como um assistente de confiança: ele compreende o histórico e os anseios do candidato, detalha em linguagem humana os motivos de aderência técnica ("Combina com seu perfil porque pede Python e Docker"), fornece atalho direto para candidatura na fonte oficial e calibra seu algoritmo com base nos feedbacks do usuário.

## Operating Context

O candidato interage com o Argos pelo navegador (em desktop no setup de trabalho ou no celular em trânsito) para verificar novas oportunidades descobertas, analisar requisitos essenciais, salvar vagas em favoritos e receber alertas no Telegram ou Discord. A experiência deve ser silenciosa, límpida, de alta legibilidade e sem distrações mecânicas.

## Capabilities and Constraints

- Monitoramento em segundo plano sem necessidade de intervenção constante;
- Deduplicação canônica de vagas idênticas publicadas em portais diferentes;
- Filtragem ativa de vagas antigas (> 60 dias) e processos seletivos já encerrados;
- Ranqueamento determinístico em 5 pilares com justificativas legíveis;
- Ingestão e extração determinística de currículos (PDF, DOCX, TXT);
- Gestão de favoritos e ajuste de recomendações via 👍 / 👎;
- Integração com Telegram e Discord com garantia de não duplicação de alertas;
- Restrição inviolável: Preservação de todos os contratos de API REST existentes e compatibilidade total com o backend FastAPI.

## Brand Commitments

- **Nome:** Argos Job Hunter 2.0 — O radar atento e incansável de oportunidades de carreira.
- **Tom de voz:** Objetivo, profissional, empático, sofisticado e transparente.
- **Identidade:** Visual autoral e editorial. Rejeição explícita da estética clichê de IA ("AI slop": gradientes neon roxos/azuis, badges de arco-íris, cards dentro de cards, glow artificial, texto cinza ilegível e métricas de infraestrutura desnecessárias).

## Product Principles

1. **Candidato no centro:** A interface serve para encontrar emprego e facilitar a candidatura, nunca para exibir a complexidade do crawler.
2. **Escaneabilidade editorial:** Tipografia intencional e espaço negativo estruturam a leitura com hierarquia imediata.
3. **Candidatura como destino:** O botão "Candidatar-se na fonte ↗" é a ação principal evidente e desimpedida.
4. **Calma e honestidade:** Sem animações falsas ou status cosméticos; o produto reflete a realidade do mercado com serenidade.
5. **Universalidade e acessibilidade:** Conformidade WCAG 2.1 AA, alvos de toque confortáveis e contraste legível sob qualquer luminosidade.

## Accessibility & Inclusion

WCAG 2.1 AA: contraste de texto $\ge$ 4.5:1, piso de legibilidade de 12px para texto funcional, navegação completa por teclado com anel de foco destacado, suporte semântico para leitores de tela (`aria-label`, `<article>`, `<main>`) e targets de toque $\ge$ 44px em mobile.
