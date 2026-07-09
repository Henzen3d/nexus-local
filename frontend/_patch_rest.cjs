const fs = require('fs')
const path = require('path')
const root = 'J:/Arquivos Osmar/Multi+/frontend/src/components'

function patch(file, transforms) {
  const p = path.join(root, file)
  let s = fs.readFileSync(p, 'utf8')
  const before = s
  for (const [from, to] of transforms) {
    if (typeof from === 'string') {
      if (!s.includes(from)) {
        console.warn(`[${file}] MISSING:`, from.slice(0, 80).replace(/\n/g, '\\n'))
        continue
      }
      s = s.split(from).join(to)
    } else {
      s = s.replace(from, to)
    }
  }
  if (s !== before) {
    fs.writeFileSync(p, s)
    console.log('patched', file)
  } else {
    console.log('no change', file)
  }
}

// ── ArtifactPanel ──────────────────────────────────────────────────────────
{
  const p = path.join(root, 'ArtifactPanel.tsx')
  let s = fs.readFileSync(p, 'utf8')
  if (!s.includes('react-i18next')) {
    s = s.replace(
      "import { useState, useRef, useEffect } from 'react'\n",
      "import { useState, useRef, useEffect } from 'react'\nimport { useTranslation } from 'react-i18next'\n"
    )
  }
  s = s.replace(
    'export function ArtifactPanel() {\n  const { activeArtifact, artifactHistory, setArtifactPanelOpen, navigateVersion, isStreaming } = useStore()',
    `export function ArtifactPanel() {
  const { t } = useTranslation()
  const { activeArtifact, artifactHistory, setArtifactPanelOpen, navigateVersion, isStreaming } = useStore()`
  )
  s = s.replace(
    `  const getFriendlyFormatName = (type: string) => {
    switch (type) {
      case 'html': return 'HTML'
      case 'markdown': return 'Markdown'
      case 'svg': return 'SVG'
      case 'jsx': return 'React'
      default: return 'Código'
    }
  }`,
    `  const getFriendlyFormatName = (type: string) => {
    switch (type) {
      case 'html': return 'HTML'
      case 'markdown': return t('artifacts.markdownLabel')
      case 'svg': return 'SVG'
      case 'jsx': return 'React'
      default: return t('artifacts.codeLabel')
    }
  }`
  )
  const titleMap = [
    ['title="Ver prévia"', "title={t('artifacts.preview')}"],
    ['title="Ver código"', "title={t('artifacts.code')}"],
    ['title="Versão anterior"', "title={t('artifacts.prevVersion')}"],
    ['title="Próxima versão"', "title={t('artifacts.nextVersion')}"],
    ['title={isRunningCode ? "Parar Execução" : "Executar Código"}', "title={isRunningCode ? t('artifacts.stopRun') : t('artifacts.runCode')}"],
    ['title="Copiar Conteúdo"', "title={t('artifacts.copyContent')}"],
    ['title="Baixar Arquivo"', "title={t('artifacts.downloadFile')}"],
    ['title="Abrir em Nova Aba"', "title={t('artifacts.openNewTab')}"],
    ['title="Fechar Painel"', "title={t('artifacts.closePanel')}"],
    ["title=\"Code Execution Console\"", "title={t('artifacts.console')}"],
    ["placeholder={isStreaming ? 'Aguardando resposta...' : 'Descreva a modificação...'}", "placeholder={isStreaming ? t('artifacts.waitingResponse') : t('artifacts.editPlaceholder')}"],
    ['title="Aplicar modificação (Enter)"', "title={t('artifacts.applyEdit')}"],
  ]
  for (const [from, to] of titleMap) {
    if (!s.includes(from)) console.warn('ArtifactPanel missing', from)
    else s = s.split(from).join(to)
  }
  fs.writeFileSync(p, s)
  console.log('patched ArtifactPanel')
}

