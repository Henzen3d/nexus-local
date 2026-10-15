# Critérios de aceite

Lista para quem for ligar `INTELLIGENT_UI_ENABLED` no servidor da família. Item sem teste observado não conta como feito.

**Auditoria 2026-10-14.** Legenda: `[x]` = confirmado por teste automatizado ou leitura inequívoca do código; `[ ]` = pendente ou parcial (motivo entre parênteses). Nenhum item foi observado em browser nesta auditoria; os de UI foram conferidos no código, no `tsc` e no `vite build`. Evidências: `backend/tests/test_ui_blocks.py` (15 passed), `frontend/src/lib/nexusUi.test.ts` + `frontend/src/ui/lib/safeMath.test.ts` (11 passed), build limpo.

**Bloqueadores para ligar a flag em produção:** (1) a flag não desliga o recurso — ver seção *Flag*; (2) `set_model` ainda exibe options do modelo; (3) frontend não recebe a lista de hosts de imagem do servidor.

## Flag

- [x] Ausente no ambiente: chat idêntico ao de hoje, inclusive se o modelo escrever um fence. *(Corrigido 2026-10-14. `chat.py` lê a config efetiva por turno; sem flag não há catálogo, extração, linha em `message_ui_blocks` nem `stream_end.ui_blocks`. Frontend: `DynamicRenderer` devolve `null`, `MessageBubble` não reparseia (`extractClientUi` removido) e o fence aparece como bloco de código. Teste: `test_flag_desligada_turno_identico_ao_chat_sem_o_recurso`.)*
- [x] `false`: mesma coisa. *(Mesmo caminho: `config_from_env` trata ausente e `false` igual; painel pode ligar sem mexer no `.env`.)*
- [x] `true` em dev: blocos válidos pintam. Inválidos somem. A prosa fica. *(Código: validação dupla backend/frontend; bloco inválido é descartado individualmente; prosa limpa vai para `cleanedContent`. Não observado em browser nesta auditoria.)*

## Contrato

- [x] `v` diferente de 1 descarta o envelope. *(Corrigido nos dois lados: `v` presente e ≠ 1 (inclusive `null`) → `None`; `v` ausente continua tolerado. Testes `test_rejeita_v_diferente_de_1_mesmo_com_bloco_valido` e `v ausente assume 1; v null ou string estranha rejeita`.)*
- [x] Quinto bloco é ignorado. *(`blocks_raw[:MAX_BLOCKS]` / `slice(0, MAX_BLOCKS)`; verificado: 5 blocos → 4.)*
- [x] JSON acima de 16000 caracteres não grava linha em `message_ui_blocks`. *(`test_rejeita_acima_do_limite_tamanho`; `validate_envelope` retorna `None` → `save_ui_blocks` não insere.)*
- [x] `messages.content` de uma resposta com fence válido não contém `nexus-ui` nem o JSON. *(`test_tira_fence_e_deixa_prosa`, `test_fence_aberto_nao_grava_json`; `chat.py` grava `full_response` já limpo.)*
- [x] Recarregar a conversa mostra os mesmos blocos, lidos da tabela, não de um reparse frágil do markdown. *(`conversations.py` devolve `ui_blocks` por mensagem a partir de `message_ui_blocks`; `test_recuperacao_ui_blocks_em_conversa`. Ressalva: existe o reparse `extractClientUi` como fallback quando `ui_blocks` vem vazio.)*
- [x] Histórico mandado de volta ao modelo não inclui o payload. *(`chat.py` monta o histórico com `SELECT role, content FROM messages`; o payload mora em outra tabela.)*

## Por tipo

