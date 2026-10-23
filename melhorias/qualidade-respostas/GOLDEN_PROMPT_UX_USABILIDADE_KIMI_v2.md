# GOLDEN PROMPT: Ciclo de Autoaperfeiçoamento de UX/UI e Confiabilidade de Streaming — Nexus Local

## Para

Agente Executor Autônomo de Engenharia Frontend/Fullstack, especialista em React, TypeScript, Zustand, WebSockets, testes e UX/UI de chat com IA.

## Objetivo

Elevar a UX/UI do **Nexus Local** (`multi.mob.tec.br`, PWA) a um padrão de excelência, fluidez e legibilidade comparável ao de produtos líderes, sem copiar interfaces ou promover redesenhos desnecessários.

Como o produto agrega modelos gratuitos via OpenRouter e provedores diretos, sujeitos a latência variável e failover durante o streaming, a interface deve transmitir confiabilidade: resposta imediata às ações, ausência de travamentos e de conteúdo híbrido, Markdown resiliente, transições discretas, Intelligent UI consistente e artefatos funcionais em desktop e mobile.

Opere em ciclos de auditoria, implementação, validação e correção. **Preserve o que já atende aos critérios:** não reescreva arquitetura nem faça alterações cosméticas sem uma lacuna ou regressão demonstrada.

---

## Regras Férreas do Projeto — Inegociáveis

1. **Três Níveis de Interface congelados:** o sistema em *Configurações > Preferências* está aprovado. É proibido alterar sua lógica, visibilidade, defaults ou comportamento:
   - **Simples:** oculta seletores manuais e ativa o smart router.
   - **Intermediário:** permite troca rápida de modelo.
   - **Avançado:** libera provedores e controle de esforço.  
   Nenhuma melhoria deste ciclo pode introduzir seletores, preferências ou comportamentos que contornem esses níveis.

2. **Docker Compose, portas e Nginx:** utilize estritamente a topologia e os procedimentos do Docker Compose/`AGENTS.md`. A porta `8000` do host pertence ao Portainer; testes de aplicação devem ocorrer nos containers ou na rede interna Docker, sem publicar ou redirecionar essa porta. O Nginx deve permanecer exclusivamente em IPv4, conforme a configuração vigente (`127.0.0.1`; nunca substituir por `localhost` ou IPv6).

3. **Proteção do banco vivo:** é proibido ler, alterar, apagar, reindexar ou executar testes contra `backend/nexuslocal.db`. Testes de backend devem usar exclusivamente SQLite temporário ou em memória, descartável.

4. **Restrição semântica:** é proibido mencionar, invocar ou reindexar `GitNexus` em arquivos do projeto, logs, comentários ou commits.

5. **Quality gate:** nenhuma iteração pode ser aprovada sem:
   - `npm run build` com código de saída `0`, sem erros de TypeScript ou bundling e sem novos warnings introduzidos para contornar problemas;
   - `pytest` com código de saída `0`, usando banco temporário;
   - todos os testes de frontend existentes e adicionados passando.  
   É proibido apagar testes, enfraquecer assertions, atualizar snapshots para aceitar regressão ou adicionar `skip`/`xfail` para obter um gate artificialmente verde. Ausência de script ou de runner não significa sucesso.

6. **Preservação de contratos e paridade:** não altere o protocolo WebSocket, o catálogo de blocos ou o comportamento dos artefatos apenas para obter efeitos visuais. Preserve a paridade da Intelligent UI e todos os eventos já suportados. Correções pontuais de backend só são permitidas quando um teste demonstrar violação dos invariantes de streaming, mantendo o contrato existente.

7. **Deploy não é automático:** somente execute deploy quando houver autorização explícita. Nesse caso, siga exclusivamente o pipeline oficial: backup e verificação de integridade do DB → `git pull` → `docker compose build --no-cache` → `docker compose up -d --force-recreate` → `docker system prune` → healthchecks e logs. Após o deploy, valide o PWA considerando Service Worker e cache, com hard refresh/renovação limpa dos assets em sessão de teste.

---

## Diagnóstico Técnico — Proteção Contra Regressão

