# 00 — Visão geral

## Problema, no código que já existe

O usuário pede uma imagem. O modelo de chat não gera raster. Ele escreve SVG. O Nexus trata isso como artefato.

Detecção: `detect_artifacts()` em `backend/orchestration/artifacts.py`.

- bloco com linguagem `svg` vira artefato `type: "svg"`
- SVG solto (`<svg>...</svg>`) também, se nenhum bloco foi detectado antes

Persistência e aviso ao cliente: `detect_and_save_artifacts()` em `backend/orchestration/persist_turn.py`. O WebSocket recebe um evento `type: artifact` com `artifact_type: svg`.

Render: `ArtifactPanel.tsx` coloca o SVG num `<img src="data:image/svg+xml;base64,...">`. Isso quebra quando o modelo entrega XML incompleto, sem `xmlns`, com entidade malformada, ou com recurso que `<img>` não executa. O painel não tem fallback.

Isso não se conserta melhorando o prompt do modelo de texto. A maioria dos modelos do catálogo não emite pixels.

## O que foi pedido

1. Modelo especializado em imagem, com free tier de verdade.
2. Esse modelo mora em outro lugar, não no seletor de chat.
3. Quando o sistema pede imagem, a geração corre em background, ao mesmo tempo que o chat.
4. A imagem chega no mesmo chat.

## Decisão

Copiar o desenho do Vision Relay, não inventar um segundo produto.

O Vision Relay já faz isto: config singleton (`vision_relay_config`), modelo intérprete separado do modelo da conversa, chave do usuário via `get_provider(..., user_id=)`. Ver `backend/vision_relay/relay.py` e `backend/routers/vision_relay.py`.

A geração de imagem segue o mesmo recorte, com três diferenças:

- a chamada não é `stream_chat` (imagem devolve JPEG, não tokens)
- a fila sobrevive a restart
- a entrega é uma mensagem do mesmo `conversation_id`

## Fluxo alvo

```
usuário pede imagem
        |
        +- heurística: raster ou vetor?
        |     vetor/diagrama/svg -> fluxo atual de artefato, sem mudança
        |     raster -> segue
        |
        +- turno de chat continua (não espera a imagem)
        |     hint no system: não emitir SVG nem código de imagem
        |     /imagem puro pula o modelo de chat
        |
        +- INSERT image_gen_tasks status=pending
                 |
                 worker (lifespan do FastAPI, 1 por vez)
                 |
                 CloudflareProvider._run_url + POST JSON
                 |
                 save_file() em storage/attachments
                 |
                 UPDATE mensagem placeholder + attachment
                 |
                 se /ws/chat desse usuário ainda estiver aberto:
                     evento image_ready
                 senão: a imagem já está no banco; o próximo load da conversa mostra
```

O socket de chat não fecha no fim do turno. `backend/routers/chat.py` fica num `while True` com ping a cada 25s. Dá para empurrar `image_ready` na mesma conexão. Não abrir um segundo WebSocket.

## Fora de escopo

- Consertar o renderer de SVG para virar gerador de imagem. SVG continua válido para diagrama, ícone e fluxograma pedidos como vetor.
- Image-to-image, upscale, várias imagens por pedido, filtro NSFW próprio.
- Rodar FLUX na RTX 3060 Ti. A GPU está no desktop. O servidor do Nexus não é o lugar do modelo.
- Monetização. Uso familiar. Cada usuário usa a própria chave. Provedor compartilhado continua desligado.

## Defaults travados para a execução

| Tema | Default | Por quê |
|---|---|---|
| Provedor | Cloudflare Workers AI | Único free tier diário confirmado na doc oficial em 2026-10-11 |
| Modelo | `@cf/black-forest-labs/flux-1-schnell` | Cabe em 10.000 neurons/dia com folga para uso familiar |
| Catálogo | tabela `image_models`, não `models` | Modelo de imagem em outro lugar |
| Chave | Uma por usuário. Confirmado em 2026-10-11. Sem chave da casa | Token em `user_api_keys`. Account id da Cloudflare também é do usuário, não o `CLOUDFLARE_ACCOUNT_ID` do servidor |
| Fila | SQLite + worker no lifespan | Sem Redis. Carga familiar |
| Paralelismo | 1 | Evita estourar o free tier |
| Teto local | 20 imagens/usuário/dia | Família. Ajustável na config |
| Gatilho | `/imagem` sempre; heurística também, com lista negativa | Ver abaixo |
| Entrega | placeholder na mesma conversa, depois o JPEG | Mesmo chat, sem bloquear o turno |

Se na execução alguém quiser só o comando `/imagem` e zero heurística, a flag é `image_gen_config.auto_detect`. Nasce ligada.

## Raster versus vetor

A heurística não pode roubar pedido de diagrama.

Dispara geração raster:

- prefixo `/imagem`, `/img`, `/image`
- verbo de criação + substantivo de imagem: gere/cria/faz/desenhe/ilustra + imagem/foto/ilustração/figura; draw / generate an image / make a picture

Não dispara (deixa o artefato SVG/HTML/código como hoje):

- svg, vetor, vetorial, diagrama, fluxograma, mermaid, gráfico, ícone, icon, html, código, component

Misto ("explica a Revolução Francesa e desenha um retrato"): chat responde o texto e o worker gera a imagem em paralelo. O hint proíbe SVG nesse turno. `detect_and_save_artifacts` ignora `type == "svg"` quando o turno tem job de imagem.

`/imagem` sozinho não chama o modelo de chat.

## Critério de pronto

1. "desenhe um gato laranja" no modelo de chat atual não abre artefato SVG quebrado.
2. Aparece um JPEG na mesma conversa, com spinner antes.
3. Fechar a aba no meio não perde a imagem: ao reabrir a conversa, o attachment está lá.
4. "faça um diagrama SVG do login" continua artefato SVG, sem chamada à Cloudflare.
5. Usuário sem chave Cloudflare recebe erro claro, sem cair numa chave do servidor nem numa chave do Vale.
