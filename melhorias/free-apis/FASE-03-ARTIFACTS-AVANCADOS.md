# Fase 3 — Artifacts Avançados (Execução de Código & Diagramas)

> **Dependência:** Fase 0 completa.
> Integra Piston/Judge0 para execução de código server-side e Kroki/QuickChart para renderização de diagramas no painel de Artifacts.

---

## 🎯 Objetivo

Superar as limitações do sandbox JSX client-side atual (`ArtifactPanel.tsx`) adicionando:
1. **Execução de código server-side** em 70+ linguagens (Python, Java, Go, Rust, C++…) via Piston/Judge0
2. **Renderização de diagramas** confiável via Kroki (Mermaid, PlantUML, D2) e QuickChart (gráficos Chart.js)

### Problema Atual

O `ArtifactPanel.tsx` atual:
- Executa apenas **React/JSX** no browser (sandbox iframe com Babel Standalone)
- Código Python, Java, C++ etc. é exibido mas **não executável**
- Diagramas Mermaid dependem do LLM gerar SVG correto (falha frequente)
- Gráficos Chart.js precisam ser montados dentro do JSX sandbox (complexo)

### Solução

```
┌─────────────────────────────────────────────────────────────┐
│                    ArtifactPanel.tsx                         │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  JSX Sandbox │  │ Code Runner  │  │ Diagram Renderer  │  │
│  │  (existente) │  │  (novo)      │  │  (novo)           │  │
│  │              │  │              │  │                   │  │
│  │ React/HTML   │  │ POST /api/   │  │ POST /api/tools/  │  │
│  │ no iframe    │  │ tools/exec   │  │ diagram           │  │
│  │              │  │   ↓          │  │   ↓               │  │
│  │              │  │ Piston API   │  │ Kroki / QuickChart│  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 Tarefas

### T3.1 — Família Code Execution (Execução de Código)

**Diretório:** `backend/tools/families/code_exec/`

#### T3.1.1 — Provider: Piston (Primário)

**Arquivo:** `backend/tools/families/code_exec/piston.py`

- [ ] Classe `PistonProvider(ToolProvider)`
- [ ] Endpoints:
  - Listar linguagens: `GET https://emkc.org/api/v2/piston/runtimes`
  - Executar: `POST https://emkc.org/api/v2/piston/execute`
- [ ] Body de execução:
  ```json
  {
      "language": "python",
      "version": "3.10.0",
      "files": [{"name": "main.py", "content": "print('Hello')"}],
      "stdin": "",
      "args": [],
      "compile_timeout": 10000,
      "run_timeout": 5000,
      "compile_memory_limit": -1,
      "run_memory_limit": -1
  }
  ```
- [ ] Resposta normalizada:
  ```python
  {
      "language": "python",
      "version": "3.10.0",
      "stdout": "Hello\n",
      "stderr": "",
      "exit_code": 0,
      "compile_output": "",
      "execution_time_ms": 45,
      "source": "Piston"
  }
  ```
- [ ] **Cache: NENHUM** (cada execução pode ter resultado diferente)
- [ ] Rate limit: 5 req/s (respeitar com throttle)
- [ ] Timeout: 10s compile + 5s run (padrão, configurável)

**Critérios de Aceite:**
- [ ] Executa Python, JavaScript, Java, C++, Go, Rust no mínimo
- [ ] Captura stdout e stderr separadamente
- [ ] Timeout controlado (não trava se código infinito)
- [ ] Nenhum dado do usuário é logado (segurança)

#### T3.1.2 — Provider: Judge0 CE (Fallback)

**Arquivo:** `backend/tools/families/code_exec/judge0.py`

- [ ] Classe `Judge0Provider(ToolProvider)`
- [ ] Endpoint: `POST https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=true&wait=true`
- [ ] Requer key via `JUDGE0_RAPIDAPI_KEY` (RapidAPI free tier: 50 req/dia)
- [ ] Body:
  ```json
  {
      "source_code": "cHJpbnQoJ0hlbGxvJyk=",  
      "language_id": 71,
      "stdin": ""
  }
  ```
- [ ] Mapear `language_id` para nomes comuns (Python=71, JS=63, Java=62, C++=54…)
- [ ] Se key ausente → provider `disabled`
- [ ] Normaliza para mesmo schema do Piston

#### T3.1.3 — Endpoint REST

**Arquivo:** `backend/routers/tools.py` (adicionar rota)

- [ ] `POST /api/tools/execute`
  ```python
  @router.post("/api/tools/execute")
  async def execute_code(
      request: CodeExecRequest,  # {language, code, stdin?}
      user: dict = Depends(get_current_user)
  ):
      result = await dispatch_tool("code_exec", {
          "language": request.language,
          "code": request.code,
          "stdin": request.stdin or ""
      }, user["id"], db)
      return result
  ```
