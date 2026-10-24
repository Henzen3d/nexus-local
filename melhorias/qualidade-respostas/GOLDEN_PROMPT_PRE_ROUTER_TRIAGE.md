# Nexus Local — Golden Prompt: Pré-Router & Triage Agent (Harness de Elite)

**Para:** Hermes Agent (Orquestrador de Produção) + Antigravity (Desenvolvimento e Execução)  
**Objetivo:** Arquitetura de Pré-Router e Triage Agent em dois estágios para eliminar a diluição de instruções no System Prompt, calibrar automaticamente o esforço de raciocínio (*reasoning effort*), extrair restrições rígidas do usuário (*strict constraints*) e eliminar *round-trips* lentos de busca web no Nexus Local.

---

## 🚨 Regras Férreas de Produção (AGENTS.md)
1. **Host Docker:** Sem PM2/systemd. A porta 8000 do host é do Portainer; API roda internamente em `nexus_backend` na rede isolada.
2. **Zero Testes no DB Vivo:** NUNCA rodar pytest ou scripts contra `nexuslocal.db`. Testes estritamente em SQLite temporário (`tempfile.mkstemp`).
3. **Sem GitNexus:** Proibido comandos de reindexação semântica ou embeddings no prompt de deploy.
4. **Portão de Qualidade:** `npm run build` (TypeScript estrito) e pytest 100% verdes antes de qualquer deploy.

---

## 1. Diagnóstico do Problema: Diluição de Instruções em Prompts Monolíticos

No harness tradicional, um único **System Prompt estático e gigante** tenta atender a todas as situações possíveis:
- Se a pergunta é uma saudação ("Olá, tudo bem?"), o modelo lê 60 linhas de instruções sobre tabelas comparativas, badges, regras epistemológicas e RAG.
- Se a pergunta é uma dúvida pontual de busca ("Qual a cotação do dólar hoje?"), o modelo hesita entre responder com um relatório acadêmico de 5 parágrafos ou dar a resposta direta.
- Se o usuário faz um pedido técnico com restrições explícitas ("escreva em Python 3.12 sem usar bibliotecas externas e responda apenas o código"), essas regras acabam soterradas no meio da conversa (fenômeno de *Instruction Dilution*).

### A Solução: Arquitetura Pré-Router / Triage Agent (< 200ms)

Colocar um modelo pequeno e ultrarrápido na linha de frente (com fallback instantâneo por regras léxicas) atuando como **Agente de Triagem**. Ele intercepta a mensagem antes do modelo principal e entrega um contrato JSON estruturado:

1. **System Prompt Modular Cirúrgico:** O modelo final recebe apenas as instruções exatas para aquele cenário (`trivial`, `specific_lookup`, `deep_technical`).
2. **Eliminação de Round-Trip de Busca Web:** O Pré-Router já entrega `needs_web_search: true` e as `search_queries` prontas para execução imediata antes de invocar o modelo final.
3. **Calibração de Raciocínio (Reasoning Effort):** Ajuste fino automático de `low`, `medium` ou `high`.
4. **Blindagem de Restrições (Strict Constraints):** Injeção de alta prioridade no rodapé do prompt das exigências explícitas do usuário.
5. **Transparência na UX:** Indicador visual dinâmico no frontend comunicando o modo ativado.

---

## 2. Contrato de Dados Pydantic (`IntentRouting`)

```python
from pydantic import BaseModel, Field
from typing import Literal, List

class IntentRouting(BaseModel):
    intent_tier: Literal["trivial", "specific_lookup", "deep_technical"] = Field(
        description="trivial: saudação, conversa casual ou fato óbvio. "
                    "specific_lookup: dúvida pontual estilo Google que exige resposta direta + síntese curta. "
                    "deep_technical: código, arquitetura, matemática, análise complexa ou escrita longa."
    )
    reasoning_effort: Literal["low", "medium", "high"] = Field(
        description="Nível de raciocínio necessário para o modelo principal."
    )
    needs_web_search: bool = Field(
        description="True se envolver eventos recentes, preços, versões atuais, fatos específicos ou risco de alucinação."
    )
    search_queries: List[str] = Field(
        default=[],
        description="Até 2 queries curtas e otimizadas para motor de busca caso needs_web_search seja True."
    )
    strict_constraints: List[str] = Field(
        default=[],
        description="Restrições explícitas pedidas pelo usuário (ex: 'apenas JSON', 'máximo 3 linhas', 'sem libs externas')."
    )
```

---

## 3. Matriz de Modulação Dinâmica do System Prompt

| Tier (`intent_tier`) | Modulação de Prompt Injetada | Comportamento do Harness |
| :--- | :--- | :--- |
| **`trivial`** | `[MODO CONVERSA CASUAL / TRIVIAL]`<br>Responda em no máximo 1 a 2 frases diretas, naturais e sem rodeios. Não adicione explicações extras, listas ou introduções. | Desliga raciocínio pesado; bypass de busca web; prioriza latência mínima. |
| **`specific_lookup`** | `[MODO RESPOSTA RÁPIDA & EMBASAMENTO]`<br>Entregue a resposta exata, o fato ou o comando já na primeira frase em **negrito**. Logo abaixo, adicione apenas 2 a 4 bullet points curtos com o embasamento técnico ou contexto essencial das fontes. Pare imediatamente após isso. | Dispara `search_queries` se necessário; esforço de raciocínio baixo/médio. |
| **`deep_technical`** | `[MODO ENGENHARIA PROFUNDA]`<br>Inicie com um veredito técnico direto na primeira linha. Em seguida, desenvolva a solução completa, cobrindo casos de borda, código pronto para produção, boas práticas e tabelas comparativas quando útil. Priorize precisão técnica absoluta. | Ativa `reasoning_effort: high`; seleciona modelo mais forte do pool; formatação visual completa. |

### Injeção de Restrições Explícitas (`strict_constraints`)
Quando detectadas pelo Pré-Router, são anexadas no final do prompt:
```text
[RESTRIÇÕES OBRIGATÓRIAS DESTA RESPOSTA]:
- {constraint_1}
- {constraint_2}
Cumpra estas regras estritamente acima de qualquer formatação padrão.
```

---

## 4. Estratégia de Execução Resiliente (Dual-Engine)

1. **Fast LLM Triage (Primário):** Tenta chamar modelo ultrarrápido (Groq Llama 3.1 8B Instant, Gemini Flash Lite ou local rápido) com timeout estrito de 800ms a 1200ms.
2. **Heuristic Rule Engine (Fallback Instantâneo):** Se nenhum provedor rápido estiver ativo, ou em caso de timeout/erro de rede, a classificação léxica do `smart_router.py` assume instantaneamente em < 1ms, garantindo zero atraso e 100% de disponibilidade.
3. **Short-Circuit para Saudações:** Mensagens triviais óbvias ("oi", "olá", "bom dia") são resolvidas no estágio léxico em 0.1ms sem chamada de API externa.

---

## 5. Critérios de Aceite

- [x] Contrato `IntentRouting` implementado com validação robusta.
- [x] Motor de triagem dual-engine (LLM rápido com fallback síncrono para regras).
- [x] Modulação dinâmica do System Prompt com base no tier detectado.
- [x] Injeção de bloco de restrições rígidas (`strict_constraints`) no prompt final.
- [x] Integração no fluxo do WebSocket com emissão de evento de status para o frontend.
- [x] Testes unitários cobrindo todos os tiers, extração de restrições e comportamento de fallback.
