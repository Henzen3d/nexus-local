# 04 — Checklist de execução

Ordem obrigatória. Não pular o spike. Não ligar `enabled` em produção antes do item 8.

Banco de teste: cópia temporária ou `:memory:`. Nunca `nexuslocal.db` vivo.

## Fase 0 — Spike (meio dia)

- [ ] Confirmar na página de pricing da Cloudflare que a cota ainda é 10.000 neurons/dia e que `flux-1-schnell` ainda existe.
- [ ] Uma chamada REST com token de teste do admin (não o token do Vale, não o `cfoat_` do wrangler).
- [ ] Gravar o envelope JSON sem o base64 em `backend/tests/fixtures/cloudflare_flux_schnell_response.json`.
- [ ] Anotar neurons consumidos no dashboard. Se a estimativa do `01` estiver errada, corrigir o `01` antes de seguir.
- [ ] Confirmar se `width`/`height` são aceitos. Se a API rejeitar, a config guarda o campo e o client não envia.

Pronto da fase: JPEG em `/tmp` aberto e válido, fixture commitável (sem segredo, sem imagem gigante).

## Fase 1 — Fila e provider (não liga no chat ainda)

- [ ] Migração em `init_db()`: `image_models`, `image_gen_config`, `image_gen_tasks`, índices, seed de um modelo. `enabled` default 0.
- [ ] `CloudflareProvider.run_image` usando `_run_url` e o fixture do spike.
- [ ] `classify_image_intent` com testes das frases do `00` (raster, vector, none, slash, misto, lista negativa ganhando de "desenhe").
- [ ] `queue.py`: insert, claim, recover de `generating` velho, cap diário em UTC.
- [ ] Worker no lifespan, paralelismo 1, timeout 60s, 429 vira failed sem retry loop.
- [ ] `save_file(..., is_image=True)` + linha em `attachments` ligada ao `message_id` placeholder.
- [ ] Testes com `httpx` mockado e banco temporário. Nenhum teste bate na API real.

## Fase 2 — Encaixe no turno

- [ ] Registry de sockets por `user_id` em `chat.py`, limpo no `finally`.
- [ ] Turno cria placeholder + task e emite `image_pending` antes do stream.
- [ ] Slash puro não chama o modelo de chat.
- [ ] Hint anti-SVG só na chamada daquele turno.
- [ ] `detect_and_save_artifacts` ignora `svg` quando há job de imagem.
- [ ] `image_ready` / failed no socket se ainda estiver aberto.
- [ ] Reload da conversa mostra a imagem sem depender do evento.

## Fase 3 — UI e config

- [ ] Bolha com spinner, img, erro. Sem painel SVG.
- [ ] Painel admin ao lado do Vision Relay. Nasce desligado.
- [ ] I18n pt-BR, en-US, es-ES.
- [ ] `npm run build` no `frontend/` com 0 erros.
- [ ] Usuário sem chave vê `imageGen.missingKey` e nenhuma chamada externa.

## Fase 4 — Ligar

- [ ] Cada usuário cola o próprio token e o próprio account id. Prova: usuário B não autentica na conta do admin.
- [ ] Admin liga `image_gen_config.enabled`.
- [ ] Prova manual no site: frase raster gera JPEG; frase de diagrama SVG não chama a Cloudflare; fechar a aba no meio e reabrir mostra a imagem; segundo usuário sem chave não usa a chave do admin.
- [ ] Só então rebuild da imagem Docker / restart, pelo fluxo do `AGENTS.md`. Esta pasta não autoriza deploy sozinha.

## Fase 5 — não fazer agora

- [ ] Adaptador Gemini imagem, só depois de uma chamada de teste provar cota free na chave daquele usuário. Sem essa prova, não codar.
- [ ] `flux-2-klein-9b` como segunda linha do catálogo, com o custo em neurons visível na UI.
- [ ] Pill no composer.
- [ ] Artefato tipo `image` na sidebar.
- [ ] Image-to-image, várias saídas, upscale.

## Aceite

| # | Prova |
|---|---|
| 1 | "desenhe um gato laranja" não cria artefato SVG |
| 2 | JPEG aparece na mesma conversa sem o usuário mandar outra mensagem |
| 3 | O texto do chat, se houver, não espera a imagem |
| 4 | "faça um diagrama SVG do login" não gera task |
| 5 | Restart do backend no meio de um `pending` retoma a task |
| 6 | Usuário B não gasta a chave do usuário A |
| 7 | 21ª imagem do dia falha localmente, sem POST |
| 8 | Pytest não abre `nexuslocal.db` |
