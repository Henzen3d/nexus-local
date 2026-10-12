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
- [ ] Slider (`range`) no controle atualiza o valor numérico em tempo real ao arrastar.
- [ ] Calculadora reativa (`computed`) recalcula a fórmula imediatamente no cliente sem fazer requisição ao servidor.
- [ ] Clique em `send_message` cria bolha do usuário com o template preenchido (incluindo `{resultado}` calculado, se houver).
- [ ] `set_model` não aceita id fora de `models`. Não usa as options que o modelo escreveu.
- [ ] Bloco com `initial_height` reserva o espaço vertical antes do desenho final, prevenindo salto de scroll (Zero CLS).
- [ ] Na Fase 7 (quando sandbox estiver ativo): sandbox roda estritamente sem `allow-same-origin` e sincroniza o tema dark/light através do Theme Bridge.
- [ ] Exportação 1-click standalone (Fase 7) gera arquivo HTML autônomo funcional sem impactar o chat.

## Prompt

- [ ] "bom dia" não injeta `catalog.txt`.
- [ ] "compare os custos dos modelos" injeta, com a flag ligada.
- [ ] "calcule a divisão da conta de 150 com 10% de gorjeta" ativa `controls` com `computed` ou catálogo.
- [ ] Catálogo acima de 400 tokens estimados (`len/4`) não é injetado.

## Acessibilidade e visual

- [ ] Barra tem `role="progressbar"` quando há value e max.
- [ ] Botão do controle mede pelo menos 44×44 px no breakpoint móvel.
- [ ] Com `prefers-reduced-motion: reduce`, a barra não anima em loop.
- [ ] Cores só dos tokens já existentes: `--surface-card`, `--hairline`, `--ink`, `--body`, `--primary`, `--cyan`, `--warning`, `--success`, `--error`.
- [ ] Transições de tema escuro/claro refletem instantaneamente nos cartões nativos e no sandbox bridge.

## Internacionalização (i18n)

- [ ] Todas as strings literais fixas dos componentes (`ProgressCard`, `ChecklistCard`, `ImageCard`, `ControlsCard`, `SandboxCard`) possuem chaves correspondentes em `pt-BR.json`, `en-US.json` e `es-ES.json` (conforme `AGENTS.md`).
- [ ] Troca de idioma da interface reflete imediatamente nos textos de botões, tooltips e fallbacks de erro sem recarregar a conversa.

## Não regressão

- [ ] Artefato HTML continua no painel lateral, não dentro da bolha.
- [ ] Fusion continua visível no cartão atual.
- [ ] TTS lê a prosa, não um dump de JSON.
- [ ] Cache de resposta antiga, sem bloco, continua hit de texto.

## Fora, de propósito

Pizza, vídeo, proxy de imagem, widget dentro do cache semântico e Thesys não são falha de aceite. Nas Fases 1 a 6, o foco é estritamente Nível 1 (Controlled Generative UI). A execução em sandbox Nível 2 é reservada para a Fase 7 pós-estabilização.

