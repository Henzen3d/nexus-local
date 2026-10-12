# 00 — Visão e diagnóstico

**Multi+ / NexusLocal** · Plano, não implementação

## Pergunta que originou o plano

Nem todo modelo tem opção de reasoning, e isso parece decidir se existe seleção de esforço. A intuição está quase certa. O detalhe que muda o desenho: **emitir raciocínio e aceitar um dial de esforço são capacidades diferentes.**

## Três casos, não dois

| Caso | O que o modelo faz | O que a UI pode oferecer |
| :--- | :--- | :--- |
| Pensa e tem dial | Aceita um parâmetro de quanto pensar | Seletor com só os níveis daquele contrato |
| Pensa e não tem dial | Raciocina sempre (típico DeepSeek R1 clássico) | Texto fixo. Sem slider. Controle real é teto de tokens, que já existe |
| Não pensa e não tem dial | Maioria do catálogo (~1633 modelos) | Nada. Omitir o campo |

Um modelo pode ainda ter dial que inclui "não pensar" (orçamento zero ou `none`). Isso continua sendo dial, não ausência de reasoning.

## O que o código faz hoje

Conferido em `main` após `6e80ebe`.

- `OpenAICompatProvider.stream_chat` monta só `model`, `messages`, `temperature`, `max_tokens`, `stream`. O comentário sobre `reasoning_effort` em `backend/providers/base.py` não entra no JSON.
- `GeminiProvider` manda `generationConfig` com `temperature` e `maxOutputTokens`. Sem `thinkingConfig`.
- `CloudflareProvider` não tem gancho de esforço.
- A tabela `models` tem `supports_vision`. Não tem flag de reasoning nem de esforço.
- O frontend já parseia `reasoning_content` e tags `<think>` / `<thinking>` e mostra no balão. Isso é leitura. Não escolhe intensidade.
- O Smart Router escolhe `temperature` por intenção (`backend/ranking/smart_router.py`). Não escolhe esforço.
- O WebSocket de chat (`backend/routers/chat.py`) lê `fusion` e `web_search`. Não lê esforço.
- O cockpit novo (`frontend/src/components/ModelSelector.tsx`) é um menu hierárquico com: toggle Auto, linha de navegação de provedor (`Provedor >`), lista compacta dos top 3 modelos e linha de mais modelos (`Mais modelos >`). Não tem linha de esforço.
- Busca no frontend por `effort`, `reasoningEffort` e `esforço`: zero ocorrências.

## Por que um campo único quebra

O catálogo fala OpenAI-compat com vários provedores (Groq, OpenRouter, Cerebras, Gemini compat, NVIDIA, SiliconFlow e outros). O mesmo nome de campo não significa o mesmo contrato:

- OpenAI e alguns Grok usam `reasoning_effort`.
- Gemini nativo usa `thinkingConfig` (`thinkingBudget` ou `thinkingLevel`, conforme a geração do modelo).
- Claude recente separa `effort` do orçamento de extended thinking.
- OpenRouter em geral só repassa. Quem honra é o modelo de destino.
- Mandar o campo para Llama/Groq/Cerebras genérico tende a 400.

Por isso o seletor é **gated pela capacidade do modelo escolhido**, e o backend traduz ou omite. Nunca um slider global no payload.

## Fora de escopo da v1

- Não reescrever o parser de pensamento.
- Não aplicar esforço em chamadas internas: enhancer, extrator de memória, dream, juiz do Fusion.
- Não varrer os 1633 nomes com heurística cega na hora do request. Heurística só sugere. Valor gravado pelo admin ganha.
- Não indexar GitNexus. Não rodar pytest no `nexuslocal.db` vivo.

## Critério de sucesso do produto

Com um modelo sem controle, o JSON enviado ao provedor é o mesmo de hoje. Com um modelo com controle, o usuário escolhe um nível que a API daquele modelo aceita, e o failover não repassa o campo se o reserva não aceita.
