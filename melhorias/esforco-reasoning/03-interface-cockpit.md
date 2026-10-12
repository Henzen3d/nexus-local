# 03 — Interface no cockpit

**Multi+ / NexusLocal** · Plano, não implementação

Referência visual: `melhorias/new-chat-input/selecao-esforco.jpg`. O flyout do Claude (Baixo, Médio recomendado, Alto, Extra, Máx, mais uma linha de consumo) é o alvo de ergonomia. Os níveis reais são os do modelo, não os cinco da foto.

## Onde fica

Dentro de `frontend/src/components/ModelSelector.tsx`, no balão que já abre pelo pill do rodapé. Não voltar controle para o header. Não criar um segundo seletor solto no `MessageInput`.

Camada nova, abaixo do toggle de Roteamento Inteligente e acima das pílulas de provedor — ou uma linha no rodapé do próprio balão, ancorada no modelo ativo:

```
Esforço          Médio >
```

Clique abre flyout lateral (desktop) ou `BottomSheet` (já usado pelo menu `+` abaixo de 768px).

## Quando mostrar

| `reasoning_control` do modelo ativo | UI |
| :--- | :--- |
| `none` ou ausente | Linha some. Nada de controle desabilitado cinza ocupando o balão |
| `always_on` | Linha visível, sem flyout. Texto: este modelo raciocina sempre e não tem nível de esforço |
| dial (`openai_effort`, `gemini_thinking`, etc.) | Linha + flyout só com `reasoning_levels` |
| modo Auto | Linha continua, rotulada como preferência. Caption: vale se o modelo escolhido aceitar |

Modelo esgotado (`quota_status === exhausted`) não ganha regra nova. O esforço não desbloqueia cota.

## Estado

- Preferência por `model_id` em `localStorage`, chave no mesmo estilo já usado por `selected_model_id` em `useStore.ts`.
- Ao trocar de modelo, mostrar o valor salvo daquele id, ou `reasoning_default`, ou omitir.
- `sendMessage` / payload do WebSocket inclui `reasoning_effort` só quando o controle ativo tem dial e há um nível escolhido.
- Evento `effort_dropped`: toast curto. Não reabrir o flyout.

## Interação

- `Escape` fecha o flyout e o balão, na mesma disciplina do menu `+`.
- Alvo de toque 44px no desktop compacto não infla a barra; no sheet mobile, 48px, igual ao `PlusActionMenu`.
- Nível default da família leva o rótulo "Recomendado".
- Uma linha de ajuda no fim do flyout: mais esforço, mais espera e mais tokens de raciocínio.

## Visual

CSS em `frontend/src/index.css`, tokens já existentes (`--primary`, `--surface-soft`, `--hairline`, `--ink`). Sem Tailwind. Claro e escuro. Sem badge luminoso no pill do modelo — o valor cabe na linha "Esforço".

## i18n

Chaves novas em `pt-BR.json`, `en-US.json` e `es-ES.json`. Demais locales caem no inglês, como no redesign do input.

Mínimo:

- `chat.effort`
- `chat.effortLow` `chat.effortMedium` `chat.effortHigh` `chat.effortExtra` `chat.effortMax` `chat.effortOff` `chat.effortMinimal`
- `chat.effortRecommended`
- `chat.effortAlwaysOn`
- `chat.effortAutoHint`
- `chat.effortCostHint`
- `chat.effortDropped`

## O que não fazer na UI

- Não mostrar esforço para os 1633 modelos "por via das dúvidas".
- Não usar a foto do Claude como lista fixa de cinco opções.
- Não acoplar o seletor ao accordion de pensamento. Um controla o pedido. O outro mostra a resposta.
