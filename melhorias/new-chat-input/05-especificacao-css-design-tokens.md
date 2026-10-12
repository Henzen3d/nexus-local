# 🎨 05 - Especificação de CSS, Tokens e Espaçamentos
**Multi+ (NexusLocal) — Design System Vanilla CSS Pixel-Perfect**

Este documento define os valores exatos de dimensionamento, espaçamento, tipografia, tokens de cor e micro-transições para o redesign do chat input, assegurando conformidade estrita com o arquivo de regras operacionais `AGENTS.md` (Vanilla CSS puro, Design Tokens existentes, Dark & Light modes).

---

## 📏 Tabela Unificada de Medidas e Espaçamentos

| Elemento Visual | Valor Unificado no Plano | Racional de Engenharia |
| :--- | :--- | :--- |
| **Altura em Repouso (Chat Ativo)** | **`44px`** | Altura compacta unificada de linha única (~50% menor que o composer atual). |
| **Altura da Linha de Digitação** | **`32px`** (textarea min-height `24px`, line-height `22px`) | Proporção ideal para leitura e alinhamento vertical com botões. |
| **Teto de Auto-Expansão** | **`200px`** (unificado) | Ponto de corte para ativação de scrollbar vertical sutil. |
| **Raio de Borda do Input** | **`20px`** no compacto / **`24px`** no empty state | Curvatura orgânica padrão de prompts modernos. |
| **Padding Externo do Card Compacto** | **`5px 8px`** | Margens internas que garantem respiro aos controles. |
| **Tamanho Visual dos Botões (`+`, Enter, Voz)** | **`32px × 32px`** (Desktop) | Dimensão compacta e simétrica (ícones em 16px). |
| **Área de Toque Mínima (Mobile)** | **`44px × 44px`** (`touch-target`) | Conforme normas WCAG / Apple HIG para telas de toque. |
| **Altura do Pill de Modelo no Rodapé** | **`26px - 28px`** | Discreto, perfeitamente alinhado à linha de base do disclaimer. |
| **Largura dos Balões Popover** | **`260px`** (Menu `+`) / **`320px`** (Menu Modelos) | Larguras adequadas para evitar truncamento de nomes. |

---

## 🎨 Tokens de Design Existentes e Aliases Semânticos

O plano prioriza os tokens já consolidados em `index.css`:

```css
/* Tokens oficiais do Multi+ reaproveitados */
var(--surface-card)         /* Fundo do composer no tema claro */
var(--surface-dark-elevated)/* Fundo do composer e popovers no tema escuro */
var(--hairline)             /* Borda sutil padrão */
var(--ink)                  /* Cor principal do texto e ícones */
var(--muted)                /* Cor secundária de ícones em repouso */
var(--muted-soft)           /* Cor do disclaimer e rótulos auxiliares */
var(--primary)              /* Cor terracota do botão de envio e seleções */
var(--surface-cream-strong) /* Hover suave de botões */
```

---

## 🧩 Regras de CSS da Estrutura Compacta (JSX Corrigido)

```css
/* 1. O Card Principal (Preserva empilhamento vertical de anexos) */
.input-card.compact-mode {
  padding: 5px 8px;
  border-radius: var(--radius-prompt, 20px);
  background: var(--surface-card);
  border: 1px solid var(--hairline);
  box-shadow: var(--shadow-soft);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

html[data-theme="dark"] .input-card.compact-mode {
  background: var(--surface-dark-elevated, #1e1e1c);
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow: none;
}

/* 2. A Linha Inline Unificada (Botão + | Textarea | Ações) */
.composer-single-line-row {
  display: flex;
  align-items: center;
  min-height: 32px;
  gap: 6px;
  width: 100%;
}

/* 3. Textarea Inline */
.composer-textarea-inline {
  flex: 1;
  min-height: 24px;
  max-height: 200px;
  padding: 4px 6px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 15px;
  line-height: 22px;
  font-family: var(--font-body);
  color: var(--ink);
  resize: none;
  overflow-y: hidden;
}

.composer-textarea-inline.is-multiline {
  overflow-y: auto;
  scrollbar-width: thin;
}

/* 4. Botão Enter (Opção A — Glifo ↵) */
.btn-send-enter {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--surface-cream-strong);
  border: 1px solid var(--hairline);
  color: var(--ink);
  cursor: pointer;
  transition: background 0.15s ease, transform 0.1s ease;
}

.btn-send-enter:hover:not(:disabled) {
  background: var(--primary);
  color: var(--on-primary, #ffffff);
  border-color: var(--primary);
  transform: translateY(-1px);
}

/* 5. Rodapé Externo Unificado */
.input-footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 4px 0;
  gap: 12px;
}

.input-footer-disclaimer {
  font-size: 11.5px;
  color: var(--muted-soft);
  line-height: 1.3;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.input-footer-model {
  flex-shrink: 0;
}
```

---

## ⚡ Micro-Transições e Animações

```css
/* Transição suave entre Voz e Enter */
.action-transition-slot {
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-swap-fade {
  animation: actionSwapFadeIn 0.16s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes actionSwapFadeIn {
  from { opacity: 0; transform: scale(0.92); }
  to { opacity: 1; transform: scale(1); }
}
```

---

## 📱 Alvos de Toque no Mobile (< 768px)

```css
@media (max-width: 768px) {
  .touch-target {
    position: relative;
  }
  .touch-target::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    min-width: 44px;
    min-height: 44px;
    width: 100%;
    height: 100%;
  }
}
```