- [ ] Rate limit: 5 execuções/min por usuário
- [ ] Validações:
  - [ ] Código max 10KB
  - [ ] Linguagem suportada (whitelist)
  - [ ] Usuário autenticado

#### T3.1.4 — Frontend: Botão "Run" no ArtifactPanel

**Arquivo:** `frontend/src/components/ArtifactPanel.tsx`

- [ ] Detectar linguagem do code block (`language` tag no artifact)
- [ ] Se linguagem ≠ jsx/tsx/html → mostrar botão **▶ Executar** em vez de "Preview"
- [ ] Ao clicar:
  1. POST `/api/tools/execute` com o código
  2. Mostrar spinner "Executando..."
  3. Exibir resultado em painel de output (stdout/stderr com syntax highlighting)
  4. Mostrar exit code e tempo de execução
- [ ] Painel de output:
  ```
  ┌─────────────────────────────────────────┐
  │ ▶ Output (Python 3.10 · 45ms · exit 0) │
  ├─────────────────────────────────────────┤
  │ Hello, World!                           │
  │ Resultado: 42                           │
  └─────────────────────────────────────────┘
  ```
- [ ] Se erro:
  ```
  ┌─────────────────────────────────────────┐
  │ ✗ Error (Python 3.10 · 12ms · exit 1)  │
  ├─────────────────────────────────────────┤
  │ Traceback (most recent call last):      │
  │   File "main.py", line 3               │
  │     print(x)                            │
  │ NameError: name 'x' is not defined     │
  └─────────────────────────────────────────┘
  ```

#### T3.1.5 — Testes

- [ ] `backend/tests/test_tools_code_exec.py`
  - [ ] Mock Piston API response
  - [ ] Teste execução Python com stdout
  - [ ] Teste execução com erro (exit code ≠ 0)
  - [ ] Teste timeout (código infinito)
  - [ ] Teste failover Piston → Judge0
  - [ ] Teste rate limit (>5 req/min → 429)

---

### T3.2 — Família Diagrams (Diagramas)

**Diretório:** `backend/tools/families/diagrams/`

#### T3.2.1 — Provider: Kroki (Primário)

**Arquivo:** `backend/tools/families/diagrams/kroki.py`

- [ ] Classe `KrokiProvider(ToolProvider)`
- [ ] Endpoint: `POST https://kroki.io/{diagram_type}/svg`
  - Ou: `GET https://kroki.io/{diagram_type}/svg/{encoded}`
- [ ] Tipos suportados: `mermaid`, `plantuml`, `d2`, `graphviz`, `ditaa`, `c4plantuml`, `excalidraw`
- [ ] Body: texto plano do diagrama
- [ ] Resposta: SVG string
- [ ] Resposta normalizada:
  ```python
  {
      "diagram_type": "mermaid",
      "svg": "<svg>...</svg>",
      "source": "Kroki"
  }
  ```
- [ ] Cache: 1 hora (mesmo input = mesmo diagrama)

**Critérios de Aceite:**
- [ ] Mermaid, PlantUML e D2 renderizam corretamente
- [ ] SVG sanitizado (sem scripts, sem event handlers)
- [ ] Erro de syntax → mensagem clara para o LLM

#### T3.2.2 — Provider: QuickChart (Fallback para gráficos)

**Arquivo:** `backend/tools/families/diagrams/quickchart.py`

- [ ] Classe `QuickChartProvider(ToolProvider)`
- [ ] Endpoint: `POST https://quickchart.io/chart`
- [ ] Body:
  ```json
  {
      "chart": {
          "type": "bar",
          "data": {
              "labels": ["Jan", "Feb", "Mar"],
              "datasets": [{"data": [10, 20, 30]}]
          }
      },
      "width": 500,
      "height": 300,
      "format": "svg"
  }
  ```
- [ ] Tipos de gráfico: `bar`, `line`, `pie`, `doughnut`, `radar`, `scatter`
- [ ] Resposta: SVG ou PNG (URL)
- [ ] Resposta normalizada:
  ```python
  {
      "chart_type": "bar",
      "image_url": "https://quickchart.io/chart/render/...",
      "svg": "<svg>...</svg>",
      "source": "QuickChart"
  }
  ```
- [ ] Cache: 1 hora

#### T3.2.3 — Endpoint REST

**Arquivo:** `backend/routers/tools.py` (adicionar rota)

