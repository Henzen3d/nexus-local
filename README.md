# ⬡ NexusLocal

Interface de chat local para modelos LLM gratuitos — Groq, Gemini, OpenRouter, Cerebras, NVIDIA NIM, SambaNova, SiliconFlow, FreeTheAI, LLM7.io e LongCat.

## Stack
- **Backend**: Python + FastAPI + WebSockets + aiosqlite
- **Frontend**: React 18 + TypeScript + Vite + Zustand
- **Banco**: SQLite (conversas e configurações persistidas localmente)

## Início Rápido

### Linux / macOS
```bash
chmod +x start.sh
./start.sh
```

### Windows
```
start.bat
```

Acesse **http://localhost:5173** e vá em **Configurações** para adicionar suas chaves de API.

## Providers suportados

| Provider      | Free tier                          | Onde pegar chave                     |
|---------------|------------------------------------|--------------------------------------|
| Groq          | ~14k req/dia, ultra rápido         | console.groq.com                     |
| OpenRouter    | 50+ modelos `:free`                | openrouter.ai/keys                   |
| Google Gemini | 1500 req/dia (muito generoso!)     | aistudio.google.com/apikey           |
| Cerebras      | Free tier, velocidade insana       | cloud.cerebras.ai                    |
| NVIDIA NIM    | $25 créditos iniciais              | build.nvidia.com                     |
| SambaNova     | Free tier com Llama 3.3 405B       | cloud.sambanova.ai                   |
| SiliconFlow   | Free tier / Cupom com vários LLMs  | siliconflow.cn                       |
| FreeTheAI     | 50+ modelos gratuitos, req. checkin| freetheai.xyz / discord.gg/secrets   |
| LLM7.io       | Vários LLMs com rate limits grátis | dash.llm7.io                         |
| LongCat       | Janela de contexto gigante (1M)    | api.longcat.chat                     |

## Recursos Avançados

O NexusLocal possui recursos avançados de orquestração de IA que otimizam a qualidade e a interatividade das respostas:

*   **[Prompt Enhancer (Varinha Mágica ✦)](file:///j:/Arquivos%20Osmar/Multi+/DOCUMENTATION.md#41-prompt-enhancer-varinha-magica-)**: Reescreve e aprimora o seu prompt simples usando um modelo secundário de engenharia de prompt antes de enviá-lo ao modelo principal.
*   **[Modo Fusion (🧬 Fusão)](file:///j:/Arquivos%20Osmar/Multi+/DOCUMENTATION.md#42-modo-fusion--fusao-de-respostas)**: Dispara a mesma pergunta para vários LLMs em paralelo e utiliza um modelo Juiz para consolidar a melhor resposta possível em tempo real.
*   **[Sistema de Artifacts (Painel Split-Screen)](file:///j:/Arquivos%20Osmar/Multi+/DOCUMENTATION.md#43-sistema-de-artifacts-painel-split-screen)**: Identifica códigos, SVGs, HTML ou documentos longos e os abre de forma interativa em um painel lateral separado do chat.

Para ver os esquemas de banco de dados, detalhes de arquitetura e funcionamento interno de cada recurso, consulte a **[Documentação Completa do Sistema](file:///j:/Arquivos%20Osmar/Multi+/DOCUMENTATION.md)**.

## Estrutura

```
nexuslocal/
├── backend/
│   ├── main.py              ← FastAPI app
│   ├── database.py          ← SQLite + schema
│   ├── models.py            ← Pydantic models
│   ├── providers/
│   │   ├── base.py          ← Adapter OpenAI-compat universal
│   │   └── registry.py      ← Roteamento por provider
│   ├── fusion/
│   │   ├── __init__.py
│   │   └── orchestrator.py  ← Orquestrador do modo Fusion
│   └── routers/
│       ├── chat.py          ← WebSocket streaming
│       ├── conversations.py ← CRUD histórico
│       ├── admin.py         ← Gerenciar chaves/modelos
│       ├── enhancer.py      ← Roteador do Prompt Enhancer
│       ├── fusion.py        ← Roteador das configurações de Fusão
│       └── artifacts.py     ← Roteador dos Artefatos
└── frontend/
    └── src/
        ├── components/      ← Sidebar, Chat, Admin, ArtifactPanel, etc.
        ├── hooks/           ← useChat (WebSocket)
        ├── store/           ← Zustand state
        └── api/             ← HTTP client
```

## Próximos módulos planejados
- [ ] **Self-Scaffold** — loop auto-avaliador inspirado no Ornith
- [ ] **System Prompts** — templates de persona por conversa
- [ ] **Export** — exportar conversa como Markdown/JSON
- [ ] **Fase 3 do Sistema de Artifacts** — edição inline e renderização dinâmica avançada

