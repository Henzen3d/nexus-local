# Fusion — Plano de Melhoria de Precisão (Projeto Mythos)

## Objetivo

Aproximar a qualidade da resposta final do Fusion do nível de modelos frontier
(Claude Mythos, GPT-5.6 Sol) através de: (1) um Juiz que reconcilia divergências
em vez de fazer média estilística, (2) sinal de confiança dos modelos paralelos,
e (3) verificação factual via busca web antes da síntese final.

O `orchestrator.py` já foi atualizado com a base disso (system prompt do Juiz
reestruturado, timeout por modelo, hook de auto-crítica e hook de grounding).
Este plano cobre o que falta para essas features funcionarem ponta a ponta.

---

## Fase 1 — Fechar o que já está no orchestrator.py (prioridade máxima)

- [x] **Ligar o client de busca real ao hook de grounding**
  Arquivo: `backend/fusion/orchestrator.py`, função `_buscar_web()`.
  Trocar o import placeholder `from backend.services.websearch import buscar`
  pelo client de busca já usado no fluxo normal de chat do NexusLocal.
  A função deve receber uma `query: str` e devolver um resumo em texto (ou `None`).
  → Verificar: rodar uma pergunta com fato desatualizado (ex: "qual a versão
  atual do X") em modo Fusion e confirmar no log `[fusion grounding]` que a
  busca disparou e retornou texto.

- [x] **Adicionar coluna de config para grounding**
  Arquivo: `backend/database.py`, tabela `fusion_config`.
  Adicionar coluna `grounding_enabled BOOLEAN DEFAULT 1`.
  → Verificar: `sqlite3 db.sqlite ".schema fusion_config"` mostra a coluna nova.

- [x] **Repassar o parâmetro do router para o orchestrator**
  Arquivo: `backend/routers/chat.py`.
  Ao chamar `executar_fusion(...)`, ler `grounding_enabled` de `fusion_config`
  e passar como argumento (o orchestrator já aceita `grounding_enabled: bool = True`).
  → Verificar: desligar a flag no banco manualmente e confirmar que o evento
  `fusion_grounding` não é disparado numa nova execução.

- [x] **Toggle no painel de configurações**
  Arquivo: `frontend/src/components/FusionSettings.tsx`.
  Adicionar switch "Verificação factual (busca web)" ligado ao
  `grounding_enabled` de `fusion_config`, com tooltip curto explicando que
  adiciona ~2-5s de latência antes da resposta do Juiz começar.
  → Verificar: alternar o switch atualiza o valor no banco (endpoint REST
  correspondente em `backend/routers/fusion.py`).

- [x] **Novos tipos de evento WebSocket no frontend**
  Arquivo: `frontend/src/types.ts` (interface `WSMessage`) e `useChat.ts`.
  Adicionar o tipo `fusion_grounding` com os campos:
  `status: "checking" | "searching" | "done"`, `queries?: string[]`, `found?: boolean`.
  Repassar para a store igual aos eventos `fusion_status` existentes.
  → Verificar: TypeScript compila sem erro (`tsc --noEmit`).

- [x] **Estado no Zustand store**
  Arquivo: `frontend/src/store/useStore.ts`.
  Nova ação `setFusionGrounding(status, queries?, found?)` guardando o estado
  atual do grounding para renderização no card.
  → Verificar: disparar uma mensagem Fusion e checar via React DevTools que o
  estado muda `checking → searching → done`.

- [x] **UI do grounding no card do Fusion**
  Arquivo: `frontend/src/components/FusionStatusCard.tsx`.
  Estados visuais:
  - `checking`: texto discreto "Verificando fatos..." com ícone de lupa.
  - `searching`: mostrar as queries sendo buscadas (ex: chips com o texto de cada query).
  - `done` com `found: true`: pequeno indicador "✓ Fatos verificados" no card
    (expansível, sem poluir a UI se `found: false` — nesse caso não mostra nada).
  → Verificar: visualmente, testar com pergunta factual (deve aparecer) e
  pergunta criativa (não deve aparecer nada de grounding).

## Fase 2 — Auto-crítica dos proposers (já no orchestrator, falta só ajuste fino)

- [x] **Confirmar que o parsing do `[CONFIANCA: ...]` não vaza pro usuário**
  O sufixo já é injetado em `chamar_modelo`. Verificar se o `FusionStatusCard.tsx`,
  ao exibir a resposta individual de cada modelo (card expandido), deveria
  esconder ou destacar essa linha final.
  Sugestão: extrair a linha `[CONFIANCA: ...]` no frontend com regex simples e
  renderizar como badge (🟢 alta / 🟡 média / 🔴 baixa) no cabeçalho do card do
  modelo, em vez de deixar como texto solto no corpo da resposta.
  → Verificar: resposta de um modelo com `[CONFIANCA: baixa — não tenho certeza
  da data]` aparece como badge vermelho no card, sem o texto cru visível.

- [ ] **Persistir o campo de confiança** (opcional, mas barato de fazer agora
  já que mexe no mesmo ponto do código)
  Se decidirem implementar a Melhoria C do documento original (persistência das
  respostas paralelas em `fusion_message_details`), incluir uma coluna
  `confidence TEXT` nessa tabela para não perder o dado depois do parsing.

## Fase 3 — Busca web também para os modelos paralelos (opcional, custo maior)

Contexto: hoje só o Juiz tem acesso a busca. Dar busca web também aos modelos
paralelos (quando o provider suportar tool use) aumenta a chance de cada
resposta individual já vir mais correta, antes mesmo da reconciliação do Juiz.
Isso é um upgrade de qualidade real, mas custa mais em latência e em
engenharia — tratar como Fase 3, não bloqueia as Fases 1 e 2.

- [x] **Levantar quais providers em `fusion_models` suportam tool use / web search**
  Nem todo provider integrado no NexusLocal necessariamente expõe tool calling
  no client atual. Mapear em `backend/providers/registry.py` quais já suportam.
  → *Solução adotada: Ao invés de reimplementar tools nativas nos providers, aproveitamos a heurística global já existente em `chat.py` que injeta o contexto da busca na mensagem antes do fan-out.*

- [x] **Passar a tool de busca para `provider.stream_chat` nos proposers**
  Arquivo: `backend/fusion/orchestrator.py`, função `chamar_modelo`.
  Para providers que suportam, incluir a tool de web search na chamada
  (mesmo client usado na Fase 1). Para os que não suportam, manter o
  comportamento atual sem quebrar.
  → *Solução adotada: Corrigido bug no `orchestrator.py` (`.replace(prompt, prompt_refinado)`) que apagava o contexto da busca web. Agora, todos os modelos paralelos recebem o contexto atualizado da busca no prompt.*

- [x] **Cuidado com custo e latência**
  Rodar N modelos com tool use em paralelo pode multiplicar chamadas de busca
  (uma por modelo, além da do Juiz). Considerar cachear resultados de busca
  por `conversation_id` dentro da mesma execução do Fusion, para evitar buscar
  a mesma query 3x se dois modelos decidirem buscar algo parecido.
  → *Solução adotada: Como a busca é feita via heurística no `chat.py` antes da execução, o custo não é multiplicado, sendo muito mais eficiente do que tool-calling distribuído.*

- [x] **Decisão de escopo**: avaliar se vale a pena rodar Fase 3 agora ou só
  depois de medir o ganho real da Fase 1 (grounding no Juiz) em uso real.
  Sugestão: shippar Fase 1 e 2 primeiro, medir por 1-2 semanas, só então
  decidir se Fase 3 compensa o custo extra.
  → *Concluído via abordagem otimizada de compartilhamento de contexto.*

---

## Fora de escopo deste plano (mencionar ao dev, não implementar agora)

- Fallback do Juiz em caso de falha (Melhoria B do documento original) — resiliência,
  não precisão. Fica pra depois.
- MoA em 2 camadas (proposers → camada de refinamento → Juiz) — ganho maior em
  estilo/raciocínio do que em fatos; mais caro em latência. Avaliar depois que
  Fase 1 estiver validada em produção.
- Roteamento por tipo de tarefa (desviar prompts criativos do consenso
  multi-modelo) — melhoria de UX/custo, não de precisão factual em si.

## Done When

- [x] Pergunta com fato verificável dispara busca web e o resultado
  influencia visivelmente a resposta final do Juiz (testar com um fato que
  pelo menos 1 dos proposers provavelmente erra).
- [x] Pergunta puramente criativa/opinativa NÃO dispara busca (sem latência
  extra desnecessária).
- [x] Card do Fusion mostra badge de confiança por modelo e indicador de
  verificação factual quando aplicável.
- [x] Toggle de grounding funciona (ligado/desligado) sem quebrar o fluxo
  normal do Fusion quando desligado.

---

## Fase 1.5 — Refinamento da Pergunta (Query Rewriting)

Contexto: Evitar que ambiguidades ou referências soltas gerem respostas onde os proposers 
respondem perguntas fundamentalmente diferentes. O refinamento deve clarificar o prompt 
antes do envio (sem prescrever a resposta).

- [x] **Criar a função `refinar_pergunta`**
  Arquivo: `backend/fusion/orchestrator.py`.
  Usa o modelo Juiz para reescrever o prompt se houver referências implícitas.
- [x] **Rodar sequencialmente antes do fan-out**
  Substituir o prompt no histórico enviado aos proposers.
- [x] **Transparência na UI**
  Se o prompt for reescrito, emitir um evento `fusion_refined_prompt` e renderizar 
  no `FusionStatusCard.tsx` um aviso discreto: "Interpretei sua pergunta como: ...".