// ── CachePanel ─────────────────────────────────────────────────────────────
{
  const p = path.join(root, 'CachePanel.tsx')
  let s = fs.readFileSync(p, 'utf8')
  if (!s.includes('react-i18next')) {
    s = s.replace(
      "import { useEffect, useState, useCallback } from 'react'\n",
      "import { useEffect, useState, useCallback } from 'react'\nimport { useTranslation } from 'react-i18next'\n"
    )
  }
  s = s.replace(
    'export function CachePanel() {\n  const [stats, setStats]',
    'export function CachePanel() {\n  const { t, i18n } = useTranslation()\n  const [stats, setStats]'
  )
  s = s.replace(
    `        <RefreshCw size={20} className="spin" />
        Carregando estatísticas...
      </div>`,
    `        <RefreshCw size={20} className="spin" />
        {t('tools.loadingStats')}
      </div>`
  )
  s = s.replace('<span className="stat-label">Total de hits</span>', '<span className="stat-label">{t(\'tools.totalHits\')}</span>')
  s = s.replace('<span className="stat-label">Tokens economizados (est.)</span>', '<span className="stat-label">{t(\'tools.tokensSaved\')}</span>')
  s = s.replace(
    '<span className="stat-label">Hits exatos · {stats.exact.entries} entradas</span>',
    '<span className="stat-label">{t(\'tools.exactHits\', { count: stats.exact.entries })}</span>'
  )
  s = s.replace(
    '<span className="stat-label">Hits semânticos · {stats.semantic.entries} entradas</span>',
    '<span className="stat-label">{t(\'tools.semanticHits\', { count: stats.semantic.entries })}</span>'
  )
  s = s.replace(
    `? <><CheckCircle2 size={14} /> Cache semântico ativo — paraphrase-multilingual-MiniLM-L12-v2</>
            : <><AlertCircle size={14} /> {stats.semantic.embedder_error || 'fastembed não instalado'}
                <code>pip install fastembed</code>
              </>`,
    `? <><CheckCircle2 size={14} /> {t('tools.semanticActive')}</>
            : <><AlertCircle size={14} /> {stats.semantic.embedder_error || t('tools.embedderMissing')}
                <code>pip install fastembed</code>
              </>`
  )
  s = s.replace('<h3>Configurações</h3>', '<h3>{t(\'settings.title\')}</h3>')
  s = s.replace('label="Cache global"\n            desc="Ativa ou desativa todo o sistema de cache"', 'label={t(\'tools.cacheGlobal\')}\n            desc={t(\'tools.cacheGlobalDesc\')}')
  s = s.replace('label="Cache exato"\n            desc="SHA-256 das mensagens — hit instantâneo"', 'label={t(\'tools.cacheExact\')}\n            desc={t(\'tools.cacheExactDesc\')}')
  s = s.replace('label="Cache semântico"\n            desc="Embedding + cosseno — captura variações de prompt"', 'label={t(\'tools.cacheSemantic\')}\n            desc={t(\'tools.cacheSemanticDesc\')}')
  s = s.replace('label="Threshold de similaridade"\n            desc="Mínimo de similaridade para um hit semântico (0.80–0.99)"', 'label={t(\'tools.similarityThreshold\')}\n            desc={t(\'tools.similarityDesc\')}')
  s = s.replace('label="TTL do cache exato"\n            desc="Horas antes de uma entrada exata expirar"', 'label={t(\'tools.ttlExact\')}\n            desc={t(\'tools.ttlExactDesc\')}')
  s = s.replace('label="TTL do cache semântico"\n            desc="Horas antes de uma entrada semântica expirar"', 'label={t(\'tools.ttlSemantic\')}\n            desc={t(\'tools.ttlSemanticDesc\')}')
  s = s.replace('<h3>Gerenciar</h3>', '<h3>{t(\'tools.manage\')}</h3>')
  s = s.replace(`            <Clock size={14} />
            Limpar expirados`, `            <Clock size={14} />
            {t('tools.clearExpired')}`)
  s = s.replace("if (confirm('Apagar TODO o cache?')) handleClear(false)", "if (confirm(t('tools.clearAllCache'))) handleClear(false)")
  s = s.replace(`            <Trash2 size={14} />
            Limpar tudo`, `            <Trash2 size={14} />
            {t('tools.clearAll')}`)
  s = s.replace(`            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            Atualizar`, `            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            {t('tools.refresh')}`)
  s = s.replace('<h3>Entradas</h3>', '<h3>{t(\'tools.entries\')}</h3>')
  s = s.replace('<Zap size={12} /> Exato ({stats.exact.entries})', '<Zap size={12} /> {t(\'tools.exactTab\', { count: stats.exact.entries })}')
  s = s.replace('<Sparkles size={12} /> Semântico ({stats.semantic.entries})', '<Sparkles size={12} /> {t(\'tools.semanticTab\', { count: stats.semantic.entries })}')
  s = s.replace('<p>Nenhuma entrada ainda</p>', '<p>{t(\'tools.noEntries\')}</p>')
  s = s.replace('<span>{e.hits} hits</span>', '<span>{t(\'tools.hitsCount\', { count: e.hits })}</span>')
  s = s.replace('<span>~{fmtTokens(e.token_est)} tokens</span>', '<span>{t(\'tools.tokensEst\', { count: fmtTokens(e.token_est) })}</span>')
  s = s.replace('title="Remover entrada"', "title={t('tools.removeEntry')}")
  s = s.replace(
    "return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })",
    "return d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit' })"
  )
  // formatDate needs access to i18n - use undefined for locale which uses browser/default; better use i18n but formatDate is outside. Keep undefined.
  fs.writeFileSync(p, s)
  console.log('patched CachePanel')
}

