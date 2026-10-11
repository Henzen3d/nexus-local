# 01 — Pesquisa de provedores (2026-10-11)

Fontes lidas nesta data, não listicles antigos:

- [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) — página diz "Last updated Oct 9, 2026"
- [flux-1-schnell](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) — "Last updated 2026-10-09 UTC"
- [Hermes image generation](https://hermes-agent.nousresearch.com/docs/user-guide/features/image-generation) — contexto, não é o alvo
- Inventário cético: [Runflow, 30 abr 2026](https://www.runflow.io/blog/free-ai-image-generation-api-lies) — útil para descartar "free" falso; o autor vende API paga, então o viés está declarado

## O que "free tier" significa aqui

Uso familiar, poucos usuários, cada um com a própria chave, sem cartão obrigatório para o caminho padrão. Crédito de cadastro que acaba em um dia não conta.

## Tabela

| Opção | Free de verdade? | Veredito |
|---|---|---|
| Cloudflare Workers AI, `flux-1-schnell` | Sim. 10.000 neurons/dia em plano Free e Paid. Reset 00:00 UTC. Acima disso, plano Free falha; plano Paid cobra US$ 0,011 / 1.000 neurons | **Padrão** |
| Cloudflare `flux-2-klein-9b` | Mesma cota, mas ~1.364 neurons no primeiro megapixel. Umas 7 imagens/dia | Opção de qualidade, não default |
| Cloudflare `flux-2-dev`, Leonardo Phoenix/Lucid | Mesma cota, bem mais caro por imagem | Não |
| Gemini Nano Banana / Imagen | Página oficial de 2026-10-09 lista preço. Não lista free tier de imagem. Artigo de abril/2026 já marcava "Free Tier: Not available" para Gemini 3 Pro Image e Imagen 4. O "500 req/dia" de listicles não foi confirmado | Não usar como caminho free. Adaptador pago só na fase 2, e só se um teste com a chave do usuário mostrar cota |
| fal.ai FLUX | Crédito inicial, depois ~US$ 0,003 a US$ 0,03 por imagem. É o catálogo do Hermes, não do Nexus | Rejeitado como padrão |
| Together, Replicate, Leonardo API | Crédito ou trial | Rejeitado |
| Hugging Face Inference | Créditos mensais, rate limit, sem garantia | Fase 3 opcional, se sobrar tempo |
| Pollinations e wrappers "ilimitados" | Sem contrato, sem SLA, some quando o dono cancela | Rejeitado |
| GPU local (RTX 3060 Ti) | Grátis em dólar, cara em ops. A placa não está no servidor do Nexus | Fora de escopo |
| Hermes `image_generate` (FAL / Nous / OpenRouter) | Exige `FAL_KEY` ou assinatura Nous. Entrega no Telegram do Hermes, não no chat do Nexus | Não reutilizar |

## Cloudflare, números para não inventar na implementação

Cota: **10.000 neurons por dia**. Não são 10.000 imagens. Não são 100.000 chamadas. Quem repetir "100.000 calls/dia" está citando texto de terceiros, não a página de preço.

Preço publicado de `@cf/black-forest-labs/flux-1-schnell`:

- 4,80 neurons por tile 512×512
- 9,60 neurons por step
- steps default 4, máximo 8

Conta fechada em 2026-10-11, página de preço de 9 out 2026. Schnell cobra duas linhas separadas, não "por tile por step" (isso é o `flux-2-dev`): 4,80 neurons por tile 512×512 mais 9,60 por step. Steps default 4. A API não aceita largura (`additionalProperties: false`). Se a imagem sair 1024 (4 tiles): 4×4,80 + 4×9,60 = 57,6 neurons → 173 imagens/dia. Se sair 512 (1 tile): 43,2 neurons → 231 imagens/dia. Conferir o tamanho real no spike.

Os 10.000 neurons são um pote só da conta, por dia, reset 00:00 UTC. Imagem, LLM, áudio e embedding gastam o mesmo pote. Não é cota separada de imagem. Exemplo só de chat, 2.000 tokens de entrada e 500 de saída: Llama 3.3 70B gasta ~156 neurons (~64 turnos/dia); Llama 3.1 8B fast gasta ~26 (~389 turnos). Vinte imagens a 57,6 deixam ~8.848 neurons. Chat pesado na Cloudflare no mesmo dia reduz as imagens, e o contrário também.

`flux-2-klein-9b`: 1.363,64 neurons no primeiro megapixel. Não é o default.

## Contrato da API (o que a doc mostra)

Modelo: `@cf/black-forest-labs/flux-1-schnell`

```bash
curl "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/ai/run/@cf/black-forest-labs/flux-1-schnell" \
  -X POST \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"cyberpunk cat","steps":4}'
```

Input publicado:

- `prompt` string, obrigatório, 1–2048 caracteres
- `steps` inteiro, máximo 8, default 4

O exemplo de Worker diz que `response.image` é JPEG em base64. Na REST API direta (`/ai/run/{model}`), a Cloudflare pode devolver de duas formas dependendo da rota e versão:
- `Content-Type: image/jpeg` (ou binário direto nos bytes do body)
- `Content-Type: application/json` com envelope `{"success": true, "result": {"image": "<base64>"}, "errors": []}`

Portanto, `run_image` **não deve assumir cegamente nenhum dos dois formatos**: deve checar o header `Content-Type` da resposta:
1. Se iniciar com `image/` ou `application/octet-stream`: extrair os bytes binários diretamente (`resp.content`).
2. Se for `application/json`: decodificar JSON, validar `result.image` e converter `base64.b64decode()`.
3. Se status 4xx/5xx: capturar `errors[0].message` do JSON para mensagem amigável (sem vazar internals).
A primeira tarefa da execução (Fase 0 - Spike) é gravar uma chamada real e fixar esses parsers com fixture.

O Nexus já fala com essa API para chat. `CloudflareProvider` em `backend/providers/base.py`:

- `base_url` esperado: `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1`
- `_run_url(model, account_id=None)` monta `.../accounts/{account_id}/ai/run/{model}`
- `stream_chat` manda `messages` e lê SSE. Modelo de imagem não fala esse protocolo. Nova função no mesmo provider: `run_image(model, prompt, steps, account_id=None) -> bytes`. Não criar provider paralelo.

## Chaves — decisão confirmada

2026-10-11: uma chave por usuário. Sem chave da casa. Sem fallback para token do servidor, do wrangler do Vale (`~/.config/.wrangler/`) ou de `GEMINI_API_KEY`.

`user_api_keys` originalmente guardava apenas `(user_id, provider_id, api_key)`. Como a REST da Cloudflare exige o Account ID na URL (`accounts/{account_id}/ai/run/{model}`), a tabela `user_api_keys` receberá a coluna `account_id TEXT` via migração incremental segura (`ALTER TABLE user_api_keys ADD COLUMN account_id TEXT;` dentro de `init_db()`).

O `{account_id}` padrão do ambiente (`CLOUDFLARE_ACCOUNT_ID`) pertence ao host/servidor e **nunca** deve ser usado para requisições de outros usuários (geraria 401/403 e gastaria cotas indevidas). Cada usuário cadastra seu token + account id no modal de chaves. Sem o par token + account id daquele usuário, a task falha imediatamente com solicitação de configuração. Como a cota de 10.000 neurons é por conta Cloudflare, cada membro da família usa os 10k neurons da sua própria conta.

## O que a execução deve revalidar no dia em que for codar

Preço e nome de modelo mudam. Antes de cravar o id no seed:

1. Abrir a página de pricing da Cloudflare e confirmar que `flux-1-schnell` ainda está na tabela de imagem e que a cota ainda é 10.000 neurons/dia.
2. Uma chamada real com a chave de teste do admin, parser do envelope, um JPEG salvo em `/tmp`.
3. Só então escrever o id no seed de `image_models`.
