# ⚙️ 02. Arquitetura Backend & Cascata de Failover
**NexusLocal / Multi+** · Especificação Técnica do Motor de Transbordo

---

## 1. Visão Geral da Arquitetura

O motor de **Auto-Switch** no backend conecta o ciclo de streaming de conversas em [resolve_request.py](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py) ao resolvedor de modelos em [failover.py](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/failover.py), garantindo que falhas de conexão ou cotas sejam contornadas de forma invisível.

---

## 2. A Nova Cascata em 3 Tiers com Prioridade do Mesmo Provedor

Atualmente, o motor de failover salta diretamente para outros provedores através de famílias ou ranking global. A introdução do **Tier 0** respeita a decisão do usuário, buscando primeiro outro modelo funcional dentro do ecossistema que ele escolheu explicitamente.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          Modelo Inicial Solicitado (ex: Minimax M3)                    │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ Falha (402 / 400 / 429)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│        TIER 0: MESMO PROVEDOR (Afinidade de Contexto e Provedor)                       │
│                                                                                        │
│  Busca no banco: outro modelo onde:                                                    │
│  • provider_id == 'llm7'                                                               │
│  • enabled == 1                                                                        │
│  • status != 'exhausted' AND status != 'cooldown'                                      │
│  • Ordenado por ranking local ou context_length                                        │
│                                                                                        │
│  ➔ Sucesso: Pula para GPT Oss:20b (mesmo provedor)                                      │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ Se todos os modelos do provedor falharem
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│        TIER 1: MESMA FAMÍLIA (Preservação de Capacidade e Arquitetura)                 │
│                                                                                        │
│  Busca na tabela model_family_members:                                                 │
│  • Outro provedor com o mesmo modelo/peso (ex: DeepSeek R1 no Groq ou SiliconFlow)     │
│  • Ordenado por fallback_order                                                         │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ Se a família estiver exaurida ou não existir
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│        TIER 2: RANKING GERAL GLOBAL (Melhor Qualidade Geral Disponível)                │
│                                                                                        │
│  Busca no model_rankings:                                                              │
│  • Modelo com maior nexuslocal_score disponível em qualquer provedor ativo             │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Implementação Técnica do Tier 0 em `failover.py`

Em [failover.py](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/failover.py), adicionamos a consulta dedicada ao mesmo provedor:

```python
async def _get_next_model_same_provider(
    requested_model_id: str,
    db: aiosqlite.Connection,
    exclude_model_ids: list[str] | None = None
) -> tuple[str, str, str] | None:
    """
    Tier 0: Busca o melhor modelo alternativo do MESMO provedor que ainda esteja disponível.
    Retorna (model_id, provider_id, display_name) ou None.
    """
    excluded = set(exclude_model_ids or [])
    excluded.add(requested_model_id)

    # 1. Descobre o provedor do modelo que falhou
    provider_id = await _get_provider_id(requested_model_id, db)
    if not provider_id:
        return None

    # 2. Busca modelos habilitados do mesmo provedor, sem esgotamento nem cooldown ativo
    query = """
        SELECT m.id, m.provider_id, m.display_name, COALESCE(r.nexuslocal_score, 50.0) as score
        FROM models m
        LEFT JOIN model_rankings r ON r.model_id = m.id
        LEFT JOIN model_quota_status q ON q.model_id = m.id
        WHERE m.provider_id = ?
          AND m.enabled = 1
          AND (
              q.status IS NULL 
              OR q.status = 'available'
              OR (q.exhausted_until IS NOT NULL AND q.exhausted_until <= datetime('now'))
          )
        ORDER BY score DESC, m.context_length DESC
    """
    async with db.execute(query, (provider_id,)) as cur:
        rows = await cur.fetchall()

    for mid, pid, dname, _ in rows:
        if mid not in excluded:
            return mid, pid, dname

    return None
```

Na função principal `resolve_model_with_failover`, a ordem de avaliação passa a ser:
1. `_get_next_model_same_provider(requested_model_id, db, exclude_model_ids)` *(Tier 0)*
2. Se `None`, busca `_get_family_for_model(...)` *(Tier 1)*
3. Se `None`, busca `_get_next_best_ranked_model(...)` *(Tier 2)*

---

## 4. O Loop de Streaming Resiliente em `resolve_request.py`

O coração da experiência fluida está em **não quebrar o WebSocket** quando uma chamada HTTP do provedor falha. 

### 4.1. Máquina de Estados do Streaming Resiliente