// ── EnhancerSettings ───────────────────────────────────────────────────────
{
  const p = path.join(root, 'EnhancerSettings.tsx')
  let s = fs.readFileSync(p, 'utf8')
  if (!s.includes('react-i18next')) {
    s = s.replace(
      "import { useEffect, useState } from 'react'\n",
      "import { useEffect, useState } from 'react'\nimport { useTranslation } from 'react-i18next'\n"
    )
  }
  s = s.replace(
    'export function EnhancerSettings() {\n  const [config, setConfig]',
    'export function EnhancerSettings() {\n  const { t } = useTranslation()\n  const [config, setConfig]'
  )
  s = s.replace('<h3>Melhorador de Prompt</h3>', '<h3>{t(\'settings.enhancer\')}</h3>')
  s = s.replace(
    '<p>Configure o modelo que vai otimizar seus prompts antes do envio.</p>',
    '<p>{t(\'tools.enhancerDesc\')}</p>'
  )
  s = s.replace('<label>Provedor</label>', '<label>{t(\'tools.provider\')}</label>')
  s = s.replace('<option value="">Selecione um provedor...</option>', '<option value="">{t(\'tools.selectProviderOption\')}</option>')
  s = s.replace('<label>Modelo</label>', '<label>{t(\'tools.model\')}</label>')
  s = s.replace(
    `          <option value="">
            {!config.enhancer_provider_id
              ? 'Selecione um provedor primeiro...'
              : 'Selecione um modelo...'}
          </option>`,
    `          <option value="">
            {!config.enhancer_provider_id
              ? t('tools.selectProviderFirst')
              : t('tools.selectModel')}
          </option>`
  )
  s = s.replace('<label>System Prompt do Agente</label>', '<label>{t(\'tools.agentSystemPrompt\')}</label>')
  s = s.replace(
    'placeholder="Instruções de sistema para o modelo de melhoria..."',
    "placeholder={t('tools.enhancerPlaceholder')}"
  )
  s = s.replace('<span>Ativar botão ✦ no chat</span>', '<span>{t(\'tools.enableChatButton\')}</span>')
  s = s.replace(
    '<small>Quando desativado, o botão desaparece da interface.</small>',
    '<small>{t(\'tools.enableChatButtonDesc\')}</small>'
  )
  s = s.replace(
    "{config.enhancer_enabled ? 'Ativo' : 'Inativo'}",
    "{config.enhancer_enabled ? t('common.active') : t('common.inactive')}"
  )
  s = s.replace(
    "{saved ? 'Salvo!' : 'Salvar Configuração'}",
    "{saved ? t('common.saved') : t('tools.saveConfig')}"
  )
  fs.writeFileSync(p, s)
  console.log('patched EnhancerSettings')
}

