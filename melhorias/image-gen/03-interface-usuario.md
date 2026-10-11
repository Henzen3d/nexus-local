# 03 — Interface

O frontend já tem bolha, painel de artefato, anexo de imagem e i18n em três línguas. A imagem gerada entra por esses caminhos. Não cria um chat paralelo e não usa Tailwind.

Arquivos de locale: `frontend/src/i18n/locales/pt-BR.json`, `en-US.json`, `es-ES.json`. Toda string nova nos três.

## O que o usuário vê

1. Pede "desenhe um farol à noite" no composer normal.
2. A bolha do assistente aparece na hora com spinner e o texto "Gerando imagem…". O modelo de chat, se ainda for chamado, escreve a resposta de texto na bolha dele. A imagem não espera esse texto, nem o texto espera a imagem.
3. Quando o JPEG chega, o spinner da bolha de imagem vira `<img>` com a URL do attachment já existente. Clique abre em tamanho maior. Não abre o `ArtifactPanel` de SVG.
4. Se falhar, a mesma bolha mostra o erro da tabela do `02`. Sem toast solto que some.
5. `/imagem farol à noite` faz só o passo 2 e 3. Sem resposta de texto.

Pedido de diagrama continua abrindo o painel de artefato, como hoje.

## Eventos no cliente

O socket é o `/ws/chat` atual. Três eventos novos, no mesmo switch que já trata `artifact`:

- `image_pending` — insere ou atualiza a bolha placeholder
- `image_ready` com `status: ready` — troca pelo `<img>`
- `image_ready` com `status: failed` — troca pelo erro

Se o evento chegar para outra `conv_id`, ignorar na tela ativa. Não precisa de store global de tasks. Ao abrir a conversa, o load de mensagens + attachments já reconstrói o estado. O evento é só para quem está olhando.

Não fazer polling. O socket já tem ping de 25s.

## Onde não colocar

- Não listar `flux-1-schnell` no `ModelSelector` dos modelos de chat.
- Não renderizar o JPEG pelo caminho `artifact-svg-content` (`btoa` + `data:image/svg+xml`). Esse caminho é a causa do bug.
- Artefato tipo `image` na sidebar fica para uma fase 2. Fase 1 entrega na bolha. A sidebar de artefatos continua para HTML/SVG/código.

## Configuração

Painel no mesmo lugar em que o Vision Relay é configurado (admin). Campos:

- ligado / desligado (default desligado até o admin testar)
- detecção automática (default ligada)
- modelo (lista de `image_models`, uma linha na fase 1)
- steps 1–8 (default 4)
- teto diário (default 20)

Decisão confirmada: uma chave por usuário, sem chave da casa. O cadastro pede o token e o account id da Cloudflare daquele usuário. O account id do servidor não serve. Se já houver token do provider Cloudflare, não duplicar o campo de token; o account id da imagem entra no mesmo cadastro, porque a URL da API precisa dos dois.

Uma linha de aviso: "A imagem sai pela sua conta Cloudflare. O servidor não guarda a chave de outra pessoa e não usa a chave do jornal."

## Composer

Fase 1 não exige pill nova. `/imagem` basta, e a heurística cobre a frase solta.

Pill "Imagem" no composer entra na fase 2, junto com os action pills de `melhorias/novas-5-melhorias-ux/`, se aquela frente ainda não tiver sido feita. Não bloquear a fase 1 por causa de pill.

## i18n mínimo

Chaves sugeridas, texto pt-BR:

- `imageGen.pending` — Gerando imagem…
- `imageGen.failedGeneric` — Não consegui gerar a imagem.
- `imageGen.missingKey` — Falta a chave Cloudflare na sua conta.
- `imageGen.quota` — Cota diária da Cloudflare acabou. Reseta à meia-noite UTC.
- `imageGen.localCap` — Limite de imagens de hoje atingido.
- `imageGen.slashHint` — /imagem seguido do que você quer ver

en-US e es-ES no mesmo PR. Build do frontend tem que passar com 0 erros de tipo.
