# Critérios de aceite

Lista para quem for ligar `INTELLIGENT_UI_ENABLED` no servidor da família. Item sem teste observado não conta como feito.

## Flag

- [ ] Ausente no ambiente: chat idêntico ao de hoje, inclusive se o modelo escrever um fence.
- [ ] `false`: mesma coisa.
- [ ] `true` em dev: blocos válidos pintam. Inválidos somem. A prosa fica.

## Contrato

- [ ] `v` diferente de 1 descarta o envelope.
- [ ] Quinto bloco é ignorado.
- [ ] JSON acima de 16000 caracteres não grava linha em `message_ui_blocks`.
- [ ] `messages.content` de uma resposta com fence válido não contém `nexus-ui` nem o JSON.
- [ ] Recarregar a conversa mostra os mesmos blocos, lidos da tabela, não de um reparse frágil do markdown.
- [ ] Histórico mandado de volta ao modelo não inclui o payload.

## Por tipo

- [ ] Progresso "Auditoria SEO" com value 7 e max 10 mostra a fração 7 de 10 e a barra.
- [ ] Dois `ui_progress` com o mesmo id: a tela fica com o segundo.
- [ ] Cartão sem imagem não reserva um buraco de foto.
- [ ] `https://exemplo.com/a.jpg` não vai para o `<img>` se o host não está em `INTELLIGENT_UI_IMAGE_HOSTS`.
- [ ] `/attachments/foto.jpg` e URL do próprio host podem ir para o `<img>`.
- [ ] `http://192.168.0.20/foto.jpg` não passa com a flag privada desligada. Passa só com `INTELLIGENT_UI_ALLOW_PRIVATE_HTTP=true`.
- [ ] `javascript:` e `data:` não passam.
- [ ] Erro de carga some com a foto e deixa título e fatos.
- [ ] `bar`, `line` e `compare` desenham com Recharts já instalado. Nenhum `npm install` novo.
- [ ] `DynamicRenderer` não importa `recharts` de forma estática. `ChartCard` entra por `React.lazy`.
- [ ] Não existe endpoint SSE novo para widget.
- [ ] Tabela acessível do gráfico contém os números dos rows.
- [ ] Controle não envia nada ao terminar o stream.
- [ ] Clique em `send_message` cria bolha do usuário com o template preenchido.
- [ ] `set_model` não aceita id fora de `models`. Não usa as options que o modelo escreveu.

## Prompt

- [ ] "bom dia" não injeta `catalog.txt`.
- [ ] "compare os custos dos modelos" injeta, com a flag ligada.
- [ ] Catálogo acima de 400 tokens estimados (`len/4`) não é injetado.

## Acessibilidade e visual

- [ ] Barra tem `role="progressbar"` quando há value e max.
- [ ] Botão do controle mede pelo menos 44×44 px no breakpoint móvel.
- [ ] Com `prefers-reduced-motion: reduce`, a barra não anima em loop.
- [ ] Cores só dos tokens já existentes: `--surface-card`, `--hairline`, `--ink`, `--body`, `--primary`, `--cyan`, `--warning`, `--success`, `--error`.

## Não regressão

- [ ] Artefato HTML continua no painel lateral, não dentro da bolha.
- [ ] Fusion continua visível no cartão atual.
- [ ] TTS lê a prosa, não um dump de JSON.
- [ ] Cache de resposta antiga, sem bloco, continua hit de texto.

## Fora, de propósito

Pizza, mapa, vídeo, proxy de imagem, widget dentro do cache, Thesys, iframe e HTML do modelo não são falha de aceite. São escopo não feito. Não implementar para "completar" esta lista.
