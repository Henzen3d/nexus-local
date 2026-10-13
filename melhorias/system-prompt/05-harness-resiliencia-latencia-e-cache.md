# ⚡ Plano 05: Resiliência, Latência, Caching e Artefatos do Harness

Este documento expande a visão do Harness além do texto do prompt, atacando os gargalos de **resiliência de streaming**, **latência percebida**, **extração inteligente de artefatos** e **isolamento de cache** no Multi+ / NexusLocal.

---

## 🎯 As Frentes de Engenharia do Harness

O harness atua como o sistema operacional em torno dos LLMs. Para garantir uma experiência ágil e profissional, 5 melhorias arquiteturais foram projetadas:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PIPELINE DO HARNESS NEXUS                       │
├─────────────────────┬───────────────────────┬──────────────────────────┤
│ 1. Time to First    │ 2. Filename Parser    │ 3. WebSocket             │
│    Token (TTFT)     │    em Artefatos       │    Coalescing            │
│    Timeout de 8s    │    Lê # main.py       │    Batching a cada 35ms  │
├─────────────────────┼───────────────────────┼──────────────────────────┤
│ 4. Proactive Quota  │ 5. Isolamento de      │ 6. Retomada de Stream    │
│    Header Tracker   │    Cache por Usuário  │    Conexão Interrompida  │
│    Skip antes do 429│    Zero vazamento PII │    Costura Transparente  │
└─────────────────────┴───────────────────────┴──────────────────────────┘
```

---

## ⏱️ 1. Timeout de Primeiro Token (TTFT Deadline & Early Failover)

### O Problema Atual
Em [backend/orchestration/resolve_request.py](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py#L238), a chamada `provider.stream_chat(...)` aguarda a resposta do modelo. Se uma API remota gratuita ou sobrecarregada (ex: servidor congestionado no OpenRouter ou Groq) travar a conexão sem emitir tokens, a requisição pode prender o usuário por até 120 segundos antes do timeout do `httpx`.

### A Solução
Implementar um deadline estrito de **8 segundos** para a emissão do primeiro token (`first_token_received`):

```python
STREAM_TTFT_TIMEOUT_SECONDS = 8.0

# No loop de streaming de resolve_request.py:
stream_iter = provider.stream_chat(model=model_name, messages=history, **stream_kwargs).__aiter__()

try:
    # Aguarda o primeiro token com prazo limite
    first_token = await asyncio.wait_for(
        stream_iter.__anext__(),
        timeout=STREAM_TTFT_TIMEOUT_SECONDS,
    )
    first_token_received = True
    full_response += str(first_token)
    await ws.send_json({"type": "token", "content": str(first_token)})
except (asyncio.TimeoutError, TimeoutError):
    logger.warning(
        "TTFT Timeout (8s excedido) no provedor '%s' (modelo '%s'). Acionando failover cascade precoce.",
        current_provider_id, current_model_id,
    )
    attempted_model_ids.add(current_model_id)
    continue  # Pula imediatamente para o próximo modelo do ranking
```

**Benefício:** Se um provedor engasgar, o usuário é transferido para o fallback em 8s em vez de esperar 2 minutos com a tela congelada.

---

## 📁 2. Extração Inteligente de Nomes de Arquivo em Artefatos

### O Problema Atual
Em [backend/orchestration/artifacts.py](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/artifacts.py#L168-L173), blocos de código recebem títulos genéricos como `"PYTHON Code"`, `"JSX React Component"` ou `"MARKDOWN Document"`.

Com o novo System Prompt (que instrui o modelo a colocar o nome do arquivo na primeira linha como comentário), o `artifacts.py` deve extrair esse nome automaticamente.

### A Solução
Adicionar a função de parsing tolerante `_extract_code_filename`:

```python
_RE_FILENAME_COMMENT = re.compile(
    r'^(?:#|//|<!--|/\*|\*)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]{1,8})(?:\s*-->|\s*\*\/)?\s*$',
    re.MULTILINE,
)