### 1. Failover mid-stream sem “splicing” sujo

**Problema anterior:** o Modelo A emitia tokens parciais, falhava e o Modelo B concatenava sua resposta ao rascunho de A, produzindo texto híbrido e corrompido.

**Invariantes obrigatórios:**

- Quando houver failover após emissão de tokens, o backend deve emitir `stream_clear` antes da nova tentativa; também deve limpar o rascunho antes de erro terminal, conforme o fluxo já corrigido.
- O handler de `stream_clear` em `useChat.ts` deve chamar `clearStreamDraft`, zerando `streamingContent` e `streamingUiBlocks` **sem finalizar a mensagem nem encerrar o turno**.
- O modelo de fallback deve recomeçar visualmente do zero. Nenhum fragmento do modelo anterior pode permanecer na bolha ou nos blocos provisórios.
- `failover_notice` deve gerar feedback discreto e compreensível, sem interromper o novo streaming. A ordem desse aviso em relação aos demais eventos deve seguir a emissão real; não reordene eventos para satisfazer testes.
- O `stream_end` final deve encerrar o turno uma única vez e aplicar os metadados e blocos finais correspondentes à resposta efetivamente servida.

### 2. Separação entre ciclo de vida do turno e indicador visual

**Problema anterior:** o primeiro evento `token` atribuía `false` a `isGeneratingRef.current`, fazendo o frontend descartar tokens subsequentes e, em alguns fluxos, o próprio `stream_end`.

**Invariantes obrigatórios:**

- `isGeneratingRef.current` controla o **ciclo de vida lógico do turno** e deve permanecer `true` durante todo o streaming.
- Ele só pode passar a `false` em: `stream_end`, erro fatal, `onclose` do WebSocket ou ação explícita de `stopStream`.
- Handlers intermediários — incluindo `token`, `stream_clear`, `search_start`, `process_step_*`, `ui_progress` e `fusion_*` — não podem encerrar o turno.
- Esses eventos podem alterar apenas o estado visual `s.isGenerating`, por exemplo, para ocultar o spinner inicial quando houver conteúdo ou etapas a exibir.
- `stream_clear` limpa o rascunho, mas não equivale a `stream_end`, cancelamento ou erro terminal.

---

## Estado Atual da Arquitetura de UI

- **WebSocket:** o protocolo em `frontend/src/types.ts` cobre streaming (`stream_start`, `stream_clear`, `token`, `stream_end`), etapas e busca (`process_step_start/update/end`, `search_start`), fusão (`fusion_*` via `FusionStatusCard.tsx`), roteamento e failover (`auto_route_decision`, `failover_notice`, `effort_dropped`) e geração de imagens (`image_pending`, `image_ready`, `image_failed`).
- **Intelligent UI:** planos 1–13 concluídos, com paridade para `metric`, `callout`, `follow_up`, `table`, `chart`, `options`, `progress`, `card`, `controls`, `sandbox`, além de `scene` 2D/3D, `checklist` e `image`.
- **Componentes:** `frontend/src/ui/components/` contém `CalloutCard`, `ChartCard`, `ChecklistCard`, `ControlsCard`, `CorrectionNotice`, `FollowUpCard`, `ImageCard`, `MetricCard`, `OptionsCard`, `ProgressCard`, `SandboxCard`, `SceneCard`, `TableCard` e `UiCard`.
- **Renderização progressiva:** `ui_progress` durante o stream e `ui_blocks` no `stream_end`, com diagnósticos de auto-correção via `ui_errors` e `CorrectionNotice.tsx`.
- **Markdown e artefatos:** `MessageBubble.tsx` usa `react-markdown` + `remark-gfm`; artefatos `html`, `markdown`, `svg`, `code` e `jsx` são apresentados em `ArtifactPanel.tsx`.

---

## Escopo e Critérios de Aceite Testáveis

O escopo compreende streaming, scroll, feedback de espera, `MessageBubble.tsx`, componentes da Intelligent UI, `ArtifactPanel.tsx`, i18n e acessibilidade dos fluxos afetados. Não inclui novos provedores, novos níveis de interface, troca de stack ou redesenho global.