- [x] Progresso "Auditoria SEO" com value 7 e max 10 mostra a fração 7 de 10 e a barra. *(`ProgressCard.tsx` com `t('intelligentUi.progressOf')` e largura `(value/max)*100`, teto 100. Sem teste de render.)*
- [x] Dois `ui_progress` com o mesmo id: a tela fica com o segundo. *(`useStore.handleUiProgress` substitui por `id`. Sem teste de store; o backend ainda não emite o evento.)*
- [x] Cartão sem imagem não reserva um buraco de foto. *(`ImageCard.tsx`: o container da foto só monta se `isImgValid`.)*
- [x] `https://exemplo.com/a.jpg` não vai para o `<img>` se o host não está em `INTELLIGENT_UI_IMAGE_HOSTS`. *(Backend remove a imagem; frontend repete a checagem. Testado nos dois lados.)*
- [x] `/attachments/foto.jpg` e URL do próprio host podem ir para o `<img>`. *(Teste TS "filtro de imagens"; `ImageCard` passa `window.location.host`.)*
- [x] `http://192.168.0.20/foto.jpg` não passa com a flag privada desligada. Passa só com `INTELLIGENT_UI_ALLOW_PRIVATE_HTTP=true` (ou o toggle equivalente no painel). *(Corrigido: `ImageCard` usa `image_hosts`/`allow_private_http` vindos de `GET /api/intelligent-ui/config`; backend coberto por `test_filtro_imagem_usa_parametros_e_nao_env` e `test_painel_manda_sobre_env_e_lista_de_hosts_chega_ao_filtro`.)*
- [x] `javascript:` e `data:` não passam. *(Também `blob:` e `file:`; testado em Python e TS.)*
- [x] Erro de carga some com a foto e deixa título e fatos. *(`onError` → `setImgError(true)`.)*
- [x] `bar`, `line` e `compare` desenham com Recharts já instalado. Nenhum `npm install` novo. *(`ChartCard.tsx`; `package.json` sem dependência nova para o módulo.)*
- [x] `DynamicRenderer` não importa `recharts` de forma estática. `ChartCard` entra por `React.lazy`. *(Build gera `ChartCard-*.js` separado. Porém `recharts` em si continua no chunk principal por causa do `AdminPanel` estático — pendência do plano 04.)*
- [x] Não existe endpoint SSE novo para widget. *(Tudo passa pelo WebSocket de `chat.py`.)*
- [x] Tabela acessível do gráfico contém os números dos rows. *(`<table>` visualmente oculta com `caption`, `x_key` e todas as séries.)*
- [x] Controle não envia nada ao terminar o stream. *(Único disparo é `onSubmit` do `<form>`.)*
- [x] Slider (`range`) no controle atualiza o valor numérico em tempo real ao arrastar. *(`<strong>{val}</strong>` ao lado do `<input type="range">`.)*
- [x] Calculadora reativa (`computed`) recalcula a fórmula imediatamente no cliente sem fazer requisição ao servidor. *(`useMemo` + `evaluateSafeFormula`; `safeMath.test.ts` passa.)*
- [x] Clique em `send_message` cria bolha do usuário com o template preenchido (incluindo `{resultado}` calculado, se houver). *(`handleSubmit` interpola campos e `{resultado}` e chama `sendMessage` do `ChatContext`.)*
- [x] `set_model` não aceita id fora de `models`. Não usa as options que o modelo escreveu. *(Corrigido 2026-10-14: `ControlsCard` lista `models` do store, some com lista vazia e mostra erro curto para id desconhecido.)*
- [x] Bloco com `initial_height` reserva o espaço vertical antes do desenho final, prevenindo salto de scroll (Zero CLS). *(`SandboxCard` inicia `currentHeight = initial_height` (fallback 300) e depois auto-ajusta via `__nexus_ogui_resize`.)*
- [x] Na Fase 7 (quando sandbox estiver ativo): sandbox roda estritamente sem `allow-same-origin` e sincroniza o tema dark/light através do Theme Bridge. *(Corrigido 2026-10-14: `sandbox="allow-scripts allow-forms"` + CSP `default-src 'none'` (esm.sh só em `script-src`/`connect-src`); tema reativo por `postMessage` com `data-theme` + tokens de `getComputedStyle`, sem recarregar o iframe.)*
- [x] Exportação 1-click standalone (Fase 7) gera arquivo HTML autônomo funcional sem impactar o chat. *(`exportStandalone.ts`; Blob + `<a download>`; sem chamada ao backend. Sem teste automatizado.)*