def _extract_code_filename(body: str, lang: str, fallback_type: str) -> str:
    """Extrai o nome do arquivo da primeira linha comentada de um bloco de código."""
    first_lines = body.strip().split("\n")[:2]
    for line in first_lines:
        m = _RE_FILENAME_COMMENT.match(line.strip())
        if m:
            candidate = m.group(1).strip()
            # Validação sanitária básica
            if "/" in candidate:
                candidate = candidate.split("/")[-1]
            if "\\" in candidate:
                candidate = candidate.split("\\")[-1]
            if len(candidate) <= 64:
                return candidate
    return f"{lang.upper() if lang else 'Code'} {fallback_type}"
```

**Benefício:** Um bloco gerado como:
```python
# database_migration.py
import sqlite3
...
```
passa a ser registrado no banco e na interface como o artefato `"database_migration.py"`, permitindo downloads diretos com o nome de arquivo correto.

---

## 🌊 3. Coalescência de Tokens no WebSocket (Token Coalescing)

### O Problema Atual
Provedores ultrarrápidos (como Groq rodando Llama 3.3 a 300+ tokens/segundo ou Cerebras a 1000 tok/s) disparam centenas de mensagens individuais por segundo no WebSocket:
`await ws.send_json({"type": "token", "content": token_str})`  
Isso causa congestionamento de renderização e engasgos de ciclo de frame (jank) no navegador e em dispositivos móveis.

### A Solução
Bufferizar micro-lotes de tokens a cada **30-40ms** ou até atingir um chunk de 8 tokens:

```python
token_buffer = []
last_flush = time.perf_counter()

async def flush_tokens():
    nonlocal token_buffer, last_flush
    if token_buffer:
        batch_text = "".join(token_buffer)
        await ws.send_json({"type": "token", "content": batch_text})
        token_buffer.clear()
        last_flush = time.perf_counter()

async for token in stream_iter:
    token_str = str(token)
    full_response += token_str
    token_buffer.append(token_str)
    
    # Descarrega se acumulou tempo ou tamanho ideal
    if len(token_buffer) >= 8 or (time.perf_counter() - last_flush) >= 0.035:
        await flush_tokens()

await flush_tokens()  # Descarrega resíduos finais
```

**Benefício:** Reduz o volume de pacotes WebSocket em ~80% em modelos ultravelozes, resultando em renderização ultra-suave a 60 FPS na interface.

---

## 🔒 4. Isolamento e Escopo Estrito de Cache

### O Problema
Respostas geradas com memórias particulares do usuário ou em projetos privados não podem, sob hipótese alguma, ser entregues para outra conta em cache hits exatos ou semânticos.

### A Regra de Segurança
No [backend/cache/manager.py](file:///j:/Arquivos%20Osmar/Multi+/backend/cache/manager.py):
1. **Condição de Não-Cacheamento:**
   - Se a requisição utilizou dados de memória (`context_fingerprint != "nomem"`), pesquisa na web ou documentos confidenciais de projetos, a chave do cache DEVE incorporar `user_id`.
2. **Hash Combinado:** O hash de `cache_exact` é calculado obrigatoriamente sobre:
   `hash = SHA256(user_id + ":" + model_id + ":" + serialized_messages)`
   garantindo isolamento criptográfico absoluto entre contas da família.

---

## 📈 Resumo dos Ganhos

| Recurso | Sem a Melhoria | Com a Melhoria |
| :--- | :--- | :--- |
| **Timeout de Falha** | Usuário espera até 120s | Failover em até 8s |
| **Nome do Artefato** | "PYTHON Code" genérico | "database_migration.py" real |
| **Consumo de CPU na UI** | 300 eventos/s no WebSocket | Micro-lotes a cada 35ms (60 FPS limpo) |
| **Segurança Multiusuário** | Risco de cache cross-user | Isolamento estrito por `user_id` |
