# JEV Fast — Plano de Execução Completo

> **Projeto:** Acelerador de velocidade do NexusLocal  
> **Data:** 2026-10-13  
> **Status:** Planejamento  
> **Responsável:** Hermes Agent

---

## 📊 Resumo Executivo

**Objetivo:** Reduzir preprocessing de ~133ms para ~24ms (87% mais rápido) sem perder inteligência.

**Metodologia:** Filosofia JEV (Just Execute Virtual) — eliminar work desnecessário mantendo 100% da lógica original.

**Fases:** 3 fases, 5 otimizações, ~2h de trabalho total.

---

## 🎯 Fases de Implementação

### Fase 1 — P0 (Segurança Máxima) — 45 min

| # | Otimização | Arquivo | Tempo | Risco |
|---|------------|---------|-------|-------|
| 1 | Early Exit Triviais | `smart_router.py` | 15 min | Mínimo |
| 2 | Cache de Contexto Completo | `context_cache.py` | 1h | Baixo |

**Total Fase 1:** 45 min  
**Ganho Esperado:** 133ms → 60ms (-55%)

---

### Fase 2 — P1 (Otimizações Moderadas) — 1.5h

| # | Otimização | Arquivo | Tempo | Risco |
|---|------------|---------|-------|-------|
| 3 | Fingerprint MD5 | `cache/manager.py` | 30 min | Baixo |
| 4 | Batch Query Unificada | `batch_context.py` | 1h | Médio |

**Total Fase 2:** 1.5h  
**Ganho Acumulado:** 60ms → 35ms (-42% adicional)

---

### Fase 3 — P2 (Otimizações Avançadas) — 20 min

| # | Otimização | Arquivo | Tempo | Risco |
|---|------------|---------|-------|-------|
| 5 | Vision Relay Cache | `vision_relay/cache.py` | 20 min | Baixo |

**Total Fase 3:** 20 min  
**Ganho Final:** 35ms → 24ms (-31% adicional)

---

## 📈 Ganhos Acumulados por Fase

```
┌────────────────────────────────────────────────────────────────────┐
│ FASE        GANHO     ACUMULADO    % MELHORIA                      │
├────────────────────────────────────────────────────────────────────┤
│ Baseline    133ms     133ms        0%                              │
│ Fase 1      -73ms     60ms         -55%                            │
│ Fase 2      -25ms     35ms         -74%                            │
│ Fase 3      -11ms     24ms         -82%                            │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Checklist de Implementação

### Pré-Implementação
- [ ] Revisar documentos 01-05
- [ ] Rodar baseline de performance (`scripts/benchmark_pre_jev.py`)
- [ ] Backup do banco (`cp backend/nexuslocal.db backend/nexuslocal_backup_pre_jev.db`)

### Fase 1
- [ ] Implementar Early Exit (`01-early-exit.md`)
- [ ] Rodar `pytest tests/test_smart_router.py`
- [ ] Implementar Model Cache (`02-model-cache.md`)
- [ ] Rodar `pytest tests/test_model_cache.py`
- [ ] Deploy em staging
- [ ] Monitorar métricas por 24h

### Fase 2
- [ ] Implementar Fingerprint (`03-fingerprint-cache.md`)
- [ ] Rodar `pytest tests/test_fingerprint.py`
- [ ] Implementar Batch Query (`04-batch-query.md`)
- [ ] Rodar `pytest tests/test_batch_context.py`
- [ ] Deploy em staging
- [ ] Monitorar métricas por 48h

### Fase 3
- [ ] Implementar Vision Cache (`05-vision-relay-cache.md`)
- [ ] Rodar `pytest tests/test_vision_cache.py`
- [ ] Deploy em staging
- [ ] Monitorar métricas por 24h

### Pós-Implementação
- [ ] Rodar benchmark final (`scripts/benchmark_post_jev.py`)
- [ ] Comparar resultados (baseline vs final)
- [ ] Atualizar documentação
- [ ] Comunicar equipe

---

## 🧪 Planos de Teste

### Testes Unitários
```bash
# Rodar todos os testes JEV
pytest tests/test_*.py -v --tb=short