## Plano 12 — passos 1 e 2 (2026-10-14)

- [x] `Origin` de outro site não abre `/ws/chat`: fecha com 4003 antes do `accept`; mesmo host e `ALLOWED_ORIGINS` passam; sem `Origin` passa. *(`backend/ws_origin.py`; `test_ws_origin.py` cobre os três caminhos e o handshake com `TestClient`.)*
- [x] CORS e WebSocket leem a mesma lista `ALLOWED_ORIGINS`. *(`main.py` usa `allowed_origins_from_env()`.)*
- [x] `metric` com 7 itens fica com 4; item sem `value`, com NaN ou booleano cai; `unit` só acompanha número. *(Testado em Python e TS.)*
- [x] `callout` com `kind` desconhecido vira `info`; sinônimos (`warn`, `error`, `note`, `ok`) mapeados; sem `body` cai. *(Idem.)*
- [x] `follow_up` escrito antes de outros blocos é pintado por último; o segundo `follow_up` cai; item com menos de 3 caracteres ou repetido cai. *(Idem.)*
- [x] Envelope com 7 blocos: só os 6 primeiros são olhados; terceiro `chart` e segundo `sandbox` caem; os demais seguem. *(Idem; `mergeUiEnvelopes`/`upsertUiBlock` usam `MAX_BLOCKS` exportado por `nexusUi.ts`.)*
- [x] Bloco sem `type` com `items` de textos vira `follow_up`, com `items` de `{label, value}` vira `metric`, com `kind` de callout e `body` vira `callout`. *(Idem.)*
- [x] `MetricCard`, `CalloutCard` e `FollowUpCard` renderizam sem erro em SSR e no showcase, em claro e escuro, de 320 a 900 px. *(Smoke manual; sem teste de DOM ainda.)*
- [x] Clique em sugestão de `follow_up` chama `sendMessage(texto)`; durante o stream os botões ficam desabilitados; nenhum envio automático. *(`FollowUpCard`; sem teste de DOM.)*
- [x] Catálogo com os três tipos continua sob 400 tokens (`len/4` ≈ 389) e o exemplo dele segue sendo um envelope válido. *(`test_catalogo_cabe_no_teto_e_tem_as_regras_da_spec`.)*
- [x] Strings novas (`metricUp/Down/Flat`, `calloutInfo/Success/Warning/Danger`, `followUpTitle/Hint`) nos oito idiomas. *(`check-i18n.mjs intelligentUi` OK.)*
- [ ] Teste de DOM (`test:dom`, plano 11 §4.5) para o clique do `follow_up` e a cor do delta por `trend × good`.

## Prompt

- [x] "bom dia" não injeta `catalog.txt`. *(`test_should_offer_ui_triggers`.)*
- [x] "compare os custos dos modelos" injeta, com a flag ligada. *(`test_should_offer_ui_triggers` + gate em `chat.py`.)*
- [x] "calcule a divisão da conta de 150 com 10% de gorjeta" ativa `controls` com `computed` ou catálogo. *(Regex `calcul` dispara o catálogo; `test_should_offer_ui_triggers` cobre "calcule a divisão da conta de 150 reais".)*
- [x] Catálogo acima de 400 tokens estimados (`len/4`) não é injetado. *(Checagem em `chat.py`; catálogo atual ≈ 277 tokens, com teto conferido por `test_catalogo_cabe_no_teto_e_tem_as_regras_da_spec`.)*
- [x] Há como medir se vale a pena manter ligado: oferecido / produzido / válido / descartado por motivo. *(`backend/ui_blocks/telemetry.py` + `GET /api/intelligent-ui/stats` (admin) + bloco no painel; `test_telemetria_conta_oferta_producao_validade_e_descartes`, `test_telemetria_motivos_de_descarte`.)*

## Acessibilidade e visual

