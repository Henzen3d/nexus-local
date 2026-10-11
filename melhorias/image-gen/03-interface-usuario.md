# 03 — Interface

O frontend já tem bolha, painel de artefato, anexo de imagem e i18n em três línguas. A imagem gerada entra por esses caminhos. Não cria um chat paralelo e não usa Tailwind.

Arquivos de locale: `frontend/src/i18n/locales/pt-BR.json`, `en-US.json`, `es-ES.json`. Toda string nova nos três.

## O que o usuário vê

1. Pede "desenhe um farol à noite" no composer normal.
2. A bolha do assistente aparece na hora com spinner suave e o texto `imageGen.pending` ("Gerando imagem…"). O modelo de chat de texto, se ainda for chamado em pedido misto, escreve a resposta de texto na bolha dele. A imagem não espera esse texto, nem o texto espera a imagem.
3. Quando o JPEG chega, o placeholder dá lugar à imagem com a URL estática `/attachments/...`. Clique abre modal de visualização/zoom. Não abre o `ArtifactPanel` de SVG.
4. Se falhar, a bolha exibe badge/card de erro com a mensagem amigável correspondente (ex: falta de chave, cota atingida). Sem toast solto que some da tela.
5. `/imagem farol à noite` (slash puro) cria o placeholder e destrava o composer instantaneamente (o backend envia `stream_end`), sem acionar modelo de chat LLM.

### ⚠️ Ponto Crítico de Segunda Instância: `MessageBubble.tsx`
Hoje, `MessageBubble.tsx` só renderiza anexos no bloco de usuário (`!isAssistant`). No bloco `isAssistant`, a prop `message.attachments` é completamente ignorada.
**Correção mandatória:** Atualizar o branch `isAssistant` em `MessageBubble.tsx` para renderizar `message.attachments` com componente de preview/download de imagem. Sem isso, ao dar reload na página ou reabrir uma conversa antiga (`GET /api/conversations/{id}`), as imagens geradas desapareceriam visualmente mesmo estando salvas no banco.

## Eventos no cliente

O socket é o `/ws/chat` atual. Eventos tratados no mesmo switch de `useChat.ts`:

- `image_pending` — insere ou atualiza a bolha com estado de loading
- `image_ready` com `status: ready` — atualiza anexo e exibe a imagem (`url: /attachments/...`)
- `image_ready` com `status: failed` — exibe mensagem de erro na bolha
- Em comandos slash, o evento `stream_end` fecha o ciclo de streaming da requisição para resetar `isStreaming = false` no composer.

Se o evento chegar para outra `conv_id`, ignorar na tela ativa. Não precisa de store global de tasks. Ao abrir a conversa, o load de mensagens + attachments já reconstrói o estado fielmente. O evento é só para quem está com a conversa aberta.

Não fazer polling. O socket já tem heartbeat de 25s.

## Onde não colocar

- Não listar `flux-1-schnell` no `ModelSelector` dos modelos de chat.
- Não renderizar o JPEG pelo caminho `artifact-svg-content` (`btoa` + `data:image/svg+xml`). Esse caminho é a causa do bug original.
- Artefato tipo `image` na sidebar fica para uma fase 2. Fase 1 entrega na bolha. A sidebar de artefatos continua para HTML/SVG/código.

## Configuração

### 1. Chaves do Usuário (`ApiKeyModal.tsx` / Perfil)
- Como a Cloudflare Workers AI exige Account ID na rota (`accounts/{account_id}/ai/run/{model}`), o modal de chaves para o provedor `cloudflare` deve conter dois campos:
  - **API Token** (`api_key`)
  - **Account ID** (`account_id`)
- Salvos na tabela `user_api_keys` via `POST /api/users/me/keys`.
- Sem o par cadastrado, a tentativa de geração exibe aviso amigável solicitando a configuração.

### 2. Painel Administrativo (ao lado do Vision Relay)
Campos do admin:
- Ligado / desligado (`enabled`, default 0 até o admin testar)
- Detecção automática heurística (`auto_detect`, default 1)
- Modelo padrão (`model_id`, pré-selecionado `cloudflare/flux-1-schnell`)
- Steps 1–8 (default 4)
- Teto diário por usuário (default 20)

Aviso explícito na UI: *"A geração de imagem consome os 10.000 neurons diários gratuitos da conta Cloudflare do próprio usuário. O Nexus não compartilha chaves entre contas."*

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
