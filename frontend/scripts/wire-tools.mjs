import fs from 'fs'

function ensureImport(s, after) {
  if (s.includes("from 'react-i18next'")) return s
  if (s.includes('from "react-i18next"')) return s
  return s.replace(after, `import { useTranslation } from 'react-i18next'\n${after}`)
}

function ensureHook(s, fnSig) {
  if (s.includes('const { t } = useTranslation()') || s.includes('const { t, i18n }')) return s
  return s.replace(fnSig, `${fnSig}\n  const { t } = useTranslation()`)
}

const jobs = [
  {
    file: 'src/components/EnhancerSettings.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function EnhancerSettings() {',
    pairs: [
      ["placeholder=\"Instruções de sistema para o modelo de melhoria...\"", "placeholder={t('tools.enhancerPlaceholder')}"],
      ["{saved ? 'Salvo!' : 'Salvar Configuração'}", "{saved ? t('common.saved') : t('tools.saveConfig')}"],
      [">Selecione um modelo...</option>", ">{t('tools.selectModel')}</option>"],
      [">Selecione um provedor primeiro...</option>", ">{t('tools.selectProviderFirst')}</option>"],
    ],
  },
  {
    file: 'src/components/FreeRegistrySettings.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function FreeRegistrySettings() {',
    pairs: [
      ["setSyncResult('Registry já estava atualizado.')", "setSyncResult(t('tools.registryUpToDate'))"],
      ["{syncing ? 'Sincronizando...' : 'Forçar Sincronização Agora'}", "{syncing ? t('common.syncing') : t('tools.forceSync')}"],
      ["{saved ? 'Salvo!' : 'Salvar Configurações'}", "{saved ? t('common.saved') : t('tools.saveSettings')}"],
      ["'Erro ao sincronizar. Verifique os logs.'", "t('tools.syncError')"],
      [">Nunca<", ">{t('common.never')}<"],
    ],
  },
  {
    file: 'src/components/FusionSettings.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function FusionSettings() {',
    pairs: [
      ["placeholder=\"Instruções de consolidação para o modelo Juiz...\"", "placeholder={t('tools.fusionJudgePlaceholder')}"],
      ["{saved ? 'Salvo!' : 'Salvar Configuração'}", "{saved ? t('common.saved') : t('tools.saveConfig')}"],
      ["title=\"Remover\"", "title={t('common.remove')}"],
      [">Selecione provedor...</option>", ">{t('tools.selectProvider')}</option>"],
      [">Modelo...</option>", ">{t('tools.modelEllipsis')}</option>"],
    ],
  },
  {
    file: 'src/components/VisionRelaySettings.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function VisionRelaySettings() {',
    pairs: [
      ["placeholder=\"Instruções para guiar a descrição objetiva da imagem...\"", "placeholder={t('tools.visionPlaceholder')}"],
      ["{saved ? 'Salvo!' : 'Salvar Configuração'}", "{saved ? t('common.saved') : t('tools.saveConfig')}"],
    ],
  },
  {
    file: 'src/components/WebSearchSettings.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function WebSearchSettings() {',
    pairs: [
      ["{saved ? 'Salvo!' : 'Salvar Configuração'}", "{saved ? t('common.saved') : t('tools.saveConfig')}"],
      [">Automática</option>", ">{t('tools.webSearchAuto')}</option>"],
      [">Manual</option>", ">{t('tools.webSearchManual')}</option>"],
      [">Alta (Threshold: 0.25)</option>", ">{t('tools.sensitivityHigh')}</option>"],
      [">Média (Threshold: 0.40)</option>", ">{t('tools.sensitivityMed')}</option>"],
      [">Baixa (Threshold: 0.60)</option>", ">{t('tools.sensitivityLow')}</option>"],
    ],
  },
  {
    file: 'src/components/CachePanel.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function CachePanel() {',
    pairs: [
      ['label="Cache global"', "label={t('tools.cacheGlobal')}"],
      ['label="Cache exato"', "label={t('tools.cacheExact')}"],
      ['label="Cache semântico"', "label={t('tools.cacheSemantic')}"],
      ['label="Threshold de similaridade"', "label={t('tools.similarityThreshold')}"],
      ['label="TTL do cache semântico"', "label={t('tools.ttlSemantic')}"],
      ['title="Remover entrada"', "title={t('tools.removeEntry')}"],
      ["'fastembed não instalado'", "t('tools.embedderMissing')"],
      ["'Apagar TODO o cache?'", "t('tools.clearAllCache')"],
    ],
  },
  {
    file: 'src/components/FamilySettings.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function FamilySettings() {',
    pairs: [
      ['title="Excluir Família"', "title={t('tools.familyDelete')}"],
      ['title="Remover"', "title={t('common.remove')}"],
      ["alert(\"Erro ao criar família. Verifique se o ID já existe.\")", "alert(t('tools.familyCreateError'))"],
      ["alert(\"Erro ao adicionar membro.\")", "alert(t('tools.familyAddMemberError'))"],
      ["alert(\"Erro ao aplicar sugestão\")", "alert(t('tools.familySuggestError'))"],
      ['placeholder="Modelos focados em raciocínio avançado..."', "placeholder={t('tools.familyDescPlaceholder')}"],
      ['title="Ordem de fallback (1 = principal)"', "title={t('tools.familyFallbackOrder')}"],
    ],
  },
  {
    file: 'src/components/RankingWeightsSettings.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function RankingWeightsSettings() {',
    pairs: [
      ["alert(\"Erro ao salvar pesos do ranking.\")", "alert(t('tools.rankingSaveError'))"],
      ["{saved ? 'Pesos Calibrados!' : 'Aplicar Calibração'}", "{saved ? t('tools.weightsCalibrated') : t('tools.applyCalibration')}"],
    ],
  },
  {
    file: 'src/components/RankingsView.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function RankingsView() {',
    pairs: [
      ["placeholder=\"Filtrar modelos...\"", "placeholder={t('tools.filterModels')}"],
      ["{savingWeights ? 'Salvando...' : weightsSaved ? 'Pesos Calibrados!' : 'Aplicar Calibração'}", "{savingWeights ? t('common.saving') : weightsSaved ? t('tools.weightsCalibrated') : t('tools.applyCalibration')}"],
    ],
  },
  {
    file: 'src/components/UsageDashboard.tsx',
    after: "import { api } from '../api/client'",
    fn: 'export function UsageDashboard() {',
    pairs: [
      [">Degradado<", ">{t('admin.degraded')}<"],
      [">Esgotado (429)<", ">{t('admin.exhausted')}<"],
      [">Rate Limit (429)<", ">{t('admin.rateLimit')}<"],
      [">Requisições<", ">{t('admin.requests')}<"],
    ],
  },
  {
    file: 'src/components/ArtifactPanel.tsx',
    after: "import { useStore } from '../store/useStore'",
    fn: 'export function ArtifactPanel() {',
    pairs: [
      ['title="Ver prévia"', "title={t('artifacts.preview')}"],
      ['title="Ver código"', "title={t('artifacts.code')}"],
      ['title="Versão anterior"', "title={t('artifacts.prevVersion')}"],
      ['title="Próxima versão"', "title={t('artifacts.nextVersion')}"],
      ['title="Copiar Conteúdo"', "title={t('artifacts.copyContent')}"],
      ['title="Baixar Arquivo"', "title={t('artifacts.downloadFile')}"],
      ['title="Abrir em Nova Aba"', "title={t('artifacts.openNewTab')}"],
      ['title="Fechar Painel"', "title={t('artifacts.closePanel')}"],
      ['title="Aplicar modificação (Enter)"', "title={t('artifacts.applyEdit')}"],
      ["'Aguardando resposta...'", "t('artifacts.waitingResponse')"],
      ["'Descreva a modificação...'", "t('artifacts.editPlaceholder')"],
      ['title={isRunningCode ? "Parar Execução" : "Executar Código"}', "title={isRunningCode ? t('artifacts.stopRun') : t('artifacts.runCode')}"],
    ],
  },
]

for (const job of jobs) {
  if (!fs.existsSync(job.file)) {
    console.log('skip missing', job.file)
    continue
  }
  let s = fs.readFileSync(job.file, 'utf8')
  const before = s
  s = ensureImport(s, job.after)
  // try common export patterns
  if (s.includes(job.fn)) s = ensureHook(s, job.fn)
  else {
    // try alternate
    const m = s.match(/export function \w+\([^)]*\) \{/)
    if (m) s = ensureHook(s, m[0])
  }
  let n = 0
  for (const [a, b] of job.pairs) {
    if (s.includes(a)) {
      s = s.split(a).join(b)
      n++
    }
  }
  if (s !== before) {
    fs.writeFileSync(job.file, s)
    console.log(job.file, 'pairs', n)
  } else {
    console.log(job.file, 'no changes', n)
  }
}