# Foco em equivalência
pytest tests/test_*.py -k "equivalence" -v
```

### Testes de Performance
```bash
# Benchmark individual
python3 scripts/benchmark_early_exit.py
python3 scripts/benchmark_model_cache.py
python3 scripts/benchmark_fingerprint.py
python3 scripts/benchmark_batch_query.py
python3 scripts/benchmark_vision_cache.py

# Benchmark integrado
python3 scripts/benchmark_full_pipeline.py
```

### Testes de Stress
```bash
# Simula 100 requests concorrentes
python3 scripts/stress_test_jev.py --concurrency 100 --duration 60
```

---

## 📊 Métricas de Monitoramento

### Dashboards (Novos endpoints)
```
GET /api/admin/metrics/jev-fast
{
  "early_exit": {
    "hits": 1247,
    "misses": 1832,
    "avg_latency_ms": 0.3
  },
  "model_cache": {
    "hits": 8934,
    "misses": 145,
    "avg_latency_ms": 0.1,
    "ttl_seconds": 30
  },
  "fingerprint": {
    "hits": 456,
    "misses": 89,
    "avg_latency_ms": 0.001
  },
  "vision_cache": {
    "hits": 234,
    "misses": 56,
    "avg_latency_ms": 0.0,
    "ttl_seconds": 3600
  },
  "total_preprocessing_ms": 24.3,
  "p99_preprocessing_ms": 45.2
}
```

### Logs
```python
logger.info(f"JEV Fast: early_exit={hits}, model_cache={cache_hits}, fingerprint={fp_hits}")
logger.warning(f"JEV Fast: cache miss, falling back to original logic")
```

---

## 🚨 Playbook de Rollback

### Se problema for identificado:

```bash
# 1. Desativar feature flag
curl -X POST http://localhost:8000/api/admin/feature-flags/disable jev-fast

# 2. Rollback para backup
cp backend/nexuslocal_backup_pre_jev.db backend/nexuslocal.db

# 3. Reverter código
git revert HEAD~5..HEAD

# 4. Redeploy
docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

---

## 📚 Arquivos do Projeto

| Arquivo | Descrição | Status |
|---------|-----------|--------|
| `00-visao-geral.md` | Documentação principal | ✅ Criado |
| `01-early-exit.md` | Early exit para trivais | ✅ Criado |
| `02-model-cache.md` | Model cache in-memory | ✅ Criado |
| `03-fingerprint-cache.md` | Fingerprint MD5 | ✅ Criado |
| `04-batch-query.md` | Batch query unificada | ✅ Criado |
| `05-vision-relay-cache.md` | Vision relay cache | ✅ Criado |
| `06-plano-execucao.md` | Este arquivo | ✅ Criado |

---

## 🎓 Glossário

| Termo | Definição |
|-------|-----------|
| **JEV** | Just Execute Virtual — filosofia de otimização |
| **Early Exit** | Retorno imediato para casos conhecidos |
| **Cache In-Memory** | Dados em RAM para evitar queries repetidas |
| **Fingerprint** | Hash ultrarrápido (MD5) para deduplicação |
| **Batch Query** | Query unificada com CTE |
| **Vision Relay** | Serviço de descrição de imagens por LLM |
| **TTL** | Time To Live — tempo de validade do cache |
| **Round-trip** | Ida e volta de rede (request/response) |

---

## ✅ Próximos Passos

1. **Revisão:** Ler documentos 01-05 em detalhes
2. **Decisão:** Aprovar implementação Fase 1 (P0)
3. **Implementação:** Seguir checklist de Fase 1
4. **Testes:** Rodar suite de testes completa
5. **Deploy:** Push para staging e produção
6. **Monitoramento:** Acompanhar métricas por 48h

---

*Documento criado: 2026-10-13*  
*Versão: 1.0*  
*Próxima revisão: Após implementação Fase 1*
