# 🔍 04. Ferramenta de Diagnóstico de Saúde de Provedores
**NexusLocal / Multi+** · Scanner Proativo e Verificação em 1 Clique

---

## 1. Motivação e Valor para o Usuário

Atualmente, o usuário só descobre que um modelo do provedor está sem saldo (402) ou inexistente (404) **no momento em que tenta conversar com ele no chat**. Isso gera frustração reativa.

A **Ferramenta de Diagnóstico de Saúde** inverte essa lógica: com um único clique no painel de administração, o sistema testa proativamente todos os modelos do provedor em segundo plano, desativa os modelos mortos e deixa a lista 100% limpa antes mesmo do usuário abrir o chat.

---

## 2. Fluxo de Execução do Scanner

```
┌────────────────────────────────────────────────────────────────────────┐
│  Usuário clica em "🔍 Diagnosticar Modelos" no card de um provedor     │
│  (ex: LLM7.io · 5 modelos cadastrados)                                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼ POST /api/admin/providers/{id}/health-check
┌────────────────────────────────────────────────────────────────────────┐
│               Execução Paralela Assíncrona no Backend                  │
│                                                                        │
│  Dispara 5 requisições HTTP simultâneas com payload ultra-leve:        │
│  • prompt: "ping"                                                      │
│  • max_tokens: 1                                                       │
│  • timeout: 8.0s por modelo                                            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                ┌───────────────────┼───────────────────┐
                ▼                   ▼                   ▼
          Modelo 1 (200)      Modelo 2 (402)      Modelo 3 (400)
             [Saudável]         [Sem Saldo]        [Indisponível]
                │                   │                   │
                │         UPDATE models             UPDATE quota
                │         SET enabled = 0           SET status = 'cooldown'
                │                   │                   │
                └───────────────────┼───────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│           Relatório em Tempo Real no Modal de Diagnóstico              │
│                                                                        │
│  ✅ 3 Modelos Saudáveis                                                │
│  ⏳ 1 Modelo em Cooldown Temporário                                    │
│  🚫 1 Modelo Desativado Automaticamente (402 Saldo Insuficiente)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Especificação do Endpoint Backend

### 3.1. Rota da API
* **Método:** `POST`
* **Caminho:** `/api/admin/providers/{provider_id}/health-check`
* **Permissão:** Requer usuário autenticado (`get_current_user`).

### 3.2. Implementação em `backend/routers/admin.py`

```python
from fastapi import APIRouter, Depends, HTTPException
import asyncio
from backend.database import get_db, check_and_deactivate_model, mark_model_cooldown
from backend.providers.registry import get_provider, get_model_name
from backend.orchestration.error_classifier import ErrorClassifier, ErrorSeverity

