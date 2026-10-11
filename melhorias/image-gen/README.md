# Hub — Geração de imagem em background (Nexus Local)

**Status:** documentação para execução posterior. Nada disto está implementado.  
**Data da pesquisa:** 2026-10-11.  
**Não é** o toolset `image_gen` do Hermes. O alvo é o chat do Multi+ em `/home/osmar/nexuslocal`.

## Índice

1. [00. Visão, problema e decisão](00-visao-geral.md)
2. [01. Pesquisa de provedores e free tier](01-pesquisa-provedores.md)
3. [02. Arquitetura de backend](02-arquitetura-backend.md)
4. [03. Interface](03-interface-usuario.md)
5. [04. Checklist de execução](04-roadmap-checklist.md)

## Decisão em uma frase

Pedido de imagem raster não passa pelo modelo de chat. Um worker em background chama Cloudflare Workers AI (`@cf/black-forest-labs/flux-1-schnell`) com a chave do próprio usuário e devolve o JPEG no mesmo chat, pelo WebSocket `/ws/chat` que já fica aberto.

## O que não fazer na execução

- Não inserir modelos de imagem na tabela `models` (os ~1633 modelos de chat). `stream_chat` não serve imagem.
- Não usar `BackgroundTasks` do FastAPI como fila. Morre no restart.
- Não apontar para as chaves Gemini do Vale da Liberdade.
- Não tratar fal.ai, Pollinations ou "500 imagens/dia no Gemini" como free tier. A pesquisa em `01` explica por quê.
- Não rodar pytest contra `nexuslocal.db` ao vivo. Ver `AGENTS.md`.
- Não adicionar Tailwind. CSS com os tokens já existentes. Strings novas em `pt-BR.json`, `en-US.json` e `es-ES.json`.
