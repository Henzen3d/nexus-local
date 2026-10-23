# GOLDEN PROMPT: Ciclo de Autoaperfeiçoamento de UX/UI e Confiabilidade de Streaming — Nexus Local

## Para
Agente Executor Autônomo de Engenharia Frontend/Fullstack (Especialista em React, TypeScript, Zustand, WebSockets e UX/UI de Chat com IA).

## Objetivo
Elevar a experiência de usuário (UX/UI) do **Nexus Local** (`multi.mob.tec.br`, PWA) ao nível de excelência, fluidez e intuitividade de produtos líderes (como ChatGPT/Claude), operando através de um **Loop de Autoaperfeiçoamento Contínuo**.

Como o Nexus Local agrega modelos gratuitos (via OpenRouter e provedores diretos como Gemini) sujeitos a latência variável e failovers mid-stream, a interface deve transmitir **confiabilidade absoluta**: zero travamentos de renderização, transições invisíveis ou elegantes durante failovers, excelente legibilidade tipográfica (Markdown, código, tabelas), Intelligent UI/Artefatos impecáveis e micro-interações responsivas.

---

## Regras Férreas do Projeto ( Inegociáveis )
1. **Intocabilidade dos 3 Níveis de Interface:** O sistema atual de três níveis em *Configurações > Preferências* (**Simples** com smart router e sem seletores manuais, **Intermediário** com troca rápida, e **Avançado** com provedores e controle de esforço) **ESTÁ APROVADO E CONGELADO**. É estritamente proibido alterar sua lógica, visibilidade ou comportamento.
2. **Isolamento de Ambiente e Portas:** O projeto roda estritamente via Docker Compose. A porta `8000` do host pertence ao Portainer — qualquer validação ou teste deve ocorrer dentro dos containers ou na rede interna do Docker. O Nginx do frontend deve escutar exclusivamente em IPv4 (`127.0.0.1`, nunca `localhost`).
3. **Proteção ao Banco de Dados:** Proibido rodar testes ou scripts destrutivos contra o banco vivo (`backend/nexuslocal.db`). Testes de backend devem usar exclusivamente instâncias SQLite temporárias/em memória descartáveis.
4. **Restrição Semântica:** É estritamente proibido mencionar, invocar ou reindexar `GitNexus` em qualquer arquivo, log, comentário ou commit.
5. **Portão de Qualidade (Quality Gate):** Nenhum código é considerado pronto sem que `npm run build` (TypeScript estrito, zero warnings fatais) e `pytest` estejam **100% verdes**.
6. **Pipeline Oficial de Deploy:** Qualquer deploy segue rigorosamente o ritual do `AGENTS.md`: backup + verificação de integridade do DB $\rightarrow$ `git pull` $\rightarrow$ `docker compose build --no-cache` $\rightarrow$ `docker compose up -d --force-recreate` $\rightarrow$ `docker system prune` $\rightarrow$ checagem de healthcheck e logs (lembrando que o PWA possui Service Worker e exige renovação limpa de cache/assets).

---

## Diagnóstico Técnico (Proteção Contra Regressão)
Dois bugs críticos de streaming foram corrigidos recentemente. **Você está proibido de regredir estas arquiteturas:**

1. **Prevenção de "Splicing" Sujo em Failover Mid-Stream (`stream_clear`):**
   * *Problema anterior:* O Modelo A emitia tokens parciais, sofria erro, e o Modelo B concatenava novos tokens na mesma bolha de mensagem, gerando textos híbridos corrompidos.
   * *Invariante atual:* Quando ocorre failover após emissão de tokens (ou antes de erro terminal), o backend emite `{ type: 'stream_clear' }`. O handler em `useChat.ts` deve invocar `clearStreamDraft` na store do Zustand, limpando `streamingContent` e `streamingUiBlocks` **sem encerrar a mensagem atual**, permitindo que o modelo de fallback comece a escrever do zero de forma limpa, acompanhado do feedback sutil de `failover_notice`.
2. **Separação Estrita entre Ciclo de Vida do Turno e Indicador Visual (`isGeneratingRef` vs `s.isGenerating`):**
   * *Problema anterior:* No evento `case 'token'`, o código fazia `isGeneratingRef.current = false` logo no primeiro fragmento recebido, fazendo o frontend descartar silenciosamente todos os tokens subsequentes e o `stream_end` (a UI congelava no primeiro caractere, ex: `"**"`).
   * *Invariante atual:* `isGeneratingRef.current` governa o **ciclo de vida lógico do turno** e **DEVE permanecer `true`** durante toda a sessão de streaming. Ele só pode ir para `false` em eventos terminais: `stream_end`, `error` fatal, `onclose` do WebSocket ou ação explícita de `stopStream` pelo usuário. Eventos intermediários (`token`, `search_start`, `process_step_start`, `ui_progress`) devem alterar apenas o estado visual `s.isGenerating` no Zustand (ex: para ocultar o spinner inicial quando o texto começa a fluir).

---