@router.post("/providers/{provider_id}/health-check")
async def provider_health_check(
    provider_id: str, 
    auto_deactivate: bool = True,
    current_user: dict = Depends(get_current_user)
):
    db = await get_db()
    try:
        # 1. Busca modelos do provedor
        async with db.execute(
            "SELECT id, name, display_name, enabled FROM models WHERE provider_id = ?",
            (provider_id,)
        ) as cur:
            models = await cur.fetchall()

        if not models:
            raise HTTPException(status_code=404, detail="Nenhum modelo cadastrado para este provedor.")

        provider = await get_provider(provider_id, db, user_id=current_user["id"])

        # 2. Função de teste unitário por modelo
        async def test_single_model(model_row):
            m_id, m_name, d_name, is_enabled = model_row
            result = {
                "model_id": m_id,
                "display_name": d_name,
                "status": "healthy",
                "status_code": 200,
                "latency_ms": 0,
                "error_detail": None,
                "action_taken": "none"
            }
            start_t = asyncio.get_event_loop().time()
            try:
                # Dispara chamada ultra-leve de 1 token
                async for _ in provider.stream_chat(
                    model=m_name,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1
                ):
                    break  # Recebeu 1 token, teste concluído com sucesso!
                
                result["latency_ms"] = int((asyncio.get_event_loop().time() - start_t) * 1000)
                result["status"] = "healthy"
                
            except Exception as e:
                result["latency_ms"] = int((asyncio.get_event_loop().time() - start_t) * 1000)
                err_str = str(e)
                severity, reason = ErrorClassifier.classify(err_str)
                result["error_detail"] = err_str[:300]
                
                if severity == ErrorSeverity.FATAL:
                    result["status"] = "fatal_error"
                    result["reason"] = reason
                    if auto_deactivate:
                        await check_and_deactivate_model(m_id, err_str, db)
                        result["action_taken"] = "deactivated"
                else:
                    result["status"] = "temporary_unavailable"
                    result["reason"] = reason
                    await mark_model_cooldown(m_id, db, cooldown_seconds=600, error_msg=err_str)
                    result["action_taken"] = "cooldown"
                    
            return result

        # 3. Execução em paralelo com semáforo de concorrência (max 5 por vez)
        sem = asyncio.Semaphore(5)
        async def sem_task(m):
            async with sem:
                return await test_single_model(m)

        tasks = [sem_task(m) for m in models]
        results = await asyncio.gather(*tasks)

        # 4. Agrega o sumário
        summary = {
            "total_tested": len(results),
            "healthy_count": sum(1 for r in results if r["status"] == "healthy"),
            "cooldown_count": sum(1 for r in results if r["status"] == "temporary_unavailable"),
            "deactivated_count": sum(1 for r in results if r["status"] == "fatal_error"),
            "results": results
        }
        return summary
        
    finally:
        await db.close()
```

---

## 4. Interface no Painel de Administração (`AdminPanel.tsx`)

No card de cada provedor, um novo botão de ação rápida é adicionado:

```tsx
<button
  className="btn-secondary btn-sm"
  onClick={() => handleRunDiagnostics(prov.id)}
  disabled={isRunningDiagnostic[prov.id]}
  title="Testar todos os modelos deste provedor e desativar os sem cota"
>
  {isRunningDiagnostic[prov.id] ? (
    <>
      <Spinner size={14} className="spin-icon" />
      <span>Diagnosticando...</span>
    </>
  ) : (
    <>
      <Stethoscope size={14} />
      <span>Diagnosticar Saúde</span>
    </>
  )}
</button>
```

### 4.1. Modal de Resultados do Diagnóstico

Ao concluir (geralmente em 2 a 4 segundos), um modal interativo apresenta o resultado:

```
┌────────────────────────────────────────────────────────────────────────┐
│  🩺 Relatório de Saúde: LLM7.io                                    [✕] │
├────────────────────────────────────────────────────────────────────────┤
│  Sumário: 5 Modelos Verificados · 3 Saudáveis · 1 Cooldown · 1 Desativ │
│                                                                        │
│  [Modelos]                                                             │
│  ✅ GPT Oss:20b              184ms    [200 OK - Saudável]              │
│  ✅ GPT-5.4 Mini             210ms    [200 OK - Saudável]              │
│  ✅ Codestral Latest         320ms    [200 OK - Saudável]              │
│  🟡 Minimax 2.7              150ms    [400 Unavailable · Cooldown 10m] │
│  🚫 Minimax M3                90ms    [402 Sem Saldo · Desativado] [↩] │
│                                                                        │
│  * O modelo Minimax M3 foi desativado automaticamente do seletor.      │
│    Clique em [↩] para reativar caso tenha recarregado créditos.        │
├────────────────────────────────────────────────────────────────────────┤
│                                                [Fechar Relatório]      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Vantagens Práticas para a Operação

1. **Varredura Instantânea:** Em menos de 5 segundos, todos os modelos do provedor são auditados.
2. **Economia Absoluta de Tokens:** O teste consome apenas 1 token por modelo, gastando fração irrelevante de cota.
3. **Limpeza Preventiva:** O usuário nunca mais tenta iniciar uma conversa com um modelo que está offline ou sem saldo.
