# FABLE5 — Execução do Plano Mythos (Fusion com precisão de modelos frontier)

Objetivo: aproximar a resposta final do Fusion da qualidade de modelos de ponta
(Fable 5, GPT-5.6 Sol, Claude Mythos) executando o plano do `MYTHOS.md`
(Fases 1 e 2), com melhorias adicionais de robustez identificadas na análise
do código atual.

## Estado encontrado na análise (já implementado, não refazer)

- [x] `_buscar_web()` já usa o motor real (`backend/web_search`) com timeout — Fase 1, item 1 do MYTHOS.md concluído.
- [x] Eventos WebSocket `fusion_grounding` já existem em `frontend/src/types.ts`, `useChat.ts` e `useStore.ts` (`updateFusionGrounding`).
- [x] UI do grounding já renderizada no `FusionStatusCard.tsx` (checking / searching / done).
- [x] System prompt do Juiz reestruturado (extração → reconciliação → síntese) e sufixo de auto-crítica `[CONFIANCA: ...]` injetado nos proposers.

## Fase 1 — Fechar o grounding ponta a ponta

### 1.1 Banco de dados (`backend/database.py`)
- [x] Adicionar coluna `grounding_enabled INTEGER DEFAULT 1` na tabela `fusion_config` (schema).
- [x] Migração incremental em `init_db()` seguindo o padrão existente (SELECT → except OperationalError → ALTER TABLE).

### 1.2 API REST (`backend/routers/fusion.py`)
- [x] Incluir `grounding_enabled` em `FusionConfigOut`, `FusionConfigIn` e `_get_judge_config()`.
- [x] Persistir `grounding_enabled` no `save_config` (INSERT ... ON CONFLICT UPDATE).

### 1.3 Orchestrator (`backend/fusion/orchestrator.py`)
- [x] Ler `grounding_enabled` de `fusion_config` na query já existente.
- [x] Regra efetiva: grounding roda se (config ligada OU usuário ativou busca web na mensagem) E busca web global habilitada.
  - Nota: `chat.py` já passa `req.get("web_search", False)`; esse flag vira um "força ligar" por mensagem, sem depender do admin.

### 1.4 Painel de configurações (`frontend/src/components/FusionSettings.tsx` + `types.ts`)
- [x] Adicionar `grounding_enabled` à interface `FusionConfig`.
- [x] Toggle "Verificação factual (busca web)" com descrição curta sobre a latência extra (~2-5s antes do Juiz).

## Fase 2 — Auto-crítica dos proposers visível e sem vazamento

### 2.1 Parsing no backend (`backend/fusion/orchestrator.py`)
- [x] Extrair a linha `[CONFIANCA: alta|media|baixa — motivo]` da resposta de cada proposer com regex tolerante (acentos, maiúsculas, variações).
- [x] Enviar no evento `fusion_status` (status `done`) os campos `confidence` e `confidence_reason`; o campo `response` vai limpo (sem a linha crua).
- [x] Manter a informação de confiança para o Juiz: o bloco de cada resposta passa a ter cabeçalho `--- RESPOSTA: <modelo> [CONFIANCA: <nível>] ---`, com corpo limpo.
  - Vantagem sobre regex no frontend (sugestão original do MYTHOS.md): parse único, nenhum texto cru chega ao usuário e o dado fica disponível estruturado para o Juiz.

### 2.2 Badge no card (`frontend/src/components/FusionStatusCard.tsx` + `types.ts` + `useStore.ts` + `useChat.ts`)
- [x] `FusionStatusEntry` ganha `confidence?: 'alta' | 'media' | 'baixa'` e `confidence_reason?: string`.
- [x] `WSMessage` do tipo `fusion_status` ganha os mesmos campos.
- [x] `updateFusionStatus` repassa confidence para a entrada correta.
- [x] Badge visual no cabeçalho da linha do modelo: verde (alta) / amarelo (média) / vermelho (baixa), com `title` mostrando o motivo. CSS em `frontend/src/index.css`.

### 2.3 Não persistir confiança em tabela nova
- Fora de escopo: depende da Melhoria C (persistência de respostas paralelas), que o usuário pediu para NÃO executar.

## Melhorias adicionais (julgadas necessárias na análise)

- [x] **Guarda anti-vazamento no Juiz**: remover qualquer linha `[CONFIANCA: ...]` da resposta final do Juiz antes de salvar no banco e detectar artifacts (defesa caso o modelo Juiz ignore a instrução do prompt).
- [x] **Timeout no Juiz e na detecção de claims**: hoje só os proposers têm timeout; um Juiz travado segura o Fusion indefinidamente. Adicionar timeout generoso (180s no Juiz, 30s na detecção de claims).
- [x] **Truncar resposta limpa antes do Juiz não é necessário** (mantido comportamento atual), mas a detecção de claims continua limitada a 1500 chars por resposta para economizar tokens.

## Fase 3 do MYTHOS.md — adiada (decisão de escopo)

Conforme o próprio plano recomenda: shippar Fases 1 e 2, medir o ganho real do
grounding no Juiz por 1-2 semanas e só então avaliar tool use nos proposers
(custo maior de latência e engenharia).

## Fora de escopo (conforme instrução do usuário)

- Melhorias A–E da seção "4. Sugestões de Melhorias para Avaliação" do `MELHORIAS_FUSION.md`.

## Done When (critérios de verificação)

- [x] `python -m py_compile` passa nos arquivos backend alterados.
- [x] `tsc --noEmit` (ou `npm run build`) passa no frontend.
- [x] Migração adiciona `grounding_enabled` num banco existente sem erro.
- [x] Toggle de grounding salva e recarrega via `/api/fusion/config`.
- [x] Resposta de proposer com `[CONFIANCA: baixa — ...]` aparece como badge no card, sem texto cru no corpo.
- [x] Resposta final do Juiz salva no banco nunca contém `[CONFIANCA: ...]`.
