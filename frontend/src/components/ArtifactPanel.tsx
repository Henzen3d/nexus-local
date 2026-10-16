import { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import {
  Copy, Check, Download, ExternalLink, X, FileCode, FileText, Image, Globe,
  ChevronLeft, ChevronRight, Pencil, Send, Atom, Play, Square, Eye, Code2,
  Terminal, Loader2, RefreshCw, AlertCircle, CheckCircle2, Network, BarChart2
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatContext } from '../context/ChatContext'
import { ThinkingParser } from '../utils/ThinkingParser'
import { highlightCode } from './CodeBlock'
import { api } from '../api/client'

/**
 * buildJsxSandbox — constrói um documento HTML completo que executa
 * um componente React/JSX usando Babel Standalone para transpilação
 * in-browser.
 *
 * Etapas de pré-processamento:
 * 1. Remove imports de ES module de react / react-dom (são UMD globals).
 * 2. Injeta os hooks/utilitários React mais comuns como globais desestruturados.
 * 3. Remove palavras-chave export (inválidas em contexto de script UMD).
 * 4. Detecta o componente de entrada e injeta o código de mount automático.
 * 5. Captura erros de transpilação e runtime e os exibe inline.
 *
 * A sandbox usa apenas `sandbox="allow-scripts"` (sem allow-same-origin)
 * para isolar o código gerado por LLM do contexto da aplicação host.
 */
function buildJsxSandbox(rawCode: string, title: string): string {
  let code = rawCode

  // 1. Remove imports de react e react-dom (carregados como UMD globals via CDN)
  code = code.replace(/^import\s+.*from\s+['"]react(?:-dom)?(?:\/[^'"]*)?['"];?\r?\n?/gm, '')
  // Remove imports de type (TypeScript — Babel vai remover mas convem limpar)
  code = code.replace(/^import\s+type\s+[^;]*;?\r?\n?/gm, '')
  // Remove export keywords (inválidos em contexto de script)
  code = code.replace(/^export\s+default\s+/gm, '')
  code = code.replace(/^export\s+(?=function|class|const|let|var)/gm, '')
  code = code.trim()

  // 2. Injeta os hooks/utilitários mais comuns do React como globais
  // (antes eram acessíveis via import; agora veem do global window.React)
  const REACT_GLOBALS = [
    'useState', 'useEffect', 'useRef', 'useCallback', 'useMemo',
    'useContext', 'createContext', 'useReducer', 'useLayoutEffect',
    'useId', 'forwardRef', 'memo', 'Fragment', 'useTransition',
    'useDeferredValue', 'startTransition', 'Suspense', 'lazy',
  ].join(', ')
  code = `const { ${REACT_GLOBALS} } = React;\n\n${code}`

  // 3. Auto-mount: injeta código de montagem se o componente não incluiu
  const hasMountCode = /ReactDOM\s*\.\s*(render|createRoot)/.test(code)
  if (!hasMountCode) {
    // Procura pelo último identificador de componente (inicial maúscula)
    const matches = [...code.matchAll(/(?:^function|^const|^class)\s+([A-Z][a-zA-Z0-9_$]*)/gm)]
    const entry = matches.length > 0 ? matches[matches.length - 1][1] : 'App'
    code += `\n\n// Auto-mounted by NexusLocal\ntry {\n  ReactDOM.createRoot(document.getElementById('root')).render(\n    React.createElement(${entry})\n  );\n} catch (__err) {\n  document.getElementById('root').innerHTML =\n    '<div style="padding:16px;color:#dc2626;font-family:monospace;font-size:13px;white-space:pre-wrap;border-left:4px solid #ef4444;background:#fef2f2;margin:16px;border-radius:4px">\\u26a0\\ufe0f Render Error\\n\\n' + __err.message + '</div>';\n}`
  }

  // 4. Escape do título para inserção segura no HTML
  const safeTitle = title.replace(/[<>&"]/g, (c) =>
    ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c] ?? c)
  )

  // 5. Monta o documento HTML completo
  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${safeTitle}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  </style>
</head>
<body>
  <div id="root"></div>
  <div id="__nexus-error" style="display:none;padding:16px;background:#fef2f2;color:#dc2626;font-family:monospace;font-size:13px;border-left:4px solid #ef4444;white-space:pre-wrap;margin:16px;border-radius:4px"></div>

  <!-- React 18 UMD: window.React / window.ReactDOM -->
  <script src="https://unpkg.com/react@18/umd/react.development.js"><\/script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"><\/script>
  <!-- Babel Standalone: transpila JSX + TypeScript no browser -->
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"><\/script>

  <!-- Captura de erros de parse (Babel) e runtime (JS) -->
  <script>
    window.addEventListener('error', function(ev) {
      var el = document.getElementById('__nexus-error');
      if (!el) return;
      el.style.display = 'block';
      el.textContent = '\\u26a0\\ufe0f ' + ev.message;
      if (ev.error && ev.error.stack) el.textContent += '\\n\\n' + ev.error.stack;
      var root = document.getElementById('root');
      if (root) root.style.display = 'none';
    });
  <\/script>

  <!-- Componente do usuário: transpilado in-browser pelo Babel -->
  <script type="text/babel" data-presets="react,typescript">
${code}
  <\/script>
</body>
</html>`
}

/**
 * buildJsSandbox — gera um documento HTML seguro para rodar JavaScript
 * interceptando chamadas de console.log/error/warn para exibi-las na tela.
 */
function buildJsSandbox(userCode: string): string {
  const escapedCode = userCode.replace(/<\/script>/g, '<\\/script>')
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {
      background: #1e1e1e;
      color: #d4d4d4;
      font-family: 'Fira Code', Consolas, Monaco, monospace;
      font-size: 13px;
      margin: 0;
      padding: 14px;
      line-height: 1.5;
    }
    .log-line {
      border-bottom: 1px solid #2d2d2d;
      padding: 4px 0;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .log-log { color: #d4d4d4; }
    .log-error { color: #f87171; border-left: 3px solid #ef4444; padding-left: 6px; }
    .log-warn { color: #fbbf24; border-left: 3px solid #f59e0b; padding-left: 6px; }
    .log-info { color: #60a5fa; }
    .system-msg { color: #888; font-style: italic; margin-top: 10px; }
  </style>
</head>
<body>
  <div id="console-output"></div>

  <script>
    const output = document.getElementById('console-output');
    function appendLog(args, type = 'log') {
      const line = document.createElement('div');
      line.className = 'log-line log-' + type;
      line.textContent = args.map(arg => {
        if (typeof arg === 'object') {
          try { return JSON.stringify(arg, null, 2); } catch(e) { return String(arg); }
        }
        return String(arg);
      }).join(' ');
      output.appendChild(line);
      window.scrollTo(0, document.body.scrollHeight);
    }

    // Intercepta console
    window.console = {
      log: (...args) => appendLog(args, 'log'),
      error: (...args) => appendLog(args, 'error'),
      warn: (...args) => appendLog(args, 'warn'),
      info: (...args) => appendLog(args, 'info')
    };

    window.addEventListener('error', (e) => {
      appendLog([e.message + ' (linha ' + e.lineno + ')'], 'error');
    });

    try {
      appendLog(['Executando JavaScript...'], 'info');
      const script = document.createElement('script');
      script.textContent = \`${escapedCode}\`;
      document.body.appendChild(script);
      appendLog(['\\n--- Execução Concluída com sucesso ---'], 'system-msg');
    } catch (err) {
      appendLog([err.message], 'error');
    }
  </script>
</body>
</html>`
}