- [x] Barra tem `role="progressbar"` quando há value e max. *(`ProgressCard.tsx`, com `aria-valuenow/min/max/label`; `ChecklistCard` usa `role="list"`.)*
- [x] Botão do controle mede pelo menos 44×44 px no breakpoint móvel. *(`minHeight: 44px`, largura total do cartão. Inputs têm 36 px de altura.)*
- [x] Com `prefers-reduced-motion: reduce`, a barra não anima em loop. *(Não há animação em loop; a transição de preenchimento (`.nexus-ui-progress-fill`) e o pulso do skeleton são desligados por media query em `index.css`, e o sandbox recebe a mesma regra no bridge.)*
- [x] Cores só dos tokens já existentes: `--surface-card`, `--hairline`, `--ink`, `--body`, `--primary`, `--cyan`, `--warning`, `--success`, `--error`. *(Também `--surface-soft` e `--canvas`, já existentes. Exceções pontuais: `#ffffff` no texto do botão de `ControlsCard` e sombras `rgba(0,0,0,…)`.)*
- [x] Transições de tema escuro/claro refletem instantaneamente nos cartões nativos e no sandbox bridge. *(Corrigido 2026-10-14: `useResolvedTheme` observa `data-theme`; o sandbox recebe `__nexus_theme` e troca o atributo do `<html>` interno, cujos tokens vêm por `html[data-theme]` no bridge.)*

## Internacionalização (i18n)

- [x] Todas as strings literais fixas dos componentes (`ProgressCard`, `ChecklistCard`, `ImageCard`, `ControlsCard`, `SandboxCard`) possuem chaves correspondentes em `pt-BR.json`, `en-US.json` e `es-ES.json` (conforme `AGENTS.md`). *(Bloco `intelligentUi` com 8 chaves nos três arquivos. `ChecklistCard` e `ImageCard` não têm string fixa. Restam fallbacks literais em português nos `||` de `ControlsCard`/`SandboxCard`.)*
- [x] Troca de idioma da interface reflete imediatamente nos textos de botões, tooltips e fallbacks de erro sem recarregar a conversa. *(`useTranslation()` nos componentes com texto.)*

## Não regressão

- [x] Artefato HTML continua no painel lateral, não dentro da bolha. *(`artifacts.py` só exclui `nexus-ui`/`nexus`/`nexus_ui` do detector genérico de código; fluxo de artefato intacto.)*
- [x] Fusion continua visível no cartão atual. *(`FusionStatusCard` e eventos `fusion_*` não foram tocados.)*
- [x] TTS lê a prosa, não um dump de JSON. *(`content` é gravado sem o fence.)*
- [x] Cache de resposta antiga, sem bloco, continua hit de texto. *(Cache não foi alterado; `extract_ui` roda também sobre resposta vinda do cache, sem efeito se não houver fence.)*

## Fora, de propósito

Pizza, vídeo, proxy de imagem, widget dentro do cache semântico e Thesys não são falha de aceite. Nas Fases 1 a 6, o foco é estritamente Nível 1 (Controlled Generative UI). A execução em sandbox Nível 2 é reservada para a Fase 7 pós-estabilização.



## Plano 12 — passo 4, laço de correção (2026-10-14)

