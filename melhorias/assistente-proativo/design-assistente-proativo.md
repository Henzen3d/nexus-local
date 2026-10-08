# Assistente Proativo — Design Doc

## Visão
Transformar o Multi de chat reativo para assistente proativo que detecta interesse e pesquisa automaticamente em background, entregando resumos como conversa natural entre amigos.

---

## Decisões Arquiteturais

### 1. Gatilho de Detecção (Padrão Recomendado)
- **Heurística híbrida**: LLM leve + regex para entidades
- **Threshold**: 0.7 confidence para emoção + presença de entidade nomeada
- **Cooldown**: 5 minutos entre pesquisas automáticas por tópico
- **Rate limit**: Máx 3 pesquisas/hora/conversa para evitar spam

### 2. Fontes de Pesquisa
- **Primária**: Web search (Brave/DuckDuckGo) — rápido, grátis
- **Fallback**: Playwright browser se resultado insuficiente
- **Sem login**: Apenas conteúdo público (conforme decisão do usuário)

### 3. Entrega
- **Mesma janela**: Se usuário ainda ativo na conversa
- **Nova mensagem**: Se usuário mudou de contexto/janela
- **Formato**: "Fiquei curioso sobre [tópico] e pesquisei..." + resumo + links

### 4. Privacidade
- Dados de pesquisa não salvos permanentemente
- Sem acesso a dados pessoais do usuário
- Logs apenas para debugging (anonimizados)

---

## Componentes Técnicos

```
┌─────────────────────────────────────────────────────────────┐
│                     Multi Chat Interface                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   User Msg  │→│  Detector   │  │  Research Pipeline  │  │
│  │  (emotion + │  │  (LLM+regex)│  │  (web + browser)    │  │
│  │   entities) │  └─────────────┘  └──────────┬──────────┘  │
│  └─────────────┘            │                 │              │
│                             ↓                 ↓              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Delivery   │←│  Synthesis  │←│   Cache (24h TTL)   │  │
│  │  (smart)    │  │  (LLM)      │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Arquivos a Criar/Modificar

### Backend (`/backend/`)
```
proactive/
├── __init__.py
├── detector.py       # Emotion + entity detection
├── researcher.py     # Web search + browser fallback
├── synthesizer.py    # LLM summary generation
├── cache.py          # 24h TTL cache
└── router.py         # FastAPI router

config:
└── proactive_config.py  # Thresholds, rate limits
```

### Frontend (`/frontend/src/`)
```
components/
├── ProactiveIndicator.tsx   # Loading spinner when researching
└── ProactiveMessage.tsx     # Styled research result bubble

hooks/
└── useProactiveResearch.ts  # WebSocket listener for results
```

### Integração Existente
- `chat.py`: Adicionar hook pós-resposta do usuário
- `web_search/providers.py`: Reutilizar existente
- `routers/`: Novo endpoint `/api/proactive/status`

---

## Timeline Estimada

| Fase | Descrição | Tempo |
|------|-----------|-------|
| 1 | Spike detector | 2h |
| 2 | Pipeline pesquisa | 4h |
| 3 | Síntese + entrega | 3h |
| 4 | UI indicators | 2h |
| 5 | Testes + refinamento | 3h |
| **Total** | | **~14h** |

---

## Critérios de Sucesso

- [ ] Detecção de interesse >85% accuracy (teste com 50 mensagens)
- [ ] Pesquisa completa <30s (web) / <60s (browser)
- [ ] Zero falsos positivos em conversas normais
- [ ] Usuário não sente "spam" de pesquisas

---

## Riscos Mitigados

| Risco | Mitigação |
|-------|-----------|
| Spam de pesquisas | Rate limit 3/hora + cooldown 5min/tópico |
| Falsos positivos | Threshold 0.7 + opção disable nas settings |
| Latência alta | Async processing, timeout 60s |
| Custo API | Cache 24h + fallback DuckDuckGo grátis |

---

**Próximo passo:** Aprovação deste design → spike de teste no detector.
