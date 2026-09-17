# DESIGN.md — Hermes Job Hunter 2.0

## Conceito: "mesa do correspondente"
O Hermes é um correspondente de empregos meticuloso, não um dashboard.
Linguagem visual de **livro-caixa editorial**: fileiras pautadas (ledger),
tipografia serifada para voz humana, um único sinal âmbar para o que importa.

## Tipografia (com justificativa)
- **Fraunces** (display, títulos de vaga e da página): serifada editorial com
  personalidade; transmite curadoria humana e confiança — como a manchete de
  um caderno de empregos. Suporta acentos PT.
- **Archivo** (UI/corpo): grotesca funcional, distinta de Inter/Roboto/SF;
  numerais tabulares para compatibilidade e salários.
- Escala: título de página 24 serif 600 · título de vaga 17–19 serif 600 ·
  corpo 14 · auxiliar 12–13 (mínimo 12, contraste ≥ 7:1).
- Sem uppercase decorativo: labels em sentence case, 12px semibold.

## Cor (sinal único)
- Base carvão `#0d0f13`, hairline `#232833`, relevo `#14171d` (só sheets).
- Texto `#edeef0`, secundário `#a7aeb9`.
- **Âmbar `#f59e0b` = atenção**: numeral de match alto, CTA primário, ativo.
  Nada mais usa âmbar como decoração.
- Verde só no ponto de status e em feedback de ação concluída. Sem pills
  verde-água por toda parte. Sem gradiente, sem glow, sem glass.

## Composição
- Ledger rows com hairlines, sem grade de cards. Uma informação não precisa
  de borda + fundo para existir.
- Hierarquia do Job: cargo (serif) → empresa · local · modalidade (quieto) →
  numeral de compatibilidade → 1 motivo → salário discreto → 1 CTA.
- Metadados secundários (fonte, data) em texto quieto, nunca badges.
- Zero emoji na UI. Setas tipográficas (→ ↗ ←) e ★/☆ em texto puro.
- Raio: 10px sheets/inputs, 8px botões. Sem pill para cada dado.

## Motion
Só transição de estado: hover/fade 150ms ease-out, spinner existente,
indeterminado honesto (sem % fake). Sem bounce, sem flutuação.

## Microcopy (humano, PT)
- "Candidatar-se ↗" · "Ver análise →" · "Salvar" / "Salva"
- "De olho em N plataformas · verificado às HH:MM"
- "N novas desde ontem"? (sem dado — não usar)
- Técnico escondido: "Verificação e plataformas" colapsável no Início.
- Nunca: engine, pipeline, crawler, .env, match score como jargão.

## Mobile
Nav textual compacta com scroll horizontal. Ledger empilha: numeral de match
na linha do título, CTA em largura total. Nada de scroll horizontal de conteúdo.