- [x] APIs legadas dos validadores e contrato `nexus-ui/1` preservados; diagnósticos em API aditiva. Tipo desconhecido cai, id duplicado continua curado; versão inválida é rejeitada também no bloco solto e booleano não vira `1`.
- [x] Python/TS compartilham `backend/tests/fixtures/ui-errors.json`: mesmos códigos, contagem e limites para o mesmo JSON/fence; casos válidos, rejeições, mistura de válidos/inválidos, subtetos, imagem insegura e auto-healing. APIs detalhadas não alteram a entrada. *(`test_ui_diagnostics.py`, `nexusUiDiagnostics.test.ts`.)*
- [x] `stream_end.ui_errors` / `ui_dropped` só com flag ligada, incluindo rejeição total/JSON inválido; até 4 erros com mensagem ≤160. Prosa/envelope continuam sendo persistidos da mesma forma. *(`test_intelligent_ui_turn.py`.)*
- [x] Botão só com flag ligada e erro, nenhuma ação no mount, desabilitado no stream; clique envia mensagem visível pela mesma função `sendMessage` e consome uma oferta por mensagem; falha offline permite retry. Remount e runtime compartilham a trava. *(Testes do componente React real em `scripts/tests/correction.ui.tsx`, integrados a `npm test`; renderer, sem navegador/E2E.)*
- [x] Bootstrap do sandbox captura `error` / `unhandledrejection`, limita mensagem a 500 e confere a origem pela janela esperada; fonte estrangeira é ignorada. CSP e sandbox sem `allow-same-origin` preservados. *(Mesmo teste executa o script em VM e exercita o listener real.)*
- [x] Fluxo WS de oferta → pedido explícito → resposta corrigida conta `correction_valid`; replay não conta novo pedido. Endpoint runtime autenticado, dono obrigatório (404), flag e dedup. *(`test_intelligent_ui_turn.py`.)*
- [x] Telemetria guarda só contagens/códigos e IDs de correlação limitados a 2048; nunca texto/payload. Admin mostra taxas por modelo e aviso abaixo de 50%. *(`test_ui_diagnostics.py`; aviso no `IntelligentUiSettings`.)*
- [x] Oito chaves novas traduzidas em oito locales. Checker global não modificado; pendência preexistente de seis locales registrada separadamente na [issue #17](https://github.com/Henzen3d/nexus-local/issues/17).
- [ ] Smoke E2E em navegador real da aparência e do erro de iframe; os testes de componente/VM não substituem essa inspeção.

## Plano 12 — passo 5, tabela (`table`) e melhorias de gráfico (`pie`, `unit`, `stacked`) (2026-10-14)

- [x] Contrato `table`: 2 a 8 colunas tipadas (`text`, `number` com unit opcional, `date` ISO `YYYY-MM-DD`), até 50 linhas, ordenação opcional `sort: { key, dir: "asc"|"desc" }`.
- [x] Validação e auto-healing espelhados Python/TS: células de tipo incorreto viram `None`/`null` e renderizam `—` (sem descartar a linha inteira); colunas sem label usam a key; subteto de 1 `table` por envelope.
- [x] Inferência automática de bloco sem `type`: objeto com `columns` e `rows` é inferido como `table` nos dois validadores.
- [x] Catálogo modular: módulo `backend/ui_blocks/catalog_modules/table.txt` integrado, gatilhos de `should_offer` (`tabela`, `planilha`, etc.) e orçamento de tokens <= 450 respeitado em todas as combinações.
- [x] Gráficos de pizza (`kind: "pie"`): suportado com 1 série e de 2 a 8 linhas; agregação automática da 8ª linha em diante em fatia única nomeada `"Outros"`. Paleta harmônica `PIE_RAMP` / `pieColors` sem tokens inventados.
- [x] Melhorias de gráfico: suporte a `stacked: true` em `compare` com cálculo do domínio Y acumulado (`yDomainThroughZero`); suporte a `unit`, `x_label` e `y_label` em eixos e tooltips.
- [x] Exportação CSV: `tableToCsv` e `chartToCsv` para ação "Copiar dados" com escape correto de vírgulas, aspas e quebras de linha.
- [x] Componentes React: `TableCard` com `UiCard`, ordenação interativa por cabeçalho (`aria-sort`), números alinhados à direita com `tabular-nums`, colapso acima de 10 linhas ("Mostrar todas" / "Mostrar menos"); `ChartCard` com `PieChart`/`Pie`/`Cell` do Recharts, tooltip com porcentagem relativa e tabela acessível `nexus-ui-sr-only`.
- [x] i18n nos 8 idiomas: strings novas (`tableTitle`, `tableShowAll`, `tableShowLess`, `tableOthers`, `pieTotal`) traduzidas em `pt-BR`, `en-US`, `es-ES`, `es-419`, `fr-FR`, `de-DE`, `ja`, `ko`.

## Plano 12 — passo 6, renderização progressiva e partial JSON no stream (2026-10-14)

- [x] Scanner tolerante de stream (`nexusUiStream.ts`): autômato que extrai blocos fechados à medida que chegam na transmissão SSE e identifica `pendingType` quando o bloco iniciou `{ "type": "..."` mas ainda não fechou.
- [x] Invariante de prefixo validado: para qualquer prefixo de fence transmitido, os blocos extraídos são rigorosamente um prefixo da lista final de blocos, sem quebras nem divergências.
- [x] Tratamento robusto de cortes difíceis: chaves literais `}` dentro de strings e sequências de escape `\"` não corrompem o parsing nem geram blocos fantasmas.
- [x] Desativação de interatividade no stream: `ControlsCard` desabilita todos os inputs e submissões enquanto `streaming=true`; `FollowUpCard` desabilita cliques em sugestões durante o stream; `SandboxCard` mantém ações desabilitadas.
- [x] Prevenção de execução insegura e vazamento de iframes no stream: `SandboxCard` não monta o iframe com código JS parcial durante o stream (renderiza placeholder com altura reservada); o iframe só monta após o encerramento do turno.
- [x] Prevenção de Layout Shift (Zero CLS): `DynamicRenderer` exibe esqueleto com altura reservada correspondente ao `pendingType` antes mesmo do bloco fechar.
- [x] Integração completa no `StreamingBubble`: `scanPartialEnvelope(deferredResponse)` mesclado com blocos do host via `mergeUiEnvelopes`, sem exibir fences parciais na resposta markdown (`stripUiFences`).
- [x] Testes automatizados: testes unitários de autômato e propriedade em `nexusUiStream.test.ts` e testes de UI de componentes em `scripts/tests/stream.ui.tsx`, integrados ao runner `npm test`.

## Plano 12 — passo 7, enquetes e alternativas (`options`) (2026-10-14)

- [x] Contrato `options`: `question` (1 a 160 caracteres), `options` (2 a 6 itens, cada qual com `label` de 1 a 80 caracteres e `description` opcional até 160), `mode: "single" | "multiple"` (padrão `"single"`), `allow_other: boolean` (padrão `false`), `action: { type: "send_message", text_template: string }` onde `text_template` obrigatoriamente contém o placeholder `{choice}`.
- [x] Validação e auto-healing espelhados Python/TS: preenchimento automático de `value` omitido a partir de `id` ou `label`; rejeição estrita se menos de 2 ou mais de 6 opções; rejeição se `text_template` não contiver `{choice}`; subteto estrito de no máximo 1 bloco `options` por envelope.
- [x] Inferência de bloco sem `type`: objeto com `question` e `options` é inferido de forma determinística como bloco `options`.
- [x] Catálogo modular e gatilhos: módulo compacto `backend/ui_blocks/catalog_modules/options.txt` (170 caracteres / ~43 tokens) adicionado; gatilhos em `should_offer.py` cobrindo termos de escolha, seleção, enquete e alternativas.
- [x] Componente React `OptionsCard`: casca `UiCard` acessível, layout em grade responsiva `.nexus-ui-options__grid` com cards selecionáveis `.nexus-ui-option-card`.
- [x] Envio por gesto explícito do usuário:
  - No modo `single` sem `allow_other`: toque direto em uma opção despacha a resposta imediatamente pelo `onSendMessage`.
  - No modo `multiple` ou ao utilizar `allow_other`: botão primário "Enviar resposta" exige confirmação explícita do usuário.
- [x] Bloqueio e estado pós-submissão: uma vez enviada a resposta, as opções ficam travadas (`data-submitted="true"`), com badge de check exibindo a escolha (`optionsAnswered`).
- [x] Respeito à transmissão de stream: prop `streaming?: boolean` desabilita interações prematuras antes do envelope fechar.
- [x] i18n completo: 5 novas chaves (`optionsSingleHint`, `optionsMultipleHint`, `optionsOther`, `optionsSubmit`, `optionsAnswered`) rigorosamente traduzidas em todos os 8 idiomas (47 chaves totais em `intelligentUi`).
- [x] Testes de paridade e UI: 5 novos testes em `test_ui_blocks.py`, testes unitários em `nexusUi.test.ts`, e testes com `react-test-renderer` em `scripts/tests/options.ui.tsx` cobrindo envio imediato, múltipla seleção, campo outro e stream.
## Plano 12 — passo 8, estado compartilhado e expressões no safeMath (2026-10-15)

- [x] Gramática matemática segura e estrita: gramática com operadores `+`, `-`, `*`, `/`, parênteses, números e variáveis `{id}` de até 32 caracteres alfanuméricos/underscore. Operador `^` expressamente proibido para evitar ambiguidades de precedência.
- [x] Funções matemáticas permitidas: suporte canônico a `round(x, casas)`, `pow(x, y)`, `abs(x)`, `floor(x)`, `ceil(x)`, `sqrt(x)`, `min(...)`, `max(...)`. Aridade validada estaticamente nos validadores.
- [x] Divisão por zero segura: expressões com divisão por zero avaliam para 0 sem lançar erros ou quebrar a interface.
- [x] Fixtures compartilhadas e paridade Python/TS: `backend/tests/fixtures/expressions.json` com 17 casos canônicos lido e testado em paridade estrita nos dois ambientes (`test_ui_expr.py` e `safeMath.test.ts`).
- [x] Ordenação topológica e detecção de ciclos: `check_dependency_cycles` analisa dependências entre computeds de `controls`, detecta dependências circulares com algoritmo DFS tricolor e retorna ordenação topológica para cálculo encadeado correto.
- [x] Validação estática de variáveis contra o envelope: expressões em `metric`, `card`, `progress`, `table` e `chart` validadas estaticamente contra os IDs de campos e computeds conhecidos de blocos `controls` presentes no mesmo envelope.
- [x] Detecção de colisão de campos de controles: dois blocos `controls` no mesmo envelope com IDs repetidos geram `duplicate_id` e o bloco conflitante é descartado.
- [x] Store reativo isolado por mensagem: `useMessageUiStore` com escopo estrito por `messageId` (`states[messageId][fieldId]`), prevenindo vazamento de estado entre mensagens da conversa. Hook `useResolvedValue(messageId, rawValue)` memoizado para reavaliação instantânea.
- [x] Interação em tempo real: alteração de sliders ou campos numéricos em `ControlsCard` recalcula e atualiza instantaneamente `MetricCard`, `ProgressCard`, células numéricas de `TableCard` e séries de `ChartCard`.
- [x] Estabilidade visual e Zero CLS no Recharts: detecção de expressões dinâmicas em `ChartCard` forçando `isAnimationActive={false}` para eliminar saltos e animações acumuladas ao arrastar sliders.
- [x] Acessibilidade: `ProgressCard` com expressão reativa mantém `aria-valuenow` numérico sincronizado com o valor calculado.
- [x] Testes automatizados: 525 testes backend aprovados em pytest, 129 testes unitários frontend e teste de UI reativa real (`reactive.ui.tsx`) validando a cadeia interativa completa.

## Plano 13 — Cenas 2D e 3D interativas em sandbox local (`sandbox` com `kind: "scene"`) (2026-10-15)

- [x] Isolamento total de Three.js: `three` instalado estritamente como `devDependency` e empacotado em bundle isolado `public/scene/runtime.js` via `vite.scene.config.ts`. O bundle principal do aplicativo React não importa Three.js (`dist/assets/index-*.js` permanece inalterado).
- [x] Runtime local e sem rede: runtime expõe `NexusScene = { setup, start }`, gerenciando palcos 3D (Three.js `Scene`, `PerspectiveCamera`, luzes, `WebGLRenderer`, `CSS2DRenderer`, `OrbitControls`) e palcos 2D (`Canvas` 800×450 letterboxed com `ctx`), relógio com passo máximo de 50ms (`MAX_STEP = 0.05`) e `reporter` com throttle a 100ms.
- [x] Protocolo estrito app ↔ cena: `sceneProtocol.ts` com mensagens tipadas `__nexus_scene_params`, `__nexus_scene_pause`, `__nexus_scene_play`, `__nexus_scene_theme`, `__nexus_scene_ready`, `__nexus_scene_report` e `__nexus_scene_error`. `readSceneMessage` sanitiza todos os payloads e descarta lixo fora do protocolo.
- [x] CSP estrita sem rede e proteção contra escape: `sceneDocument.ts` gera `srcdoc` com `default-src 'none'`, `script-src 'unsafe-inline' /scene/runtime.js` e `style-src 'unsafe-inline'`. `escapeScript` transforma `</script>` e `<!--` com segurança. Segundo `load` do iframe é bloqueado e exibe aviso de sandbox.
- [x] Validação e auto-healing espelhados Python/TS:
  - Verificação de termos proibidos (`while`, `import`, `fetch`, `WebSocket`, `XMLHttpRequest`, `document.cookie`, `localStorage`, `window.parent`, `postMessage`, `eval`, `Function(`) retornando código de diagnóstico `invalid_scene_code`.
  - Tetos de código: máximo 6000 caracteres e máximo 120 linhas.
  - Validação estrita de `params` (range, number, select) com `default` obrigatório e IDs únicos (máximo 4 parâmetros).
  - Validação de `readout` com chaves válidas e sem repetição (máximo 6 leituras).
  - Subteto estrito de no máximo 1 bloco `sandbox` por envelope.
  - Inferência automática: objetos sem `type` com `code` (e sem `html`) inferidos como `sandbox`.
- [x] Componente `SceneCard`:
  - Casca `UiCard as="figure" variant="flush"` com ícones de modo (`Orbit` para 3D e `PenTool` para 2D).
  - Ações no cabeçalho: Pausar/Continuar, Reiniciar, Tela cheia (via `requestFullscreen` no card) e Baixar HTML (quando `standalone_download !== false`).
  - Layout responsivo: no desktop, palco principal com barra lateral de 200px para parâmetros; no mobile, controles dispostos abaixo do palco.
  - Faixa de leitura `readout` com `tabular-nums` e tabela oculta `sr-only` para acessibilidade em leitores de tela.
  - Estado compartilhado reativo: leituras recebidas por `__nexus_scene_report` publicam em `useMessageUiStore` como `sim.<key>` e `<key>` para consumo por outros blocos do envelope.
- [x] Respeito a movimento e visibilidade:
  - `prefers-reduced-motion` monta a cena pausada (`setup.paused = true`) e exibe o botão "Continuar".
  - `visibilitychange` pausa a animação quando a aba fica oculta.
  - `useSceneViewport` com `rootMargin: '100% 0px'` desmonta o iframe quando o usuário rola para longe (liberando contextos WebGL escassos) e remonta com os parâmetros atuais ao retornar.
- [x] Tratamento de erros e laço de autocorreção: faixa de erro exibe mensagem capturada e botão "Pedir correção" envia prompt estruturado ao chat com título da cena e erro formatado. Erro de `webglcontextlost` oferece reinicialização direta.
- [x] Exportação standalone autônoma: `downloadStandaloneSceneHtml` / `assembleStandaloneSceneHtml` embute o runtime.js completo lido localmente diretamente em `<script>`, setup inicial com parâmetros atuais e código da cena, permitindo funcionamento 100% offline em qualquer navegador.
- [x] Catálogo modular e telemetria: módulo `backend/ui_blocks/catalog_modules/scene.txt` adicionado; gatilhos em `should_offer.py` (`órbita`, `pêndulo`, `partícula`, `passo a passo animado`); telemetria de eventos `scene_mounted`, `scene_error` e `scene_fix_requested` em `telemetry.py` e endpoint `/api/intelligent-ui/scene-event`.
- [x] Fixtures canônicas: 6 cenas canônicas implementadas em `frontend/src/ui/scene/__fixtures__/fixtures.ts` (< 60 linhas cada): órbita com velocidade (3D), pêndulo simples (2D), ordenação bubble sort (2D), partículas com atrito (3D), gráfico de superfície (3D) e relógio analógico (2D).
- [x] i18n rigoroso: 6 novas chaves traduzidas em todos os 8 locales (total de 53 chaves em `intelligentUi` validadas por `check-i18n.mjs`).
- [x] Testes automatizados: 529 testes pytest aprovados no backend, 134 testes unitários e 12 testes de UI no frontend (146 testes frontend totais), TypeScript com 0 erros e compilação de produção limpa.