Cada item só pode ser marcado como concluído com evidência: teste automatizado, comando e código de saída, ou validação em execução com resultado observável. Inspeção estática, isoladamente, não aprova critérios visuais ou de interação. Se um item já estiver atendido, preserve a implementação e registre a evidência.

### CA-1 — Confiabilidade e fluidez de streaming

- [ ] **Ciclo de vida do turno:** testes dos handlers demonstram que eventos intermediários nunca atribuem `false` a `isGeneratingRef.current`. Os quatro encerramentos permitidos são testados: `stream_end`, erro fatal, `onclose` e `stopStream`.
- [ ] **Failover limpo:** reproduzir um turno em que A emite texto e blocos provisórios, ocorre `stream_clear` com `failover_notice`, e B emite uma nova resposta até `stream_end`. O resultado final deve conter somente B; `streamingContent` e `streamingUiBlocks` devem ter sido zerados; a mensagem não pode ter sido finalizada no clear; não pode haver overflow horizontal, bolha duplicada ou aviso quebrando o layout.
- [ ] **Erro terminal e limpeza:** após a sequência de limpeza e erro fatal, o rascunho parcial não pode permanecer apresentado como resposta concluída; o erro deve ser exibido e o ciclo lógico deve terminar.
- [ ] **Smart Scroll Anchor:** utilize o limiar já existente no projeto; se não houver um, adote e documente um único limiar de **100 px** da base. Enquanto o usuário estiver dentro do limiar, tokens e blocos mantêm a leitura ancorada no final. Se ele rolar para cima e sair do limiar, novos eventos não alteram sua posição de leitura e surge o botão discreto “Ir para o final”. O botão desaparece ao retornar à base e, quando acionado, rola até o final e reativa a ancoragem.
- [ ] **Feedback de espera:** após o envio, há indicador imediato até a chegada de conteúdo ou etapas. `process_step_*`, `search_start` e `fusion_*` não deixam a interface sem estado nem encerram o turno. A substituição do placeholder pelo primeiro token não desloca o composer, o cabeçalho ou mensagens anteriores e não introduz overflow; apenas a área da resposta cresce conforme necessário.
- [ ] **Estabilidade de renderização:** mensagens anteriores mantêm keys estáveis e não são desmontadas a cada token. Não deve haver fila de animações de scroll ou remontagem da bolha ativa a cada fragmento.

### CA-2 — Organização visual e tipografia em `MessageBubble.tsx`

- [ ] **Hierarquia tipográfica:** texto corrido usa `line-height` entre `1,5` e `1,75`, salvo token tipográfico equivalente já adotado e documentado. Parágrafos, listas e listas aninhadas têm espaçamento consistente; `h1–h4` apresentam hierarquia visual não crescente e distinguível do corpo. Validar em viewport móvel de **360 px de largura** e em desktop, sem overflow ou sobreposição.
- [ ] **Blocos de código:** todo bloco `pre/code` possui cabeçalho sempre presente com a linguagem informada ou rótulo neutro quando ela estiver ausente. O botão “Copiar código” copia somente o código, apresenta confirmação visual por **2.000 ms** e depois retorna ao estado inicial. Falha da Clipboard API não pode exibir falso sucesso.
- [ ] **Código sem estouro:** linhas longas usam scroll horizontal isolado no bloco. Em 360 px, o bloco não aumenta a largura da `MessageBubble` nem produz scroll horizontal no documento. O cabeçalho e o botão permanecem utilizáveis no mobile.
- [ ] **Tabelas GFM:** tabelas são envolvidas por container com `overflow-x: auto`, cabeçalho destacado, bordas discretas e zebra striping sutil baseada nos tokens do projeto. Uma tabela larga pode rolar dentro do wrapper, mas `document.documentElement.scrollWidth` não pode exceder sua largura de viewport por causa dela.
- [ ] **Markdown parcial resiliente:** testar prefixos de stream com fence de código aberto, tabela incompleta, lista e ênfase incompletos. Nenhum prefixo pode lançar exceção, desmontar toda a bolha, criar overflow horizontal ou alternar nodes estáveis sem necessidade. Ao chegar o fechamento e o `stream_end`, a renderização final deve ser semanticamente correta.

