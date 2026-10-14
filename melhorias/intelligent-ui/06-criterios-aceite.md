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

