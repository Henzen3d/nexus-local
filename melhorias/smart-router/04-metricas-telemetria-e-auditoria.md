# 🧭 04. Telemetria, Métricas e Dashboard
**Multi+ / NexusLocal** · Planejamento Arquitetural

---

## 1. Esquema de Dados e Auditoria

Para mensurar a eficácia do roteamento inteligente e saber para onde as mensagens estão sendo direcionadas, a tabela existente `model_usage_log` (em [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py)) receberá colunas complementares:

```sql
-- Extensão da tabela model_usage_log
ALTER TABLE model_usage_log ADD COLUMN was_auto_routed INTEGER DEFAULT 0;
ALTER TABLE model_usage_log ADD COLUMN route_intent TEXT;          -- 'code_engineering', 'trivial_quick', etc.
ALTER TABLE model_usage_log ADD COLUMN route_confidence REAL;      -- 0.0 a 1.0
ALTER TABLE model_usage_log ADD COLUMN route_latency_ms REAL;      -- Latência do classificador (< 2.0ms)
ALTER TABLE model_usage_log ADD COLUMN route_policy TEXT;          -- 'economical_free', 'balanced_smart', etc.
```

---

## 2. Métricas de Sucesso do Roteador (KPIs)

O sistema coletará e exibirá 4 indicadores vitais no [`UsageDashboard.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UsageDashboard.tsx):

```
┌────────────────────────────────────────────────────────────────────────┐
│                        KPIs DO AUTO-ROTEADOR INTELIGENTE               │
├─────────────────────┬────────────────────┬─────────────────────────────┤
│  ⚡ Throughput Médio │  💰 Cota Poupada   │  🎯 Precisão de Intenção    │
│     142 tok/s       │     ~62% tokens    │     96.2% confiança média   │
│  (+40% vs manual)   │     preservados    │     em tarefas técnicas     │
└─────────────────────┴────────────────────┴─────────────────────────────┘
```

1. **Taxa de Economia de Tokens Nobres:** Percentual de requisições simples que foram direcionadas para modelos ultra-leves e gratuitos, evitando o consumo desnecessário de cotas do DeepSeek ou Claude.
2. **Latência de Decisão:** Garantir que o tempo do classificador local permaneça consistentemente abaixo de **2 milissegundos**.
3. **Distribuição de Intenções:** Mapeamento visual das atividades do usuário (quantos % do uso foram programação vs pesquisa vs raciocínio).
4. **Incidência de Failover Pós-Roteamento:** Quantas vezes o modelo escolhido pelo roteador precisou de failover imediato por erro 429.

---

## 3. Visualização no `UsageDashboard.tsx`

Um novo card analítico será adicionado ao Dashboard do NexusLocal:

```
┌────────────────────────────────────────────────────────────────────────┐
│  📊 DISTRIBUIÇÃO DE TAREFAS PELO AUTO-ROTEADOR (Últimos 30 Dias)       │
├────────────────────────────────────────────────────────────────────────┤
│  💻 Programação & Código        42%  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ (184 msgs)   │
│  ⚡ Trivial & Perguntas Rápidas 28%  ▓▓▓▓▓▓▓▓▓▓▓▓ (122 msgs)           │
│  🧠 Raciocínio & Lógica         16%  ▓▓▓▓▓▓▓ (70 msgs)                 │
│  🌐 Síntese Web / Pesquisa       8%  ▓▓▓▓ (35 msgs)                    │
│  👁️ Imagens & Multimodal         6%  ▓▓ (26 msgs)                      │
├────────────────────────────────────────────────────────────────────────┤
│  💡 Estimativa de Benefício:                                           │
│  O roteamento automático evitou 122 requisições desnecessárias a       │
│  modelos pesados, economizando ~180.000 tokens e gerando respostas     │
│  quase instantâneas no Groq.                                           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Endpoint de Estatísticas do Roteador

Novo endpoint analítico em [`backend/routers/dashboard.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/dashboard.py):

```python
@router.get("/auto-router/stats")
async def get_auto_router_stats(
    days: int = 30,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Retorna métricas agregadas do roteador:
    - Total de chamadas roteadas vs manuais
    - Distribuição percentual por intenção
    - Modelos mais despachados por categoria
    - Média de latência do classificador
    """
    ...
```