### CA-3 — Intelligent UI e `ArtifactPanel.tsx`

- [ ] **Consistência visual:** produzir uma matriz de auditoria dos componentes de `ui/components/`, cobrindo container, borda, raio, sombra, padding e estados interativos. Cores, sombras e raios devem usar os tokens/CSS variables existentes quando houver equivalente; exceções precisam de justificativa. Apenas elementos interativos recebem affordances de hover, focus e disabled.
- [ ] **Progressão sem duplicação:** eventos repetidos ou sucessivos para o mesmo bloco são reconciliados por identidade, sem cards duplicados. A hidratação de `ui_blocks` no `stream_end` não duplica o progresso provisório nem reinicia desnecessariamente um estado interativo já válido. `stream_clear` continua removendo os blocos provisórios.
- [ ] **Animações e placeholders:** entradas usam `fade-in`/`slide-up` discreto de **150–200 ms**, sem animação de todo o histórico. Placeholders preservam dimensões conhecidas ou uma altura mínima estável. Com `prefers-reduced-motion: reduce`, animações não essenciais são removidas ou reduzidas.
- [ ] **Interatividade:** `FollowUpCard` e `OptionsCard` respondem imediatamente a clique e teclado, disparam a ação existente uma única vez e impedem envio duplicado enquanto a mesma ação estiver pendente. Estados ativo/desabilitado só são usados quando compatíveis com a semântica do bloco; opções reutilizáveis não podem ser desabilitadas permanentemente sem motivo.
- [ ] **Artefatos:** abrir, fechar, alternar Preview/Code, copiar, baixar e expandir/retornar da tela cheia funcionam sem perder o artefato selecionado. Copiar usa o código-fonte; baixar preserva o conteúdo e gera nome/extensão coerentes com o tipo; as transições respeitam redução de movimento.
- [ ] **Teclado e foco:** todos os controles dos fluxos alterados são alcançáveis por `Tab` e acionáveis pelo teclado. `Escape` fecha o `ArtifactPanel` quando aplicável, sem apagar texto do composer; ao fechar, o foco retorna ao acionador, se ele ainda existir. Botões somente com ícone possuem nome acessível e foco visível.
- [ ] **i18n completo dos fluxos em escopo:** enumerar os locales na configuração de i18n durante a auditoria, sem presumir quantidade, e validar todos eles. Não adicionar nem remover idiomas. Rótulos estáticos, tooltips, estados de cópia, botões e avisos de `CorrectionNotice`, `failover_notice` e `effort_dropped` não podem exibir chaves cruas ou texto hardcoded novo. Nomes de modelos e diagnósticos recebidos como dados devem ser preservados; rótulos e razões mapeáveis devem ser localizados, sem inventar tradução para payload técnico.

### CA-4 — Preservação e qualidade geral

- [ ] **Níveis intactos:** validar em execução que Simples continua sem seletores manuais e com smart router; Intermediário mantém a troca rápida; Avançado mantém provedores e esforço. Nenhum controle ou comportamento novo pode alterar esses modos.
- [ ] **Paridade preservada:** todos os tipos de bloco, componentes, eventos de fusão, artefatos e diagnósticos anteriores continuam disponíveis. Testes de paridade existentes permanecem verdes.
- [ ] **Responsividade e ausência de erros:** os fluxos alterados são validados em 360 px e desktop, sem overflow horizontal da página, erros de renderização ou exceções no console atribuíveis às mudanças.
- [ ] **Gate completo:** build, testes de frontend e `pytest` estão verdes após a última alteração. O relatório registra comandos, ambiente e códigos de saída; nenhum teste usa o banco vivo.
- [ ] **Diff controlado:** as mudanças finais estão relacionadas às lacunas auditadas, sem formatação massiva, arquivos gerados acidentais ou refatorações não relacionadas.

---

## Loop de Autoaperfeiçoamento — Protocolo de Execução

Não peça confirmação humana para auditar, implementar ou testar. Continue o ciclo até obter **APROVADO** ou até identificar um **BLOQUEADO** real de ambiente/dependência externa. Nunca converta validação não executada em aprovação.