// ── FusionSettings ─────────────────────────────────────────────────────────
{
  const p = path.join(root, 'FusionSettings.tsx')
  let s = fs.readFileSync(p, 'utf8')
  if (!s.includes('react-i18next')) {
    s = s.replace(
      "import { useEffect, useState } from 'react'\n",
      "import { useEffect, useState } from 'react'\nimport { useTranslation } from 'react-i18next'\nimport i18n from '../i18n'\n"
    )
  }
  // Replace DEFAULT_JUDGE_PROMPT usage with i18n
  s = s.replace(
    `const DEFAULT_JUDGE_PROMPT =
  "Você é o Agente Juiz e Consolidador do NexusLocal.\\n\\n" +
  "Abaixo estão as respostas de diferentes modelos LLM para a pergunta do usuário. " +
  "Analise cada resposta, extraia os pontos fortes de cada uma, neutralize erros " +
  "factuais ou alucinações e monte a resposta ideal: unificada, clara e abrangente.\\n\\n" +
  "Responda diretamente ao usuário, sem mencionar que está consolidando respostas. " +
  "Retorne apenas a resposta final em Markdown."`,
    `const getDefaultJudgePrompt = () => i18n.t('tools.fusionDefaultPrompt')`
  )
  s = s.replace(
    'export function FusionSettings() {\n  const [providers, setProviders]',
    'export function FusionSettings() {\n  const { t } = useTranslation()\n  const [providers, setProviders]'
  )
  s = s.replace(
    'const [judgePrompt, setJudgePrompt] = useState(DEFAULT_JUDGE_PROMPT)',
    'const [judgePrompt, setJudgePrompt] = useState(getDefaultJudgePrompt)'
  )
  s = s.replace(
    'setJudgePrompt(cfg.judge_system_prompt || DEFAULT_JUDGE_PROMPT)',
    'setJudgePrompt(cfg.judge_system_prompt || getDefaultJudgePrompt())'
  )
  s = s.replace('<h3>Modo Fusion</h3>', '<h3>{t(\'settings.fusionMode\')}</h3>')
  s = s.replace(
    '<p>Execute múltiplos modelos em paralelo e consolide as respostas com um modelo Juiz.</p>',
    '<p>{t(\'tools.fusionDesc\')}</p>'
  )
  s = s.replace(
    '<h4 className="fusion-section-title">Modelos Paralelos</h4>',
    '<h4 className="fusion-section-title">{t(\'tools.parallelModelsSection\')}</h4>'
  )
  s = s.replace(
    `        <p className="fusion-section-desc">
          Cada linha usa um provedor diferente. Um modelo por provedor para evitar rate limits.
        </p>`,
    `        <p className="fusion-section-desc">
          {t('tools.parallelModelsDesc')}
        </p>`
  )
  s = s.replace('title="Remover"', "title={t('common.remove')}")
  s = s.replace('<option value="">Provedor...</option>', '<option value="">{t(\'tools.providerEllipsis\')}</option>')
  s = s.replace(
    '{blockedIds.includes(p.id) ? `${p.name} (em uso)` : p.name}',
    "{blockedIds.includes(p.id) ? t('tools.inUse', { name: p.name }) : p.name}"
  )
  s = s.replace(
    `{!line.provider_id ? 'Selecione provedor...' : 'Modelo...'}`,
    `{!line.provider_id ? t('tools.selectProvider') : t('tools.modelEllipsis')}`
  )
  s = s.replace(
    `          <Plus size={14} />
          Adicionar Modelo`,
    `          <Plus size={14} />
          {t('tools.addModel')}`
  )
  s = s.replace(
    '<h4 className="fusion-section-title">Modelo Juiz</h4>',
    '<h4 className="fusion-section-title">{t(\'tools.judgeModel\')}</h4>'
  )
  s = s.replace(
    `        <p className="fusion-section-desc">
          O Juiz analisa todas as respostas e gera um veredito consolidado. Pode usar qualquer provedor, inclusive repetidos.
        </p>`,
    `        <p className="fusion-section-desc">
          {t('tools.judgeModelDesc')}
        </p>`
  )
  s = s.replaceAll('<label>Provedor</label>', '<label>{t(\'tools.provider\')}</label>')
  s = s.replaceAll('<option value="">Selecione um provedor...</option>', '<option value="">{t(\'tools.selectProviderOption\')}</option>')
  s = s.replaceAll('<label>Modelo</label>', '<label>{t(\'tools.model\')}</label>')
  s = s.replace(
    `{!judgeProviderId ? 'Selecione provedor...' : 'Modelo...'}`,
    `{!judgeProviderId ? t('tools.selectProvider') : t('tools.modelEllipsis')}`
  )
  s = s.replace('<label>System Prompt do Juiz</label>', '<label>{t(\'tools.judgeSystemPrompt\')}</label>')
  s = s.replace(
    'placeholder="Instruções de consolidação para o modelo Juiz..."',
    "placeholder={t('tools.fusionJudgePlaceholder')}"
  )
  s = s.replace('<span>Verificação factual (busca web)</span>', '<span>{t(\'tools.factualCheck\')}</span>')
  s = s.replace(
    '<small>O Juiz verifica fatos das respostas na web antes de consolidar. Adiciona ~2-5s de latência.</small>',
    '<small>{t(\'tools.factualCheckDesc\')}</small>'
  )
  s = s.replaceAll(
    "{groundingEnabled ? 'Ativo' : 'Inativo'}",
    "{groundingEnabled ? t('common.active') : t('common.inactive')}"
  )
  s = s.replace('<span>Ativar Modo Fusion</span>', '<span>{t(\'tools.enableFusion\')}</span>')
  s = s.replace(
    '<small>Quando ativo, o toggle 🧬 aparece no chat.</small>',
    '<small>{t(\'tools.enableFusionDesc\')}</small>'
  )
  s = s.replaceAll(
    "{enabled ? 'Ativo' : 'Inativo'}",
    "{enabled ? t('common.active') : t('common.inactive')}"
  )
  s = s.replace(
    "{saved ? 'Salvo!' : 'Salvar Configuração'}",
    "{saved ? t('common.saved') : t('tools.saveConfig')}"
  )
  fs.writeFileSync(p, s)
  console.log('patched FusionSettings')
}

console.log('rest batch 1 done')