- [ ] `POST /api/tools/diagram`
  ```python
  @router.post("/api/tools/diagram")
  async def render_diagram(
      request: DiagramRequest,  # {type, source_code}
      user: dict = Depends(get_current_user)
  ):
      result = await dispatch_tool("diagrams", {
          "type": request.type,
          "source": request.source_code
      }, user["id"], db)
      return result
  ```

#### T3.2.4 — Frontend: Renderização no ArtifactPanel

**Arquivo:** `frontend/src/components/ArtifactPanel.tsx`

- [ ] Detectar blocos de código com linguagem `mermaid`, `plantuml`, `d2`
- [ ] Em vez de exibir código raw:
  1. POST `/api/tools/diagram` com o source
  2. Receber SVG
  3. Renderizar SVG inline no painel de preview
  4. Botão "📋 Copiar SVG" e "⬇ Download PNG"
- [ ] Para gráficos (Chart.js):
  1. Detectar JSON de configuração Chart.js no artifact
  2. POST `/api/tools/diagram` com type=`chart`
  3. Renderizar resultado

#### T3.2.5 — Testes

- [ ] `backend/tests/test_tools_diagrams.py`
  - [ ] Mock Kroki renderização Mermaid → SVG
  - [ ] Mock QuickChart renderização bar chart
  - [ ] Teste cache 1h
  - [ ] Teste diagrama com syntax error → erro limpo
  - [ ] Teste sanitização SVG (sem scripts)

---

## 🔒 Considerações de Segurança

### Execução de Código
- **NUNCA** executar código no servidor NexusLocal — sempre via API externa (Piston/Judge0)
- Código é enviado como texto e executado em sandbox isolado do provedor
- Stdout/stderr são truncados em 4096 chars
- Nenhum código do usuário é logado (apenas metadata: linguagem, tempo, exit_code)

### Diagramas SVG
- SVGs retornados pelo Kroki são sanitizados:
  - Remove `<script>` tags
  - Remove event handlers (`onclick`, `onerror`, etc.)
  - Remove `<foreignObject>` 
  - Remove `data:` URLs (XSS vector)
- SVGs são renderizados via `dangerouslySetInnerHTML` com sanitização prévia
- Alternativa segura: converter SVG → `<img src="data:image/svg+xml;base64,...">` (CSP safe)

---

## 📁 Arquivos Criados/Modificados

| Arquivo | Ação |
|---|---|
| `backend/tools/families/code_exec/__init__.py` | Criado |
| `backend/tools/families/code_exec/piston.py` | Criado |
| `backend/tools/families/code_exec/judge0.py` | Criado |
| `backend/tools/families/diagrams/__init__.py` | Criado |
| `backend/tools/families/diagrams/kroki.py` | Criado |
| `backend/tools/families/diagrams/quickchart.py` | Criado |
| `backend/routers/tools.py` | Criado — endpoints /execute e /diagram |
| `frontend/src/components/ArtifactPanel.tsx` | Modificado — botão Run e diagram render |
| `backend/tests/test_tools_code_exec.py` | Criado |
| `backend/tests/test_tools_diagrams.py` | Criado |

---

## ⏱️ Estimativa

| Subtarefa | Tempo |
|---|---|
| T3.1 Code Execution (2 providers + endpoint + frontend) | 5h |
| T3.2 Diagrams (2 providers + endpoint + frontend) | 4h |
| Testes completos | 2h |
| **Total** | **~11h** |

---

## 🔗 Integração com ArtifactPanel Existente

### Estado Atual (`ArtifactPanel.tsx`)
```typescript
// Linha ~26: buildJsxSandbox() — monta iframe para React/JSX
// Linha ~50: hasMountCode — detecta ReactDOM.render/createRoot
// Executa APENAS React/JSX via Babel Standalone + UMD scripts
```

### Mudanças Necessárias

1. **Detecção de linguagem ampliada:**
   ```typescript
   const isExecutable = (lang: string) => 
     ['python', 'javascript', 'java', 'cpp', 'go', 'rust', 'c', 'csharp'].includes(lang)
   
   const isDiagram = (lang: string) =>
     ['mermaid', 'plantuml', 'd2', 'graphviz'].includes(lang)
   ```

2. **Três modos de preview:**
   - `jsx/tsx/html` → sandbox iframe (existente)
   - `python/java/...` → POST para Piston/Judge0 → output panel
   - `mermaid/plantuml/...` → POST para Kroki → SVG inline

3. **UI do output panel:**
   - Fundo escuro (#1a1a2e), monospace font
   - Verde para stdout, vermelho para stderr
   - Badge com linguagem, versão, tempo e exit code
   - Botão "Re-executar" para rodar novamente
