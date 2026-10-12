# 03 — Interface no cockpit

**Multi+ / NexusLocal** · Plano, não implementação

## Referências visuais

- **`melhorias/esforco-reasoning/tela-inicial-digitacao-select-model.png`**: Demonstração da caixa de digitação (`MessageInput.tsx`) e cockpit fechado/aberto:
  - **Pill no Disparador (`model-trigger`):** Exibe o nome do modelo junto com o nível de esforço ativo lado a lado (ex.: `Sonnet 5.5 Alto`, ou `Claude 3.7 Sonnet Médio`). Caso o modelo não suporte esforço ou esteja em `off`, exibe apenas o nome do modelo.
  - **Posicionamento no Popover:** No menu principal do cockpit, a linha `Esforço [Nível] >` entra logo após os modelos rápidos (`topModels`) e imediatamente antes de `Mais modelos >`.
  - **Rodapé do Chat (`input-footer-row`):** O pill compacto no rodapé externo reflete o mesmo estado sincronizado (`[Modelo] [Esforço]`).

- **`melhorias/esforco-reasoning/selecao-esforco.jpg`**: Detalhe do submenu cascata (flyout):
  - **Texto explicativo de cabeçalho:** No topo do container flutuante:  
    *"Mais esforço significa respostas mais completas, mas leva mais tempo e consome seus limites mais rápido."* (chave i18n `chat.effortExplainerHint`).
  - **Lista de opções:**
    - Item ativo recebe checkmark azul (`✓`) alinhado à direita.
    - O nível padrão/recomendado da família recebe a tag sutil `Recomendado` (`chat.effortRecommended`).
    - Níveis extremos (`extra` / `max`) recebem badge/alerta visual `⚠️ 5x ou mais de uso` (`chat.effortMaxWarning`).

## Onde fica

Dentro de `frontend/src/components/ModelSelector.tsx`, no balão popover já existente aberto pelo pill no rodapé da caixa de mensagem. Não voltar controle para o header. Não criar um segundo seletor solto no `MessageInput`.

### 1. No Trigger (`.model-trigger`)
O botão que abre o popover atualiza sua label:
```tsx
<span className="model-trigger-name">
  {isAuto ? (
    ...
  ) : selectedModel ? (
    <>
      <span className="model-name">{selectedModel.display_name}</span>
      {currentEffortLabel && (
        <span className="model-trigger-effort-badge">{currentEffortLabel}</span>
      )}
    </>
  ) : (
    t('chat.selectModel')
  )}
</span>
```

### 2. No Menu Principal (`renderMainMenu`)
A linha entra no menu principal do cockpit como um botão de navegação nativo (`cockpit-nav-row`), posicionado entre os top 3 modelos e a linha de `Mais modelos >`:

```tsx
<button
  type="button"
  className={`cockpit-nav-row ${activeSubmenu === 'effort' ? 'active' : ''}`}
  onClick={() => setActiveSubmenu(activeSubmenu === 'effort' ? 'none' : 'effort')}
  onMouseEnter={() => !isMobile && setActiveSubmenu('effort')}
  aria-expanded={activeSubmenu === 'effort'}
>
  <div className="cockpit-nav-left">
    <Brain size={14} strokeWidth={1.8} className="cockpit-row-icon" />
    <span>{t('chat.effort', { defaultValue: 'Esforço' })}</span>
  </div>
  <div className="cockpit-nav-right">
    <span className="cockpit-nav-value">{currentEffortLabel}</span>
    <ChevronRight size={14} className="cockpit-nav-chevron" />
  </div>
</button>
```

- **Desktop (≥ 768px):** Abre lateralmente no painel cascata `cockpit-submenu-flyout`, renderizando `renderEffortSubmenu()`, exatamente no mesmo layout exibido em `selecao-esforco.jpg`.
- **Mobile (< 768px):** O `ModelSelector` já utiliza `<BottomSheet>`. O clique altera `activeSubmenu = 'effort'` e renderiza o submenu com o cabeçalho de drill-down e botão `<button className="cockpit-back-btn">` já existente.

## Quando mostrar

| `reasoning_control` do modelo ativo | UI |
| :--- | :--- |
| `none` ou ausente | Linha some. Nada de controle desabilitado cinza ocupando o balão |
| `always_on` | Linha visível, sem flyout/seta. Texto informativo: este modelo raciocina sempre e não possui nível ajustável |
| dial (`openai_effort`, `gemini_thinking`, etc.) | Linha com valor atual + flyout listando apenas os `reasoning_levels` válidos |
| modo Auto | Linha visível rotulada como preferência global. Caption explicativo: aplicado se o modelo roteado suportar dial |

Modelo esgotado (`quota_status === exhausted`) não ganha regra nova. O esforço não desbloqueia cota.

## Estado e Fluxo

- **Persistência escopada:** Utilizar o padrão `_scopedKey` já definido em `useStore.ts`:
  - `_scopedKey('reasoning_effort_by_model')`: mapa JSON `Record<string, string>` guardando o nível escolhido por `model_id`.
  - `_scopedKey('reasoning_effort_auto')`: preferência do usuário para quando o Auto-Router estiver ativo.
- **Ao trocar de modelo:** Exibir o valor salvo para aquele id no mapa, ou cair no `reasoning_default` do modelo, ou omitir.
- **Envio no WebSocket:** Em `frontend/src/hooks/useChat.ts`, a função `sendMessage` injeta `reasoning_effort: activeEffort || undefined` no JSON transmitido pelo socket.
- **Tratamento de descarte:** Ao receber a mensagem `{ type: 'effort_dropped', reason, ... }` no switch do WebSocket em `useChat.ts`, despachar um toast leve via `useStore.getState().showToast(...)` com mensagem contextual traduzida. Não fechar nem reabrir o flyout.

## Interação

- `Escape` fecha o submenu de esforço (se aberto) ou o cockpit inteiro, preservando o listener de teclado existente em `ModelSelector.tsx`.
- Alvo de toque mínimo: 44px no desktop e 48px no mobile.
- Nível padrão da família recebe a tag visual `Recomendado`.
- Nível `max` ou `extra` ganha badge/aviso visual de consumo intensivo (`5x ou mais de uso`).
- Cabeçalho explicativo no flyout: *"Mais esforço significa respostas mais completas, mas leva mais tempo e consome seus limites mais rápido."*

## Visual

CSS puro em `frontend/src/index.css`, utilizando as variáveis de design tokens (`var(--primary)`, `var(--surface-soft)`, `var(--hairline)`, `var(--ink)`). Sem Tailwind. Suporte completo a tema claro e escuro. Fidelidade ao visual de referência em `selecao-esforco.jpg`.

## i18n

Chaves obrigatórias em `pt-BR.json`, `en-US.json` e `es-ES.json`:

- `chat.effort`
- `chat.effortLow`, `chat.effortMedium`, `chat.effortHigh`, `chat.effortExtra`, `chat.effortMax`, `chat.effortOff`, `chat.effortMinimal`
- `chat.effortRecommended`
- `chat.effortMaxWarning` (ex: "5x ou mais de uso")
- `chat.effortAlwaysOn`
- `chat.effortAutoHint`
- `chat.effortCostHint`
- `chat.effortDroppedFailover`
- `chat.effortDroppedUnsupported`
- `chat.effortDroppedProvider`

## O que não fazer na UI

- Não mostrar esforço para os 1633 modelos "por via das dúvidas".
- Não usar a foto do Claude como lista fixa de cinco opções.
- Não acoplar o seletor ao accordion de pensamento. Um controla o pedido. O outro mostra a resposta.