```text
[1. Auditar e estabelecer baseline]
                  │
                  ▼
[2. Implementar um lote cirúrgico + testes]
                  │
                  ▼
[3. Executar testes, build e validar CAs]
                  │
        ┌─────────┴─────────┐
        │                   │
   qualquer falha       tudo verde e evidenciado
        │                   │
        ▼                   ▼
[4. Causa raiz/correção]  [Aprovar e relatar]
        │
        └────────► retornar à Fase 2
```

### Fase 1 — Auditoria focada e baseline

1. Inspecione `useChat.ts`, a store Zustand, `MessageBubble.tsx`, `ArtifactPanel.tsx`, `FusionStatusCard.tsx`, `ui/components/`, estilos/tokens e a fonte de verdade de i18n.
2. Execute o baseline do build e dos testes antes de alterar código. Registre falhas pré-existentes separadamente; não as atribua às suas mudanças nem as oculte.
3. Inventarie os locales configurados e os testes disponíveis. Identifique lacunas por CA, priorizando regressões de streaming e erros funcionais antes de polimento estético.
4. Se todos os critérios já estiverem comprovadamente atendidos, não faça mudanças cosméticas: execute o gate completo e finalize com as evidências.

### Fase 2 — Implementação cirúrgica

1. Trabalhe em lotes pequenos e coesos, cada um associado a uma lacuna identificada.
2. Adicione ou ajuste testes junto da correção, especialmente para sequências WebSocket, Markdown parcial, reconciliação de blocos e interações de cópia/teclado.
3. Mantenha TypeScript estrito, sem `any` implícito ou supressões injustificadas. Reutilize Tailwind, CSS variables, componentes e padrões já existentes; não troque a stack nem adicione dependência para resolver algo trivial.
4. Preserve rigorosamente os três níveis, o contrato WebSocket e a separação `isGeneratingRef`/`s.isGenerating`.

### Fase 3 — Testes e validação

1. Execute testes focados após cada lote.
2. Antes da aprovação, execute novamente, após a última alteração:
   - `npm run build` no ambiente previsto pelo projeto;
   - toda a suíte de frontend configurada, incluindo paridade da Intelligent UI e ciclo de vida de `useChat`;
   - `pytest` com SQLite temporário/em memória.
3. Valide em execução, no mínimo:
   - turno normal com Markdown e `stream_end`;
   - failover após tokens, com limpeza e resposta única do fallback;
   - scroll ancorado e leitura manual acima da base;
   - Markdown parcial, código e tabela largos em 360 px;
   - `ui_progress` seguido de `ui_blocks`, sem duplicação;
   - artefato com Preview/Code, copiar, baixar, tela cheia e teclado;
   - os três níveis de interface sem alteração.
4. Revise CA-1 a CA-4 item por item e associe evidências. Se uma ferramenta necessária para validar um critério visual estiver indisponível, não marque esse item como aprovado.

### Fase 4 — Decisão e encerramento

- **Se houver falha de build, teste, regressão ou CA sem evidência:** identifique a causa raiz, reverta apenas o lote defeituoso quando necessário e retorne à Fase 2. Não contorne a falha alterando o teste para aceitar o comportamento incorreto.
- **Se houver impedimento externo ou de ambiente:** encerre de forma controlada com status **BLOQUEADO**, informando o que foi executado, a evidência do impedimento, o estado do código e o próximo passo. Não declare aprovação parcial.
- **Se e somente se todos os gates e CAs estiverem verdes:** finalize com status **APROVADO** e um resumo executivo contendo:
  1. lacunas encontradas e melhorias aplicadas;
  2. arquivos alterados;
  3. comandos executados e resultados;
  4. checklist dos CAs com evidências;
  5. confirmação explícita de não regressão dos invariantes e dos três níveis;
  6. riscos ou pendências remanescentes, se houver.
- Deploy permanece condicionado à autorização explícita e ao pipeline oficial. Sem essa autorização, apenas informe que o código está validado e que o deploy não foi executado.

**Inicie agora a Fase 1 do Loop de Autoaperfeiçoamento.**