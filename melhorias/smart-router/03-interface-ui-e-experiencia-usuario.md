# 🧭 03. Interface do Usuário (UI/UX) e Transparência
**Multi+ / NexusLocal** · Planejamento Arquitetural

---

## 1. Ponto de Entrada: `ModelSelector.tsx`

Para que o Auto-Roteamento seja natural e acessível, a opção **`🎯 Auto (Roteamento Inteligente)`** deve figurar como a primeira opção destacada no topo da lista de modelos:

```
┌────────────────────────────────────────────────────────┐
│  Selecione o Modelo:                                   │
├────────────────────────────────────────────────────────┤
│  🎯 Auto (Roteamento Inteligente)             [PADRÃO] │
│     Seleciona a melhor IA por contexto, cota e tarefa  │
├────────────────────────────────────────────────────────┤
│  ── Modelos Disponíveis (Ordenados por Ranking) ────── │
│  🥇 DeepSeek V4 (OpenRouter)              94 pts       │
│  🥈 Llama 3.3 70B (Groq)                  91 pts       │
│  🥉 Gemini 2.0 Flash (Google)             88 pts       │
│     Qwen 2.5 Coder 32B                    85 pts       │
│     Llama 3.1 8B (Groq)                   76 pts       │
└────────────────────────────────────────────────────────┘
```

### Detalhes de Design:
* **Item Fixo no Topo:** A opção `Auto` não é reordenada pelo ranking alfabético; ela permanece ancorada no topo com estilo visual refinado (borda sutil acentuada e ícone de alvo `🎯` ou faísca `✨`).
* **Estado Ativo no Store:** Quando selecionado, `selectedModelId` armazena o valor especial `'auto'`, disparando a lógica preditiva no backend.

---

## 2. Indicador Transparente no Chat (`MessageBubble.tsx`)

O princípio de **transparência radical** exige que o usuário veja exatamente qual modelo foi acionado e por qual razão. No cabeçalho da resposta da IA:

```
┌────────────────────────────────────────────────────────────────────────┐
│ 🤖 Llama 3.3 70B (Groq)   🎯 Auto: Código & Engenharia       10:42      │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│ Para corrigir esse erro de tipagem no TypeScript, você precisa...     │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Comportamento do Tooltip / Popover Informativo:
Ao passar o mouse sobre o badge `🎯 Auto: Código & Engenharia`:

```
┌────────────────────────────────────────────────────┐
│  Decisão do Smart Intent Router                    │
├────────────────────────────────────────────────────┤
│  • Intenção Detectada: Código & Engenharia (94%)   │
│  • Sinal Principal: Presença de TypeScript/React   │
│  • Política: Equilibrada (Smart)                   │
│  • Tempo de Decisão: 1.2 milissegundos             │
│  • Modelo Escolhido: Llama 3.3 70B (#1 em Código)  │
└────────────────────────────────────────────────────┘
```

---

## 3. Painel de Preferências em Configurações

Uma nova seção dedicada em **Configurações ➔ Roteador de Modelos** (ou integrada em [`RankingsView.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/RankingsView.tsx)):

```
┌────────────────────────────────────────────────────────────────────────┐
│  🎯 AUTO-ROTEADOR INTELIGENTE DE MODELOS                               │
├────────────────────────────────────────────────────────────────────────┤
│  Modo de Roteamento Padrão:                                            │
│  ( ) 🟢 Econômico (Free-First) — Prioriza modelos 100% gratuitos       │
│  (•) 🔵 Equilibrado (Smart) — Ultra-rápido no simples, 70B no complexo │
│  ( ) 🟣 Máxima Qualidade (Pro) — Sempre o maior score do benchmark     │
├────────────────────────────────────────────────────────────────────────┤
│  Modelos Especialistas Preferenciais (Opcional):                       │
│  • Programação / Código:    [ Automático pelo Ranking ▾ ]              │
│  • Raciocínio Profundo:     [ DeepSeek-R1 (OpenRouter) ▾ ]             │
│  • Respostas Rápidas:       [ Llama 3.1 8B (Groq) ▾ ]                  │
│  • Leitura de Imagens:      [ Gemini 2.0 Flash ▾ ]                     │
├────────────────────────────────────────────────────────────────────────┤
│  [✓] Exibir motivo da escolha do modelo em cada resposta no chat       │
│  [✓] Notificar se houver failover automático durante o streaming       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Integração com a Frente 01 (Composer Action Pills)

Quando as [Action Pills](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/01-composer-action-pills.md) estiverem ativas no rodapé do input:
* Uma pill `🎯 Auto` informará o modo ativado.
* O atalho de teclado `Alt+A` permitirá alternar instantaneamente entre `Auto` e o último modelo fixo utilizado.
