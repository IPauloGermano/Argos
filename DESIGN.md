---
name: hermes-design-system
version: 2.0.0
colors:
  surface-canvas: "#0e1015"
  surface-panel: "#151820"
  surface-elevated: "#1c202b"
  surface-interactive: "#232836"
  surface-border: "#282d3c"
  surface-border-subtle: "#1f2330"
  text-primary: "#f3f4f6"
  text-secondary: "#9ca3af"
  text-muted: "#6b7280"
  accent-amber: "#f59e0b"
  accent-amber-hover: "#d97706"
  accent-amber-subtle: "rgba(245, 158, 11, 0.12)"
  accent-match: "#10b981"
  accent-match-subtle: "rgba(16, 185, 129, 0.12)"
  danger-subtle: "rgba(244, 63, 94, 0.12)"
  danger: "#f43f5e"
typography:
  display: "Cinzel, Georgia, serif"
  editorial: "Fraunces, 'Times New Roman', serif"
  sans: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
  mono: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
---

# Design System — Argos Job Hunter 2.0

<!-- impeccable:design-schema 1 -->

## Creative North Star: "O Vigia Criterioso" (The Discerning Watchman)

O Argos Job Hunter 2.0 não é um painel de DevOps nem um clone de SaaS corporativo com estética "AI neon". Ele é um **concierge de carreira pessoal, calmo e criterioso**. Ele herda a sobriedade e a autoridade de uma publicação editorial nobre (como The Economist ou Financial Times), combinada com a agilidade de um instrumento pessoal de produtividade.

---

## 1. Princípios Fundamentais de Design

1. **Escaneabilidade Editorial sobre Empilhamento de Cards:**
   - Evitar o vício de IA de transformar cada elemento em um card com borda e sombra.
   - Usar espaçamento vertical, linhas finas de corte (`1px`), peso tipográfico e contraste de tom para agrupar informações.
2. **Zero "AI Purple" e Zero Efeitos Cosméticos:**
   - Eliminar gradientes roxo-para-azul, neons, texturas glassmorphic gratuitas e sombras coloridas sem fonte de luz.
   - A paleta é ancorada em carvão mineral e grafite quente (`#0e1015`, `#151820`), com destaque para o **Âmbar Dourado** (`#f59e0b`) e **Verde Folha** (`#10b981`) para compatibilidade real.
3. **Candidatura como Ação Soberana:**
   - O botão `Candidatar-se na fonte ↗` é o elemento de maior peso visual na tela. Ele não disputa atenção com 6 botões secundários.
4. **Tipografia com Propósito:**
   - Títulos e grandes seções usam voz editorial distinta com ritmo humano.
   - O corpo do texto respeita o chão estrito de legibilidade do Impeccable (mínimo de 13px para metadados e 15px para descrições, nunca textos de 10px ou 11px).
5. **Microcopy Confiável e Humana:**
   - Falar como um consultor humano que revisou o mercado para você hoje, nunca como um robô que expõe seus circuitos internos.

---

## 2. Paleta de Cores e Superfícies

* **Tela de Fundo (Canvas):** `#0e1015` — Carvão mineral profundo, acolhedor e sereno.
* **Superfície dos Blocos (Panels):** `#151820` — Grafite com borda fina `#282d3c` (1px).
* **Superfície Elevada / Hover:** `#1c202b` — Contraste sutil e natural ao focar ou passar o mouse.
* **Acentuação Principal (Âmbar Argos):** `#f59e0b` / hover `#d97706` — Calor, inteligência e claridade.
* **Compatibilidade (Match Verde):** `#10b981` — Usado exclusivamente para pontuações de aderência e verificações.
* **Texto Primário:** `#f3f4f6` — Branco quente, alto contraste sem queimar os olhos.
* **Texto Secundário:** `#9ca3af` — Legível, tom quente neutro (contraste $\ge 4.5:1$).
* **Bordas:** `#282d3c` — Sutis, precisas, delimitam sem sufocar.

---

## 3. Tipografia & Escala de Leitura

* **Piso de Legibilidade (Impeccable Rule):** Nenhum texto funcional de interface pode ter menos de 12px. Metadados e badges usam 12px/13px. Títulos usam 18px a 24px.
* **Tratamento de Overflow:** Títulos de vagas devem permitir quebra de linha natural (`break-words`, `line-clamp-2`), nunca cortando com `truncate` rígido que oculte o cargo do candidato.

---

## 4. Anatomia do Job Card Reformulado

```
┌──────────────────────────────────────────────────────────────────┐
│ Senior Backend Developer (Python & FastAPI)          [ 94% Match ]│
│ GitLab  ·  Remoto (Brasil)                                       │
│                                                                  │
│ 💰 R$ 18.000 - 24.000   ·   Publicada há 2 dias                  │
│                                                                  │
│ 💡 Por que combina com você:                                     │
│    Requer Python sênior, FastAPI e vivência com microsserviços.  │
│                                                                  │
│ [ ⭐ Salvar ]  [ 👍 ] [ 👎 ]       [ Candidatar-se na fonte ↗ ]   │
└──────────────────────────────────────────────────────────────────┘
```

- Sem badges de arco-íris competindo entre si.
- Compatibilidade destacada no canto superior direito de forma límpida.
- Justificativa evidente que responde em 2 segundos "por que devo abrir esta vaga?".
- Ação de candidatura como CTA primário inconfundível.

---

## 5. Do's and Don'ts

| O que Fazer (Do) | O que Nunca Fazer (Don't) |
| :--- | :--- |
| Usar espaço e divisores finos para organizar | Não empilhar cards dentro de cards |
| Usar no máximo 2 destaques de cor por elemento | Não encher o card com 6 badges de cores saturadas |
| Botões com altura mínima de 44px para toque | Não criar botões minúsculos ou textos de 10px |
| Títulos com quebra de linha legível | Não usar `truncate` que oculte metade do nome da vaga |
| Microcopy humana ("Vagas compatíveis hoje") | Não usar termos de crawler ("Deduplicação", "Circuit Breakers") |
| Animações curtas apenas em transições de estado | Não usar bounce, pulse constante ou efeitos de neon |