/**
 * buildPythonSandbox — gera um documento HTML que carrega Pyodide via CDN
 * para interpretar e rodar código Python diretamente no navegador.
 */
function buildPythonSandbox(userCode: string): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {
      background: #1e1e1e;
      color: #d4d4d4;
      font-family: 'Fira Code', Consolas, Monaco, monospace;
      font-size: 13px;
      margin: 0;
      padding: 14px;
      line-height: 1.5;
    }
    .log-line {
      border-bottom: 1px solid #2d2d2d;
      padding: 4px 0;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .log-log { color: #d4d4d4; }
    .log-error { color: #f87171; border-left: 3px solid #ef4444; padding-left: 6px; }
    .log-info { color: #60a5fa; }
    .system-msg { color: #888; font-style: italic; margin-top: 10px; }
  </style>
  <script src="https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js"></script>
</head>
<body>
  <div id="console-output">
    <div class="log-line log-info">Inicializando Pyodide WebAssembly (baixando interpretador Python)...</div>
  </div>

  <script>
    const output = document.getElementById('console-output');
    function appendLog(msg, type = 'log') {
      const line = document.createElement('div');
      line.className = 'log-line log-' + type;
      line.textContent = String(msg);
      output.appendChild(line);
      window.scrollTo(0, document.body.scrollHeight);
    }

    async function main() {
      try {
        let pyodide = await loadPyodide();
        output.innerHTML = "";
        appendLog("Pyodide carregado. Executando script Python...", "info");
        pyodide.setStdout({ batched: (msg) => appendLog(msg, 'log') });
        pyodide.setStderr({ batched: (msg) => appendLog(msg, 'error') });
        await pyodide.runPythonAsync(\`${userCode.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`);
        appendLog("\\n--- Execução Concluída ---", "system-msg");
      } catch (err) {
        appendLog(err.message, "error");
      }
    }
    main();
  </script>
</body>
</html>`
}

export function ArtifactPanel() {
  const { t } = useTranslation()
  const { activeArtifact, artifactHistory, setArtifactPanelOpen, navigateVersion, isStreaming } = useStore()
  const { sendMessage } = useChatContext()
  const [copied, setCopied] = useState(false)
  const [editPrompt, setEditPrompt] = useState('')
  const editInputRef = useRef<HTMLTextAreaElement>(null)

  // Modo de visualização de arquivo (prévia ou código)
  const [viewMode, setViewMode] = useState<'preview' | 'code'>('preview')

  // Estados para execução segura client-side (sandbox iframe legada)
  const [isRunningCode, setIsRunningCode] = useState(false)
  const [runKey, setRunKey] = useState(0)

  // Estados para execução de código server-side (Piston / Judge0)
  const [isExecutingRemote, setIsExecutingRemote] = useState(false)
  const [execResult, setExecResult] = useState<{
    language?: string
    version?: string
    stdout?: string
    stderr?: string
    exit_code?: number
    compile_output?: string
    execution_time_ms?: number
    source?: string
    error?: string
  } | null>(null)

  // Estados para renderização de diagramas (Kroki / QuickChart)
  const [renderedSvg, setRenderedSvg] = useState<string | null>(null)
  const [diagramLoading, setDiagramLoading] = useState(false)
  const [diagramError, setDiagramError] = useState<string | null>(null)

  // Reseta estado de execução e visualização ao trocar de artefato/versão
  useEffect(() => {
    setIsRunningCode(false)
    setIsExecutingRemote(false)
    setExecResult(null)
    setViewMode('preview')
  }, [activeArtifact?.id])

  // Garante que tags de raciocínio (ex: <think>...</think> ou </think> órfãos) do modelo
  // sejam removidas caso o artifact venha do histórico anterior do banco
  const cleanContent = activeArtifact
    ? (ThinkingParser.parse(activeArtifact.content).answer || activeArtifact.content)
    : ''

  /**
   * Normaliza o tipo do artefato para garantir compatibilidade com MIME types (ex: text/markdown)
   * e formatos legados ou variantes sem que a interface quebre ou fique em branco.
   */
  const normalizedType = useMemo(() => {
    if (!activeArtifact?.type) return 'markdown'
    const raw = activeArtifact.type.toLowerCase().trim()
    if (raw === 'text/markdown' || raw === 'markdown' || raw === 'md') return 'markdown'
    if (raw === 'text/html' || raw === 'html' || raw === 'htm') return 'html'
    if (raw === 'image/svg+xml' || raw === 'svg') return 'svg'
    if (raw === 'jsx' || raw === 'tsx' || raw === 'react') return 'jsx'
    if (['diagram', 'mermaid', 'plantuml', 'd2', 'graphviz', 'chart'].includes(raw)) return 'diagram'
    if (raw === 'code') return 'code'
    if (raw.startsWith('text/')) return 'markdown'
    // Se o tipo for desconhecido, analisa o conteúdo para inferir o tipo
    if (cleanContent.startsWith('<!DOCTYPE html') || cleanContent.startsWith('<html')) return 'html'
    if (cleanContent.startsWith('<svg')) return 'svg'
    if (/^\s*(sequenceDiagram|classDiagram|erDiagram|gantt|pie|flowchart|graph\s+[TBRLE]|gitGraph)/i.test(cleanContent)) return 'diagram'
    if (/^\s*@startuml/i.test(cleanContent)) return 'diagram'
    if (/^\s*\{\s*"chart"\s*:/i.test(cleanContent)) return 'diagram'
    return 'markdown'
  }, [activeArtifact?.type, cleanContent])

  /**
   * Determina a variante do diagrama (mermaid, plantuml, d2, graphviz, chart)
   */
  const diagramType = useMemo(() => {
    if (!activeArtifact) return 'mermaid'
    const raw = activeArtifact.type?.toLowerCase().trim() || ''
    if (raw === 'plantuml' || /^\s*@startuml/i.test(cleanContent)) return 'plantuml'
    if (raw === 'd2' || (/^\s*(\w+)\s*\{/i.test(cleanContent) && cleanContent.includes('->'))) return 'd2'
    if (raw === 'graphviz' || /^\s*(digraph|graph)\s*\{/i.test(cleanContent)) return 'graphviz'
    if (raw === 'chart' || /^\s*\{\s*"chart"\s*:/i.test(cleanContent)) return 'chart'
    return 'mermaid'
  }, [activeArtifact, cleanContent])

  /**
   * Detecta a linguagem para syntax highlight a partir do tipo/título do artifact.
   * Títulos de código vêm do backend no formato "{LANG} Code" (ex: "PYTHON Code").
   */
  const highlightLang = useMemo(() => {
    if (!activeArtifact) return ''
    const type = normalizedType
    if (type === 'html') return 'html'
    if (type === 'svg') return 'svg'
    if (type === 'jsx') return 'jsx'
    if (type === 'markdown') return 'markdown'
    if (type === 'diagram') return diagramType

    const title = activeArtifact.title.toLowerCase()
    const known: Array<[RegExp, string]> = [
      [/\b(python|py)\b/, 'python'],
      [/\b(typescript|ts)\b/, 'typescript'],
      [/\b(javascript|js)\b/, 'javascript'],
      [/\b(tsx)\b/, 'tsx'],
      [/\b(jsx)\b/, 'jsx'],
      [/\b(html)\b/, 'html'],
      [/\b(css)\b/, 'css'],
      [/\b(json)\b/, 'json'],
      [/\b(bash|shell|sh)\b/, 'bash'],
      [/\b(yaml|yml)\b/, 'yaml'],
      [/\b(sql)\b/, 'sql'],
      [/\b(go|golang)\b/, 'go'],
      [/\b(rust|rs)\b/, 'rust'],
      [/\b(java)\b/, 'java'],
      [/\b(c\+\+|cpp)\b/, 'cpp'],
      [/\b(c#|csharp)\b/, 'csharp'],
      [/\b(php)\b/, 'php'],
      [/\b(ruby|rb)\b/, 'ruby'],
      [/\b(swift)\b/, 'swift'],
      [/\b(kotlin|kt)\b/, 'kotlin'],
    ]
    for (const [re, lang] of known) {
      if (re.test(title)) return lang
    }
    const first = title.split(/[\s._-]+/)[0]?.replace(/[^a-z0-9+#]/g, '')
    if (first && first.length >= 1 && first.length <= 12 && first !== 'code') return first
    return ''
  }, [activeArtifact, normalizedType, diagramType])

  const highlightedCode = useMemo(
    () => (cleanContent ? highlightCode(cleanContent, highlightLang) : ''),
    [cleanContent, highlightLang]
  )

  const getFriendlyFormatName = (type: string) => {
    switch (type) {
      case 'html': return 'HTML'
      case 'markdown': return 'Markdown'
      case 'svg': return 'SVG'
      case 'jsx': return 'React'
      case 'diagram': return diagramType === 'chart' ? 'Gráfico' : `Diagrama (${diagramType})`
      default: return 'Código'
    }
  }

  const getRunnableLanguage = () => {
    if (normalizedType !== 'code' || !activeArtifact) return null
    const lang = (highlightLang || '').toLowerCase()
    const titleLower = (activeArtifact.title || '').toLowerCase()
    const supported = [
      'python', 'py', 'javascript', 'js', 'typescript', 'ts',
      'java', 'cpp', 'c', 'csharp', 'cs', 'go', 'rust', 'rs',
      'ruby', 'rb', 'php', 'bash', 'sh', 'swift', 'kotlin', 'kt', 'sql'
    ]
    for (const s of supported) {
      if (lang === s || titleLower.includes(s)) {
        if (s === 'py') return 'python'
        if (s === 'js') return 'javascript'
        if (s === 'ts') return 'typescript'
        if (s === 'sh') return 'bash'
        if (s === 'cs') return 'csharp'
        if (s === 'rs') return 'rust'
        if (s === 'rb') return 'ruby'
        if (s === 'kt') return 'kotlin'
        return s
      }
    }
    return null
  }

  const getFileExtension = (type: string) => {
    switch (type) {
      case 'html': return 'html'
      case 'markdown': return 'md'
      case 'svg': return 'svg'
      case 'jsx': return 'jsx'
      case 'diagram': return renderedSvg ? 'svg' : 'txt'
      default: return 'txt'
    }
  }

  const getMimeType = (type: string) => {
    switch (type) {
      case 'html': return 'text/html'
      case 'markdown': return 'text/markdown'
      case 'svg': return 'image/svg+xml'
      case 'diagram': return renderedSvg ? 'image/svg+xml' : 'text/plain'
      default: return 'text/plain'
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(cleanContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const mime = getMimeType(normalizedType)
    const content = (normalizedType === 'diagram' && renderedSvg) ? renderedSvg : cleanContent
    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    
    const rawTitle = activeArtifact?.title || 'artifact'
    const safeTitle = rawTitle.replace(/[^a-z0-9\s-_.]/gi, '')
    const ext = getFileExtension(normalizedType)
    a.download = safeTitle.toLowerCase().endsWith(`.${ext}`) ? safeTitle : `${safeTitle}.${ext}`
    
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleOpenNewTab = () => {
    const mime = getMimeType(normalizedType)
    const content = (normalizedType === 'diagram' && renderedSvg) ? renderedSvg : cleanContent
    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
  }

  // ── Renderização Kroki / QuickChart ────────────────────────────────
  const fetchDiagram = useCallback(async () => {
    if (normalizedType !== 'diagram' || !cleanContent) return
    setDiagramLoading(true)
    setDiagramError(null)
    try {
      const res = await api.renderDiagram(diagramType, cleanContent)
      if (res.success && res.data?.svg) {
        setRenderedSvg(res.data.svg)
      } else {
        setDiagramError(res.error || 'Falha ao renderizar diagrama')
      }
    } catch (err: any) {
      setDiagramError(err.message || 'Erro ao conectar ao renderizador Kroki')
    } finally {
      setDiagramLoading(false)
    }
  }, [normalizedType, diagramType, cleanContent])

  useEffect(() => {
    if (normalizedType === 'diagram') {
      fetchDiagram()
    } else {
      setRenderedSvg(null)
      setDiagramError(null)
    }
  }, [normalizedType, diagramType, cleanContent, fetchDiagram])

  // ── Execução de Código Remota (Piston / Judge0) ────────────────────
  const handleExecuteCode = async () => {
    const lang = getRunnableLanguage()
    if (!lang || !cleanContent || isExecutingRemote) return
    setIsExecutingRemote(true)
    setExecResult(null)
    try {
      const res = await api.executeCode(lang, cleanContent)
      if (res.success && res.data) {
        setExecResult(res.data)
      } else {
        setExecResult({
          error: res.error || 'Falha na execução',
          stdout: '',
          stderr: res.error || '',
          exit_code: 1,
        })
      }
    } catch (err: any) {
      setExecResult({
        error: err.message || 'Erro ao conectar ao executor de código',
        stdout: '',
        stderr: err.message || '',
        exit_code: 1,
      })
    } finally {
      setIsExecutingRemote(false)
    }
  }

  const renderIcon = (type: string) => {
    switch (type) {
      case 'html':
        return <Globe size={16} className="text-blue-500" />
      case 'svg':
        return <Image size={16} className="text-green-500" />
      case 'markdown':
        return <FileText size={16} className="text-orange-500" />
      case 'jsx':
        return <Atom size={16} className="text-cyan-500" />
      case 'diagram':
        return diagramType === 'chart' ? (
          <BarChart2 size={16} className="text-emerald-500" />
        ) : (
          <Network size={16} className="text-emerald-500" />
        )
      default:
        return <FileCode size={16} className="text-purple-500" />
    }
  }

  const handleEdit = () => {
    if (!editPrompt.trim() || !activeArtifact || isStreaming) return

    const typeLabel: Record<string, string> = {
      html: 'HTML',
      svg: 'SVG',
      markdown: 'Markdown',
      diagram: 'diagrama',
      code: 'código',
    }
    const label = typeLabel[normalizedType] ?? normalizedType.toUpperCase()

    const wrappedContent = normalizedType !== 'markdown'
      ? `\`\`\`${normalizedType}\n${cleanContent}\n\`\`\``
      : `\`\`\`markdown\n${cleanContent}\n\`\`\``

    const fullPrompt =
      `Edite o seguinte documento ${label} conforme a instrução abaixo.\n` +
      `Retorne o documento completo e atualizado dentro de um bloco de código, sem texto explicativo fora do bloco.\n\n` +
      `[DOCUMENTO ATUAL: "${activeArtifact.title}"]\n${wrappedContent}\n[/DOCUMENTO ATUAL]\n\n` +
      `Instrução: ${editPrompt.trim()}`

    const displayText = `✏️ ${activeArtifact.title}: ${editPrompt.trim()}`

    sendMessage(fullPrompt, displayText)
    setEditPrompt('')
  }

  const handleEditKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleEdit()
    }
  }

  if (!activeArtifact) return null

  return (
    <div className="artifact-panel">
      {/* Toolbar */}
      <div className="artifact-toolbar">
        <div className="artifact-info">
          {['html', 'svg', 'markdown', 'jsx', 'diagram'].includes(normalizedType) ? (
            <div className="segmented-control">
              <button 
                className={`segmented-btn custom-tooltip-trigger ${viewMode === 'preview' ? 'active' : ''}`}
                onClick={() => setViewMode('preview')}
                data-tooltip={t('artifacts.preview', 'Prévia')}
              >
                <Eye size={14} />
              </button>
              <button 
                className={`segmented-btn custom-tooltip-trigger ${viewMode === 'code' ? 'active' : ''}`}
                onClick={() => setViewMode('code')}
                data-tooltip={t('artifacts.code', 'Código')}
              >
                <Code2 size={14} />
              </button>
            </div>
          ) : (
            renderIcon(normalizedType)
          )}
          
          <span className="artifact-title" title={activeArtifact.title}>
            {activeArtifact.title}
            {['html', 'svg', 'markdown', 'jsx', 'diagram'].includes(normalizedType) && (
              <>
                <span className="artifact-title-separator"> · </span>
                <span className="artifact-title-format">{getFriendlyFormatName(normalizedType)}</span>
              </>
            )}
          </span>
          <span className="artifact-version-tag">v{activeArtifact.version}</span>
        </div>

        {/* Navegação entre versões */}
        {artifactHistory.length > 1 && (() => {
          const currentIdx = artifactHistory.findIndex((a) => a.id === activeArtifact.id)
          const total = artifactHistory.length
          return (
            <div className="artifact-version-nav">
              <button
                className="artifact-action-btn custom-tooltip-trigger"
                onClick={() => navigateVersion('prev')}
                disabled={currentIdx <= 0}
                data-tooltip={t('artifacts.prevVersion', 'Versão anterior')}
              >
                <ChevronLeft size={14} />
              </button>
              <span className="artifact-version-indicator">
                {currentIdx + 1} / {total}
              </span>
              <button
                className="artifact-action-btn custom-tooltip-trigger"
                onClick={() => navigateVersion('next')}
                disabled={currentIdx >= total - 1}
                data-tooltip={t('artifacts.nextVersion', 'Próxima versão')}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          )
        })()}
        
        <div className="artifact-actions">
          {getRunnableLanguage() && (
            <button
              className={`artifact-action-btn run-btn custom-tooltip-trigger ${isExecutingRemote ? 'running' : ''}`}
              onClick={handleExecuteCode}
              disabled={isExecutingRemote}
              data-tooltip={isExecutingRemote ? t('artifacts.runningCode', 'Executando...') : t('artifacts.runCode', 'Executar código (Piston)')}
            >
              {isExecutingRemote ? (
                <Loader2 size={14} className="animate-spin text-primary" />
              ) : (
                <Play size={14} className="text-emerald-500" />
              )}
            </button>
          )}

          <button 
            className="artifact-action-btn custom-tooltip-trigger" 
            onClick={handleCopy} 
            data-tooltip={t('artifacts.copyContent', 'Copiar conteúdo')}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          
          <button 
            className="artifact-action-btn custom-tooltip-trigger" 
            onClick={handleDownload} 
            data-tooltip={t('artifacts.downloadFile', 'Baixar arquivo')}
          >
            <Download size={14} />
          </button>
          
          <button 
            className="artifact-action-btn custom-tooltip-trigger" 
            onClick={handleOpenNewTab} 
            data-tooltip={t('artifacts.openNewTab', 'Abrir em nova aba')}
          >
            <ExternalLink size={14} />
          </button>

          <div className="artifact-toolbar-divider" />
          
          <button 
            className="artifact-action-btn close-btn custom-tooltip-trigger" 
            onClick={() => setArtifactPanelOpen(false)} 
            data-tooltip={t('artifacts.closePanel', 'Fechar painel')}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Viewer */}
      <div className="artifact-viewer">
        {['html', 'svg', 'markdown', 'jsx', 'diagram'].includes(normalizedType) && viewMode === 'code' ? (
          <pre className="artifact-code-content">
            <code
              className={`language-${highlightLang || normalizedType}`}
              dangerouslySetInnerHTML={{ __html: highlightedCode }}
            />
          </pre>
        ) : (
          <>
            {normalizedType === 'html' && (
              <iframe
                sandbox="allow-scripts"
                srcDoc={cleanContent}
                referrerPolicy="no-referrer"
                title={activeArtifact.title}
              />
            )}
            
            {normalizedType === 'markdown' && (
              <div className="artifact-markdown-content">
                <ReactMarkdown 
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({ node, ...props }) => (
                      <div className="markdown-table-wrapper">
                        <table className="markdown-table" {...props} />
                      </div>
                    )
                  }}
                >
                  {cleanContent}
                </ReactMarkdown>
              </div>
            )}

            {normalizedType === 'svg' && (
              <div className="artifact-svg-content">
                <img 
                  src={"data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(cleanContent)))} 
                  alt={activeArtifact.title} 
                />
              </div>
            )}

            {normalizedType === 'jsx' && (
              <iframe
                sandbox="allow-scripts"
                srcDoc={buildJsxSandbox(cleanContent, activeArtifact.title)}
                referrerPolicy="no-referrer"
                title={activeArtifact.title}
              />
            )}

            {normalizedType === 'diagram' && (
              <div className="artifact-diagram-container">
                {diagramLoading && (
                  <div className="artifact-diagram-loading">
                    <Loader2 size={24} className="animate-spin text-primary" />
                    <span>{t('artifacts.renderingDiagram', 'Renderizando diagrama via Kroki...')}</span>
                  </div>
                )}
                {diagramError && (
                  <div className="artifact-diagram-error">
                    <div className="artifact-diagram-error-header">
                      <AlertCircle size={16} className="text-red-500" />
                      <strong>{t('artifacts.diagramError', 'Falha ao renderizar diagrama')}</strong>
                    </div>
                    <pre className="artifact-diagram-error-text">{diagramError}</pre>
                    <button 
                      className="artifact-diagram-retry-btn" 
                      onClick={fetchDiagram}
                    >
                      <RefreshCw size={13} /> {t('common.retry', 'Tentar novamente')}
                    </button>
                  </div>
                )}
                {!diagramLoading && !diagramError && renderedSvg && (
                  <div 
                    className="artifact-diagram-svg-wrap"
                    dangerouslySetInnerHTML={{ __html: renderedSvg }} 
                  />
                )}
              </div>
            )}
          </>
        )}

        {normalizedType === 'code' && (
          <div className="artifact-code-wrapper">
            <pre className="artifact-code-content">
              <code
                className={`language-${highlightLang || 'code'}`}
                dangerouslySetInnerHTML={{ __html: highlightedCode }}
              />
            </pre>

            {/* Console de saída da execução remota Piston / Judge0 */}
            {execResult && (
              <div className="artifact-exec-console">
                <div className="artifact-console-header">
                  <div className="artifact-console-meta">
                    <Terminal size={13} />
                    <span className="artifact-console-status">
                      {execResult.exit_code === 0 ? (
                        <span className="status-success">
                          <CheckCircle2 size={12} /> {t('artifacts.execSuccess', 'Sucesso')}
                        </span>
                      ) : (
                        <span className="status-error">
                          <AlertCircle size={12} /> {t('artifacts.execFailed', 'Erro')} ({execResult.exit_code ?? 1})
                        </span>
                      )}
                    </span>
                    <span className="artifact-console-tag">
                      {execResult.language} {execResult.version || ''}
                    </span>
                    {execResult.execution_time_ms !== undefined && (
                      <span className="artifact-console-tag">
                        {execResult.execution_time_ms}ms
                      </span>
                    )}
                    {execResult.source && (
                      <span className="artifact-console-tag source-tag">
                        {execResult.source}
                      </span>
                    )}
                  </div>
                  <button 
                    className="artifact-console-close" 
                    onClick={() => setExecResult(null)}
                    title={t('common.close', 'Fechar')}
                  >
                    <X size={12} />
                  </button>
                </div>
                <div className="artifact-console-body">
                  {execResult.compile_output && (
                    <div className="artifact-console-section compile">
                      <div className="section-label">Compile Output:</div>
                      <pre className="artifact-console-compile">{execResult.compile_output}</pre>
                    </div>
                  )}
                  {execResult.stdout && (
                    <div className="artifact-console-section stdout">
                      <pre className="artifact-console-stdout">{execResult.stdout}</pre>
                    </div>
                  )}
                  {execResult.stderr && (
                    <div className="artifact-console-section stderr">
                      <div className="section-label">Error Output:</div>
                      <pre className="artifact-console-stderr">{execResult.stderr}</pre>
                    </div>
                  )}
                  {execResult.error && (
                    <div className="artifact-console-section stderr">
                      <pre className="artifact-console-stderr">{execResult.error}</pre>
                    </div>
                  )}
                  {!execResult.stdout && !execResult.stderr && !execResult.compile_output && !execResult.error && (
                    <div className="artifact-console-empty">{t('artifacts.noOutput', '(Sem saída gerada)')}</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Fallback de segurança universal */}
        {!['html', 'svg', 'markdown', 'jsx', 'diagram', 'code'].includes(normalizedType) && (
          <div className="artifact-markdown-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {cleanContent}
            </ReactMarkdown>
          </div>
        )}
      </div>

      {/* Barra de Edição Inline */}
      <div className={`artifact-edit-bar${isStreaming ? ' artifact-edit-bar--disabled' : ''}`}>
        <Pencil size={14} className="artifact-edit-icon" />
        <textarea
          ref={editInputRef}
          className="artifact-edit-input"
          placeholder={isStreaming ? t('artifacts.waitingResponse', 'Aguardando...') : t('artifacts.editPlaceholder', 'Descreva o que deseja alterar...')}
          value={editPrompt}
          onChange={(e) => setEditPrompt(e.target.value)}
          onKeyDown={handleEditKeyDown}
          disabled={isStreaming}
          rows={1}
        />
        <button
          className="artifact-edit-send"
          onClick={handleEdit}
          disabled={isStreaming || !editPrompt.trim()}
          title={t('artifacts.applyEdit', 'Aplicar')}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  )
}