```python
_MAX_FAILOVER_ATTEMPTS = 5

async def stream_from_llm(
    ws: "WebSocket",
    db,
    conversation_id: str,
    user_id: str,
    model_id: str,
    provider_id: str,
    history: list[dict],
) -> tuple[str, str, str] | None:
    attempt = 0
    success = False
    original_model_id = model_id
    full_response = ""
    excluded_models = []

    while attempt < _MAX_FAILOVER_ATTEMPTS and not success:
        attempt += 1

        # 1. Resolve o modelo considerando falhas acumuladas
        try:
            resolved = await resolve_model_with_failover(
                original_model_id,
                db,
                failover_enabled=True,
                exclude_model_ids=excluded_models,
                force_skip=(attempt > 1)
            )
        except NoAvailableModelError as e:
            await ws.send_json({
                "type": "error",
                "message": f"Todos os modelos redundantes falharam: {str(e)}"
            })
            return None

        current_model_id = resolved.model_id
        current_provider_id = resolved.provider_id

        # 2. Notifica a transição suave caso haja failover
        if resolved.was_failover:
            await ws.send_json({
                "type": "failover_notice",
                "original_model": original_model_id,
                "fallback_model": resolved.display_name,
                "fallback_model_id": current_model_id,
                "provider_id": current_provider_id,
                "reason": resolved.failover_reason or "failover_auto_switch",
                "attempt": attempt,
            })

        # 3. Tenta conectar e iniciar o streaming do provedor
        tokens_emitted = 0
        try:
            provider = await get_provider(current_provider_id, db, user_id=user_id)
            model_name = await get_model_name(current_model_id, db)

            async for token in provider.stream_chat(model=model_name, messages=history):
                token_str = str(token)
                full_response += token_str
                tokens_emitted += 1
                await ws.send_json({"type": "token", "content": token_str})

            # Sucesso confirmado!
            await mark_model_success(current_model_id, db)
            success = True
            model_id = current_model_id
            provider_id = current_provider_id

        except Exception as e:
            error_msg = str(e)
            logger.warning(
                f"[Auto-Switch] Tentativa {attempt}/{_MAX_FAILOVER_ATTEMPTS} falhou com "
                f"'{current_model_id}': {error_msg}"
            )
            
            # Adiciona o modelo atual à lista de exclusão desta requisição
            excluded_models.append(current_model_id)

            # Classifica a severidade do erro
            severity, reason = ErrorClassifier.classify(error_msg)

            if severity == ErrorSeverity.FATAL:
                # Desativação Permanente (402, 404, etc.)
                from backend.database import check_and_deactivate_model
                await check_and_deactivate_model(current_model_id, error_msg, db)
                await ws.send_json({
                    "type": "model_auto_disabled",
                    "model_id": current_model_id,
                    "display_name": resolved.display_name,
                    "reason": reason,
                })
            else:
                # Cooldown Temporário (400 unavailable, 429, 503)
                await mark_model_cooldown(
                    current_model_id, db, cooldown_seconds=600, error_msg=error_msg
                )
                await ws.send_json({
                    "type": "model_cooldown",
                    "model_id": current_model_id,
                    "display_name": resolved.display_name,
                    "duration_seconds": 600,
                    "reason": reason,
                })

            # Se falhou depois de cuspir tokens parciais (queda de conexão no meio da resposta):
            # Limpa o texto parcial para não gerar respostas duplicadas ou truncadas
            if tokens_emitted > 0:
                await ws.send_json({
                    "type": "stream_rollback",
                    "reason": "Conexão interrompida no meio da geração. Reiniciando no modelo de contingência."
                })
                full_response = ""

            # Continua o loop 'while' para a próxima tentativa!
            continue

    if not success:
        await ws.send_json({
            "type": "error",
            "message": "Limite de tentativas de contingência atingido. Todos os modelos falharam.",
        })
        return None

    return full_response, model_id, provider_id
```

---

## 5. Auditoria e Telemetria em `model_usage_log`

Toda alternância automática realizada pelo motor é registrada de forma detalhada para auditoria:

```sql
INSERT INTO model_usage_log (
    id, model_id, provider_id, conversation_id, user_id,
    was_fallback, fallback_from_model_id, fallback_reason,
    attempt_count, created_at
) VALUES (
    ?, ?, ?, ?, ?, 1, ?, ?, ?, datetime('now')
);
```

Isso alimenta a tabela de **Eventos Recentes de Failover** no painel de administração, permitindo ao usuário e ao desenvolvedor auditar quais modelos estão falhando com mais frequência.