## Estado Atual da Arquitetura de UI
* **Protocolo WebSocket (`frontend/src/types.ts`):** Suporta ciclo completo (`stream_start`, `stream_clear`, `token`, `stream_end`), raciocínio/etapas (`process_step_start/update/end`, `search_start`), modo Fusão (`fusion_start`, `fusion_phase`, `fusion_status`, `fusion_judge_start`, `fusion_grounding`, `fusion_refined_prompt` renderizados via `FusionStatusCard.tsx`), roteamento (`auto_route_decision`, `failover_notice`, `effort_dropped`) e geração de mídia (`image_pending/ready/failed`).
* **Intelligent UI (Planos 1 a 13 Concluídos com 100% de Paridade):**
  * Catálogo `UiBlockType`: `progress`, `card`, `chart`, `table`, `controls`, `options`, `sandbox`, `metric`, `callout`, `follow_up` (+ suporte a `scene` 2D/3D, `checklist`, `image`).
  * Componentes em `frontend/src/ui/components/`: `CalloutCard`, `ChartCard`, `ChecklistCard`, `ControlsCard`, `CorrectionNotice`, `FollowUpCard`, `ImageCard`, `MetricCard`, `OptionsCard`, `ProgressCard`, `SandboxCard`, `SceneCard`, `TableCard`, `UiCard`.
  * Possui renderização progressiva durante o stream (`ui_progress` e `ui_blocks` no `stream_end`), auto-correção com diagnósticos (`ui_errors`, `CorrectionNotice.tsx`) e estado compartilhado com expressões seguras.
* **Markdown e Artefatos:** Texto rico renderizado em `MessageBubble.tsx` via `react-markdown` + `remark-gfm`. Artefatos complexos (`html`, `markdown`, `svg`, `code`, `jsx`) abrem lateralmente no `ArtifactPanel.tsx`.
* **Níveis de Interface:** Três modos operacionais (Simples, Intermediário, Avançado) perfeitamente estabelecidos.

---

## Escopo de Atuação e Critérios de Aceite (Testáveis)

Para que uma iteração do loop seja considerada **APROVADA**, todos os critérios abaixo devem ser verificados no código e validados em execução:

### CA-1: Confiabilidade e Fluidez de Streaming (Zero Travamentos)
- [ ] **Invariante de Turno:** Verificar em `useChat.ts` e na store que `isGeneratingRef.current` nunca é mutado para `false` em handlers não-terminais (`token`, `ui_progress`, `process_step_*`, `search_start`, `stream_clear`).
- [ ] **Limpeza de Failover:** Simular/testar o recebimento de `stream_clear` seguido de `failover_notice` e novos `token`s: a bolha da mensagem deve limpar o rascunho anterior instantaneamente sem "piscar" layout quebrado e exibir um aviso discreto e traduzido do failover se aplicável.
- [ ] **Auto-Scroll Inteligente (Smart Scroll Anchor):** Durante o streaming de tokens e renderização de blocos da Intelligent UI, a tela deve rolar suavemente para baixo **apenas** se o usuário já estiver próximo ao final da página. Se o usuário rolar para cima para ler o histórico durante a geração, o auto-scroll deve pausar imediatamente e exibir um botão flutuante discreto ("Ir para o final" / seta para baixo).
- [ ] **Transições de Estado de Espera:** Entre o envio da mensagem e o primeiro `token`, o usuário deve ver feedback imediato e sem congelamentos (skeleton sutil ou indicador de pulso harmonizado com `process_step_start`, `search_start` e `fusion_*`), sem causar *Cumulative Layout Shift* (CLS) abrupto quando o primeiro token chegar.

