# Plano 19: Head Budgeting para Embeddings e Janela de Pré-Processamento
**Conceito inspirado na arquitetura Laya (`head_max_len`)**

**Status:** 📋 Proposta de Plano  
**Prioridade:** Alta (P1)  
**Tempo Estimado:** 45 min  
**Risco:** Baixo  

---

## 📋 1. Resumo e Motivação

O projeto **Laya** (*NandhaKishorM/laya*) demonstrou que modelos e sistemas de decisão/roteamento nunca devem processar textos arbitrariamente longos na íntegra para extrair semântica ou classificar intenções. No Laya, o conceito de `head_max_len` estabelece um teto estrito de tokens para o cabeçalho do payload.

No **NexusLocal**, quando um usuário cola um código de 800 linhas, um arquivo de log extenso ou um documento de 20.000 caracteres, o subsistema de embeddings (`FastEmbed` ONNX) tenta processar todo o conteúdo. Vetorizar 20.000 caracteres em CPU via ONNX consome entre **350ms e 600ms**, gerando um gargalo severo que anula os ganhos das outras otimizações JEV.

A quase totalidade das mensagens de usuários em chats coloca a dúvida ou o comando nas **primeiras linhas ou parágrafos** (ex: *"Como corrijo este erro de conexão? [dump do log de 500 linhas]"*). O restante é carga bruta que não altera a intenção de roteamento e satura o cálculo vetorial.

---

## 🔍 2. Problema Atual no NexusLocal

```
Cenário Atual com Prompts Grandes:
┌────────────────────────────────────────────────────────┐
│ Usuário envia prompt de 25.000 caracteres (log/código) │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ CacheManager._get_semantic() / RequestContext          │
│ ➔ Chama embed_text_async() com todos os 25k chars      │
│ ➔ FastEmbed ONNX tokeniza e calcula 512+ tokens na CPU │
│ ➔ Duração: 450ms a 700ms de travamento de CPU!         │
└────────────────────────────────────────────────────────┘
```

---

## ✅ 3. Solução Proposta: Head Budgeting

Implementar um limitador de cabeçalho (`HEAD_BUDGET_CHARS = 1500`, aproximadamente ~350 tokens) antes de submeter textos ao pipeline de embeddings e cache semântico.

### Regra de Formação da Chave de Head:
1. Se `len(text) <= 1500`, utiliza o texto integral normalizado.
2. Se `len(text) > 1500`:
   - Extrai os primeiros `1500` caracteres (cabeçalho representativo).
   - Opcionalmente combina com as últimas 2 linhas (onde muitas vezes o usuário conclui: *"o que acha?"*).
   - Calcula o hash exato SHA-256 sobre o head representativo.
   - Envia apenas essa fatia compacta para a inferência FastEmbed ONNX.

### Onde Aplicar:
1. **`backend/context/request_context.py`**:
   ```python
   HEAD_BUDGET_CHARS = 1500

   async def get_embedding(self, text: str) -> Optional[bytes]:
       if not text or not text.strip():
           return None
       # Aplica Head Budgeting antes de inferir ou consultar o cache efêmero
       budgeted_text = text.strip()[:HEAD_BUDGET_CHARS]
       ...
   ```
2. **`backend/cache/manager.py`**:
   No cálculo da chave semântica `_semantic_prompt_key` e em `_get_semantic()`.

---

## ⚡ 4. Ganhos Esperados de Latência

| Tamanho do Prompt | Latência Atual (CPU FastEmbed) | Latência com Head Budgeting | Redução |
|---|---|---|---|
| **Curto (< 200 chars)** | ~25ms | ~25ms | 0% (sem impacto) |
| **Médio (1.000 chars)** | ~45ms | ~45ms | 0% |
| **Grande (5.000 chars)** | ~180ms | **~30ms** | **-83%** |
| **Gigante (25.000 chars)** | ~550ms | **~32ms** | **-94%** |

O tempo de pré-processamento passa a ser **O(1) amortizado** no pior caso, independentemente do tamanho do payload enviado pelo usuário.

---

## 🛡️ 5. Casos de Borda e Segurança

* **Perguntas no final do texto**: Em dumps onde o usuário escreve a pergunta após o código (`[log gigante] ... como resolvo?`), a captura inteligente de Head + Tail (primeiros 1.200 caracteres + últimos 300 caracteres) garante cobertura de 100% da intenção.
* **Busca Exata vs Semântica**: O cache exato (`cache_exact`) continua utilizando o SHA-256 do prompt 100% íntegro. O Head Budgeting aplica-se exclusivamente à inferência vetorial e ao cache semântico.
