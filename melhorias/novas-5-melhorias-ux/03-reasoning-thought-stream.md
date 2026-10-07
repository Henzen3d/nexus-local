# 🎯 Frente 03: Accordion de Raciocínio (Thought Stream) & Timeline Fusion

## 1. Contexto e Problema Atual

Atualmente no Multi+:
* O suporte a modelos analíticos avançados (como DeepSeek-R1, Gemini 2.0 Flash Thinking e Llama 3.3 70B com prompt de raciocínio) devolve o processo de pensamento misturado com a resposta final ou com tags puras `<think>...</think>`.
* No Modo Fusion, embora exista o [`FusionStatusCard.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/FusionStatusCard.tsx), a transição entre as etapas de consulta dos múltiplos modelos, a análise pelo juiz e a resposta consolidada pode causar sensação de atraso se não houver um feedback visual contínuo e elegante.

## 2. Benchmark de Mercado

* **DeepSeek**: Referência absoluta de UX para raciocínio. Apresenta uma caixa discreta e colapsável com:
  * Um ícone com animação de pulso sutil enquanto o modelo pensa.
  * Cronômetro de tempo real: *"Pensando... (4s)"* que ao concluir vira *"Pensou por 14 segundos ▾"*.
  * O conteúdo do pensamento fica formatado com tipografia mono/secundária suave, separando visualmente o raciocínio analítico da resposta definitiva.
* **ChatGPT**: Accordion discreto intitulado *"Pensamento"*, recolhido por padrão quando a resposta começa a fluir.
* **Manus & MiniMax AI**: Linha do tempo visual indicando o andamento das ferramentas e provedores em paralelo.

---

## 3. Especificação da Solução para o Multi+

### A. Componente ThoughtAccordion (Pensamento Profundo)

```
┌────────────────────────────────────────────────────────────────────────┐
│  🧠 Pensou por 6.8 segundos ▾                                [Copiar] │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ O usuário está perguntando sobre otimização assíncrona em Python.│  │
│  │ Preciso abordar asyncio, aiohttp e concorrência sem bloqueio...  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  Aqui está a arquitetura recomendada para processamento assíncrono:    │
│  ... (resposta final formatada)                                        │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Durante o streaming de raciocínio**:
   * O accordion permanece aberto com indicador de digitação suave e tempo decorrido ao vivo.
2. **Quando o modelo conclui o pensamento e inicia a resposta final**:
   * O accordion se recolhe suavemente (auto-collapse com transição CSS) para deixar o foco imediato na resposta final.
   * O usuário pode clicar no cabeçalho a qualquer momento para expandir e ler a cadeia de pensamentos completa.

### B. Mini-Timeline do Modo Fusion

Transformar o cartão de status do Fusion em uma linha do tempo vertical ou horizontal minimalista:
* `● 1. Provedores Consultados` (Groq, Cerebras, Gemini respondendo em paralelo com micro-status).
* `● 2. Análise do Juiz` (identificando concordâncias e divergências).
* `✓ 3. Síntese Unificada` (gerada e pronta para leitura).

---

## 4. Divisão de Tarefas e Subtarefas

### Tarefa 3.1: Detecção e Streaming de Raciocínio (Parser)
- [ ] **3.1.1**: Criar utilitário [`thoughtParser.ts`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/utils/thoughtParser.ts) capaz de separar o bloco `<think>...</think>` do conteúdo da resposta durante o streaming em tempo real via WebSocket.
- [ ] **3.1.2**: Tratar casos onde a tag de fechamento `</think>` ainda não chegou durante o streaming contínuo.
- [ ] **3.1.3**: Suporte a modelos que enviam o campo específico `reasoning_content` (DeepSeek API, OpenRouter).

### Tarefa 3.2: Componente ThoughtAccordion
- [ ] **3.2.1**: Criar o componente [`ThoughtAccordion.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/ThoughtAccordion.tsx).
- [ ] **3.2.2**: Adicionar cronômetro interno com `requestAnimationFrame` ou timer de 100ms medindo o tempo decorrido desde o início da geração.
- [ ] **3.2.3**: Implementar auto-recolhimento automático quando o conteúdo da resposta final começar a chegar.
- [ ] **3.2.4**: Botão para copiar apenas o texto de raciocínio ou a resposta completa.

### Tarefa 3.3: Refatoração da Timeline do Modo Fusion
- [ ] **3.3.1**: Redesenhar [`FusionStatusCard.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/FusionStatusCard.tsx) com layout em timeline minimalista (estilo editorial).
- [ ] **3.3.2**: Exibir badges compactos de latência de cada modelo participante (ex: *Cerebras: 240ms*, *Groq: 480ms*).
- [ ] **3.3.3**: Tornar a visualização dos rascunhos individuais colapsável sob demanda.

### Tarefa 3.4: Estilização Editorial & Design Tokens
- [ ] **3.4.1**: Adicionar classes em [`index.css`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/index.css) para o bloco de pensamento com fundo levemente diferenciado (`rgba(0,0,0,0.02)` no claro, `rgba(255,255,255,0.03)` no escuro) e borda esquerda sutil.
- [ ] **3.4.2**: Aplicar fonte monospace sutil ou itálica com peso balanceado para o texto de raciocínio.

---

## 5. Critérios de Aceite (Definition of Done)

* [ ] Ao enviar pergunta para modelo com raciocínio (R1/Thinking), o processo analítico é exibido no accordion com contador de segundos.
* [ ] A resposta final não é poluída por tags brutas `<think>`.
* [ ] O accordion fecha de forma fluida quando a resposta final inicia, sem causar pulo brusco de scroll na tela.
* [ ] No Modo Fusion, o usuário consegue acompanhar o progresso das chamadas paralelas sem sensação de travamento.