### CA-2: Organização Visual e Tipografia em `MessageBubble.tsx`
- [ ] **Hierarquia Tipográfica (Padrão ChatGPT):** Espaçamento vertical (`line-height`, margens entre parágrafos, listas aninhadas e cabeçalhos `h1-h4`) calibrado para leitura longa sem fadiga visual, tanto em telas desktop quanto mobile (PWA).
- [ ] **Blocos de Código de Primeira Classe:** Todo bloco `<pre><code>` deve possuir cabeçalho fixo com o nome da linguagem, botão de "Copiar código" com feedback visual de confirmação (ícone de check por 2s) e *horizontal scroll* isolado (nunca quebrando a largura da `MessageBubble` no mobile).
- [ ] **Tabelas GFM Responsivas:** Tabelas Markdown em `MessageBubble.tsx` devem ser envolvidas em containers com `overflow-x: auto`, bordas suaves, cabeçalhos destacados e *zebra striping* sutil, impedindo estouro de viewport em telas pequenas.
- [ ] **Markdown Parcial Resiliente:** Durante o streaming, construtos Markdown incompletos (ex: blocos de código abertos ``` sem fechamento ou tabelas pela metade) não devem quebrar o layout nem gerar *flickering* agressivo.

### CA-3: Polimento da Intelligent UI e `ArtifactPanel.tsx`
- [ ] **Estética e Consistência dos `UiCard`s:** Todos os componentes em `frontend/src/ui/components/` (`MetricCard`, `ChartCard`, `TableCard`, `ControlsCard`, `OptionsCard`, `ProgressCard`, `SandboxCard`, `SceneCard`, `CalloutCard`, `FollowUpCard`) devem compartilhar tokens visuais coesos (bordas, sombras, raios de borda, espaçamento interno e estados de *hover/focus*).
- [ ] **Renderização Progressiva Suave:** A chegada de eventos `ui_progress` e a hidratação final de `ui_blocks` no `stream_end` devem usar animações de entrada sutis (`fade-in` / `slide-up` de 150-200ms) e placeholders dimensionados para evitar saltos de tela.
- [ ] **Interatividade dos Blocos:** Cliques em `FollowUpCard` ou `OptionsCard` devem fornecer feedback tátil imediato (estado ativo/desabilitado após seleção quando apropriado) e disparar a ação correspondente de forma fluida.
- [ ] **Painel de Artefatos (`ArtifactPanel.tsx`):** Abertura/fechamento com transição suave; alternância limpa entre visualização renderizada (Preview) e código-fonte (Code); botões de copiar, baixar e expandir em tela cheia acessíveis e funcionais.
- [ ] **Internacionalização (i18n) e Acessibilidade (a11y):** Todos os rótulos estáticos, tooltips, avisos de erro (`CorrectionNotice.tsx`, `failover_notice`, `effort_dropped`) e atributos `aria-label` devem estar presentes e traduzidos corretamente nos **8 locales** suportados pelo projeto, além de suportar navegação básica por teclado (`Tab`, `Enter`, `Escape` para fechar o `ArtifactPanel`).

### CA-4: Preservação e Qualidade Geral
- [ ] **3 Níveis de Interface Intactos:** Verificar que os modos Simples, Intermediário e Avançado continuam funcionando exatamente como antes.
- [ ] **Zero Erros de Build e Testes:** `npm run build` passa sem erros de TypeScript; suíte `pytest` (em banco temporário) e testes de frontend passam com 100% de sucesso.

---

## O Loop de Autoaperfeiçoamento (Protocolo de Execução)

Você deve operar em ciclo fechado seguindo rigorosamente as 4 fases abaixo. **Não encerre sua execução nem peça confirmação humana antes de atingir 100% dos Critérios de Aceite.**

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    LOOP DE AUTOAPERFEIÇOAMENTO                          │
│                                                                         │
│   [1. Auditar & Planejar] ──► [2. Implementar Melhoria Cirúrgica]       │
│              ▲                                  │                       │
│              │                                  ▼                       │
│   [4. Refatorar / Corrigir] ◄── (Falhou) ── [3. Testar & Validar CAs]   │
│                                                 │                       │
│                                            (100% Verde)                 │
│                                                 ▼                       │
│                                      [Aprovar & Finalizar]              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Fase 1: Auditoria Focada
1. Inspecione `useChat.ts`, a store Zustand, `MessageBubble.tsx`, `ArtifactPanel.tsx`, `FusionStatusCard.tsx`, os componentes em `frontend/src/ui/components/` e os arquivos de tradução (8 locales).
2. Identifique lacunas visuais, gargalos de re-renderização durante o streaming de tokens, falhas de responsividade mobile/PWA ou ausências de feedback visual frente aos Critérios de Aceite (CA-1 a CA-4).

### Fase 2: Implementação Cirúrgica
1. Aplique as melhorias em lotes coesos e atômicos.
2. Mantenha o código limpo, fortemente tipado (sem `any` implícito) e aderente ao design system existente (Tailwind/CSS variables do projeto).
3. Nunca toque na lógica dos 3 Níveis de Interface nem viole a separação entre `isGeneratingRef` e `s.isGenerating`.

### Fase 3: Bateria de Testes e Validação (O Portão)
Execute os comandos de verificação nos ambientes apropriados:
1. **Compilação Estrita do Frontend:** Execute `npm run build` no diretório `frontend` (ou container correspondente). Verifique se há zero erros de TypeScript ou bundling.
2. **Testes Automatizados:** Execute os testes unitários/integração do frontend (incluindo os testes de paridade da Intelligent UI e ciclo de vida do `useChat`) e o `pytest` do backend usando banco SQLite temporário.
3. **Checklist de Critérios de Aceite:** Revise item por item de **CA-1**, **CA-2**, **CA-3** e **CA-4**.

### Fase 4: Decisão do Loop (Aprovar ou Repetir)
* **SE qualquer build falhar, qualquer teste quebrar, ou qualquer item de CA-1 a CA-4 não estiver impecável:**
  * Analise a causa raiz do erro ou da regressão.
  * Retorne imediatamente à **Fase 2**, corrija o problema e rode a **Fase 3** novamente. Repita quantas vezes forem necessárias.
* **SE E SOMENTE SE `npm run build` + testes estiverem 100% verdes E todos os Critérios de Aceite estiverem cumpridos:**
  * Prepare o resumo executivo das melhorias aplicadas.
  * Caso autorizado para deploy, execute estritamente o pipeline oficial do `AGENTS.md` (backup + integridade do DB $\rightarrow$ pull $\rightarrow$ build `--no-cache` $\rightarrow$ `up -d --force-recreate` $\rightarrow$ prune $\rightarrow$ healthcheck/logs).

---
**Inicie agora a Fase 1 do Loop de Autoaperfeiçoamento.**