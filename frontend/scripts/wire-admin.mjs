import fs from 'fs'

const path = 'src/components/AdminPanel.tsx'
let s = fs.readFileSync(path, 'utf8')

// imports
if (!s.includes('useTranslation')) {
  s = s.replace(
    "import { api } from '../api/client'",
    "import { useTranslation } from 'react-i18next'\nimport { api } from '../api/client'\nimport { SUPPORTED_LOCALES } from '../i18n'"
  )
  s = s.replace(
    "import { RankingsView } from './RankingsView'\n",
    "import { RankingsView } from './RankingsView'\nimport { Languages } from 'lucide-react'\n"
  )
  // Languages might already be available from lucide - check if we need separate import
  // Actually Languages not in lucide import line - add to existing lucide import
  s = s.replace(
    'Award\n} from \'lucide-react\'',
    'Award, Languages\n} from \'lucide-react\''
  )
  // remove duplicate Languages import if we added it separately
  s = s.replace("import { Languages } from 'lucide-react'\n", '')
}

// Mobile: add useTranslation + locale/setLocale
if (!s.includes("const { t, i18n } = useTranslation()")) {
  s = s.replace(
    `function AdminPanelMobile() {
  const {
    setView, loadModels, user, theme, setTheme, chatFont, setChatFont,
    hapticFeedback, setHapticFeedback, displayName, fullName, occupation,
    customInstructions, setProfile, logout
  } = useStore()

  // Stack navigation state
  const [screenStack, setScreenStack] = useState<string[]>(['list'])
  const [activeBottomSheet, setActiveBottomSheet] = useState<'theme' | 'font' | null>(null)`,
    `function AdminPanelMobile() {
  const { t, i18n } = useTranslation()
  const {
    setView, loadModels, user, theme, setTheme, chatFont, setChatFont,
    hapticFeedback, setHapticFeedback, displayName, fullName, occupation,
    customInstructions, setProfile, logout, locale, setLocale
  } = useStore()

  // Stack navigation state
  const [screenStack, setScreenStack] = useState<string[]>(['list'])
  const [activeBottomSheet, setActiveBottomSheet] = useState<'theme' | 'font' | 'language' | null>(null)`
  )
}

// Desktop store + t
if (!s.includes('locale, setLocale') || s.split('locale, setLocale').length < 2) {
  s = s.replace(
    `const { setView, loadModels, user, theme, setTheme, chatFont, setChatFont, modelSortMode, setModelSortMode, displayName, fullName, occupation, customInstructions, setProfile } = useStore()`,
    `const { t, i18n } = useTranslation()
  const { setView, loadModels, user, theme, setTheme, chatFont, setChatFont, modelSortMode, setModelSortMode, displayName, fullName, occupation, customInstructions, setProfile, locale, setLocale } = useStore()`
  )
}

const handleLocaleChange = `
  const handleLocaleChange = (code: string) => {
    setLocale(code)
    i18n.changeLanguage(code)
  }
`

// insert handleLocaleChange after mobile triggerHaptic if exists, else after state
if (!s.includes('handleLocaleChange')) {
  // add after mobile useStore block close - find first triggerHaptic or similar
  s = s.replace(
    `const [activeBottomSheet, setActiveBottomSheet] = useState<'theme' | 'font' | 'language' | null>(null)`,
    `const [activeBottomSheet, setActiveBottomSheet] = useState<'theme' | 'font' | 'language' | null>(null)
  const handleLocaleChange = (code: string) => {
    setLocale(code)
    i18n.changeLanguage(code)
  }`
  )
  // desktop also needs it - add near desktop start after useStore
  s = s.replace(
    `const { setView, loadModels, user, theme, setTheme, chatFont, setChatFont, modelSortMode, setModelSortMode, displayName, fullName, occupation, customInstructions, setProfile, locale, setLocale } = useStore()`,
    `const { setView, loadModels, user, theme, setTheme, chatFont, setChatFont, modelSortMode, setModelSortMode, displayName, fullName, occupation, customInstructions, setProfile, locale, setLocale } = useStore()
  const handleLocaleChange = (code: string) => {
    setLocale(code)
    i18n.changeLanguage(code)
  }`
  )
}

// Simple string replacements (global)
const simple = [
  ['title="Voltar"', 'title={t("common.back")}'],
  ['aria-label="Voltar para tela anterior"', 'aria-label={t("settings.backToPrevious")}'],
  ['title="Fechar Configurações"', 'title={t("settings.closeSettings")}'],
  ['aria-label="Fechar modal de configurações"', 'aria-label={t("settings.closeModal")}'],
  ['title="Informações"', 'title={t("settings.information")}'],
  ['title="Info"', 'title={t("common.info")}'],
  ['title="Fechar"', 'title={t("common.close")}'],
  ['placeholder="Procurar..."', 'placeholder={t("settings.searchPlaceholder")}'],
  ['placeholder="Buscar modelo..."', 'placeholder={t("settings.searchModel")}'],
  ['placeholder="ex.: manter explicações breves e diretas"', 'placeholder={t("settings.instructionsPlaceholder")}'],
  ['placeholder="Cole sua chave aqui"', 'placeholder={t("settings.pasteKey")}'],
  ['placeholder="Cole o ID da conta Cloudflare aqui"', 'placeholder={t("settings.cloudflareId")}'],
  [">Configurações</span>", '>{t("settings.title")}</span>'],
  [">Configurações</div>", '>{t("settings.title")}</div>'],
  ['>Aparência & Preferências</div>', '>{t("settings.appearancePrefs")}</div>'],
  ['>Modo de Cor</span>', '>{t("settings.colorMode")}</span>'],
  ['>Estilo de Fonte</span>', '>{t("settings.fontStyle")}</span>'],
  ['>Feedback Háptico</span>', '>{t("settings.haptic")}</span>'],
  ['>Vibrar levemente ao navegar e interagir com o app</span>', '>{t("settings.hapticDesc")}</span>'],
  ['>Modelos & Agentes</div>', '>{t("settings.modelsAgents")}</div>'],
  ['>Capacidades</span>', '>{t("settings.capabilities")}</span>'],
  ['>Provedores e modelos de IA locais/nuvem</span>', '>{t("settings.capabilitiesSub")}</span>'],
  ['>Rankings de Modelos</span>', '>{t("settings.modelRankings")}</span>'],
  ['>Classificação geral de modelos e score</span>', '>{t("settings.rankingsSub")}</span>'],
  ['>Conectores (Ferramentas)</span>', '>{t("settings.connectors")}</span>'],
  ['>Melhorador de prompt, Modo Fusion, Busca web</span>', '>{t("settings.connectorsSub")}</span>'],
  ['>Gerenciar Usuários</span>', '>{t("settings.manageUsers")}</span>'],
  ['>Excluir e controlar contas de usuários</span>', '>{t("settings.manageUsersSub")}</span>'],
  ['>Sistema & Segurança</div>', '>{t("settings.systemSecurity")}</div>'],
  ['>Visualizar e atualizar Perfil</p>', '>{t("settings.viewUpdateProfile")}</p>'],
  ["Header title=\"Editar Perfil\"", 'Header title={t("settings.editProfile")}'],
  ["Header title=\"Capacidades\"", 'Header title={t("settings.capabilities")}'],
  ["Header title=\"Cache Inteligente\"", 'Header title={t("settings.smartCache")}'],
  ["Header title=\"Conectores\"", 'Header title={t("settings.connectorsShort")}'],
  ["Header title=\"Melhorador de Prompt\"", 'Header title={t("settings.enhancer")}'],
  ["Header title=\"Modo Fusion\"", 'Header title={t("settings.fusionMode")}'],
  ["Header title=\"Vision Relay\"", 'Header title={t("settings.visionRelay")}'],
  ["Header title=\"Busca Web\"", 'Header title={t("settings.webSearch")}'],
  ["Header title=\"Free Registry\"", 'Header title={t("settings.freeRegistry")}'],
  ["Header title=\"Calibração de Score\"", 'Header title={t("settings.scoreCalibration")}'],
  ["Header title=\"Rankings de Modelos\"", 'Header title={t("settings.modelRankings")}'],
  ["Header title=\"Usuários\"", 'Header title={t("settings.users")}'],
  ["Header title=\"Cobrança\"", 'Header title={t("settings.billing")}'],
  ["Header title=\"Permissões\"", 'Header title={t("settings.permissions")}'],
  ["Header title=\"Privacidade & Segurança\"", 'Header title={t("settings.privacy")}'],
  ["Header title=\"Links Compartilhados\"", 'Header title={t("settings.sharedLinks")}'],
  ["Header title=\"Configurações de Voz\"", 'Header title={t("settings.voiceSettings")}'],
  [">Salvar Preferências</button>", '>{t("settings.savePreferences")}</button>'],
  [">Perfil Atualizado!</button>", '>{t("settings.profileUpdated")}</button>'],
  ["profileSaved ? 'Perfil Atualizado!' : 'Salvar Preferências'", "profileSaved ? t('settings.profileUpdated') : t('settings.savePreferences')"],
  ["syncing[prov.id] ? 'Sincronizando...' : 'Sincronizar Modelos'", "syncing[prov.id] ? t('common.syncing') : t('settings.syncModels')"],
  ["saved[prov.id] ? 'Salvo!' : 'Salvar'", "saved[prov.id] ? t('common.saved') : t('common.save')"],
  [">Oferece Modelos Free</span>", '>{t("settings.offersFree")}</span>'],
  [">Apenas Modelos Pagos</span>", '>{t("settings.paidOnly")}</span>'],
  [">Chave de API</label>", '>{t("settings.apiKey")}</label>'],
  [">Modelos Habilitados</label>", '>{t("settings.enabledModels")}</label>'],
  [">Cache Inteligente</span>", '>{t("settings.smartCache")}</span>'],
  [">Otimizações e estatísticas de cache semântico</span>", '>{t("settings.cacheSettingsSub")}</span>'],
  [">Usuários Cadastrados</h4>", '>{t("settings.registeredUsers")}</h4>'],
  [">Carregando usuários...</div>", '>{t("settings.loadingUsers")}</div>'],
  ["setUserError('Erro ao carregar a lista de usuários.')", "setUserError(t('settings.loadUsersError'))"],
  ["u.role === 'admin' ? 'Administrador' : 'Usuário'", "u.role === 'admin' ? t('common.admin') : t('common.user')"],
  [">Excluir Usuário</", '>{t("settings.deleteUser")}</'],
  ['title="Excluir usuário"', 'title={t("settings.deleteUserTitle")}'],
  [">Geral</h2>", '>{t("settings.general")}</h2>'],
  [">Perfil</h3>", '>{t("settings.profile")}</h3>'],
  [">Preferências</h3>", '>{t("settings.preferences")}</h3>'],
  [">Aparência</h4>", '>{t("settings.appearance")}</h4>'],
  [">Escolha o tema de cores da aplicação</p>", '>{t("settings.appearanceDesc")}</p>'],
  [">Dispositivo</button>", '>{t("settings.themeDevice")}</button>'],
  [">Claro</button>", '>{t("settings.themeLight")}</button>'],
  [">Escuro</button>", '>{t("settings.themeDark")}</button>'],
  [">Excluir Conta</button>", '>{t("settings.deleteAccount")}</button>'],
  [">Ações de Conta</h4>", '>{t("settings.accountActions")}</h4>'],
  [">Excluir dados permanentemente da sua conta de usuário.</p>", '>{t("settings.accountActionsDesc")}</p>'],
  [">Nome Completo</label>", '>{t("settings.fullName")}</label>'],
  [">Nome completo</label>", '>{t("settings.fullNameAlt")}</label>'],
  [">Como devemos te chamar?</label>", '>{t("settings.howToCall")}</label>'],
  [">Como o Claude deveria te chamar?</label>", '>{t("settings.howClaudeCall")}</label>'],
  [">Área de Atuação</label>", '>{t("settings.occupation")}</label>'],
  [">O que melhor descreve seu trabalho?</label>", '>{t("settings.occupationDesc")}</label>'],
  [">Instruções personalizadas</label>", '>{t("settings.customInstructions")}</label>'],
  [">Instruções para o Claude</label>", '>{t("settings.instructionsForClaude")}</label>'],
  [">Selecionar...</option>", '>{t("common.select")}</option>'],
  [">Desenvolvedor / Engenheiro de Software</option>", '>{t("settings.occupationDev")}</option>'],
  [">Designer de Interface / UX</option>", '>{t("settings.occupationDesigner")}</option>'],
  [">Gerente de Produto / Projeto</option>", '>{t("settings.occupationManager")}</option>'],
  [">Estudante / Acadêmico</option>", '>{t("settings.occupationStudent")}</option>'],
  [">Outro</option>", '>{t("settings.occupationOther")}</option>'],
  [">Iniciais representativas do nome</span>", '>{t("settings.initialsHint")}</span>'],
  [">Iniciais representativas do nome</p>", '>{t("settings.initialsHint")}</p>'],
  [">Avatar</h4>", '>{t("settings.avatar")}</h4>'],
  ['label: \'Geral\'', "label: t('settings.general')"],
  ['label: \'Providers & Modelos\'', "label: t('settings.providersModels')"],
  ['label: \'Rankings de Modelos\'', "label: t('settings.modelRankings')"],
  ['label: \'Uso\'', "label: t('settings.usage')"],
  ['label: \'Cache Inteligente\'', "label: t('settings.smartCache')"],
  ['label: \'Ferramentas\'', "label: t('settings.tools')"],
  ['label: \'Usuários\'', "label: t('settings.users')"],
  ["label: 'Dispositivo'", "label: t('settings.themeDevice')"],
  ["label: 'Claro'", "label: t('settings.themeLight')"],
  ["label: 'Escuro'", "label: t('settings.themeDark')"],
  [">Modo de Cor</span>", '>{t("settings.colorMode")}</span>'], // bottom sheet title uses class
  [">Estilo de Fonte do Chat</span>", '>{t("settings.fontStyleChat")}</span>'],
  ["theme === 'system' ? 'Sistema' : theme === 'light' ? 'Claro' : 'Escuro'", "theme === 'system' ? t('settings.themeSystem') : theme === 'light' ? t('settings.themeLight') : t('settings.themeDark')"],
]

let applied = 0
for (const [a, b] of simple) {
  if (s.includes(a)) {
    s = s.split(a).join(b)
    applied++
  }
}
console.log('simple replacements applied:', applied)

// Language row in mobile appearance section - insert after font row, before haptic
const langRow = `
              <div className="settings-list-item" onClick={() => { setActiveBottomSheet('language'); triggerHaptic() }}>
                <div className="settings-list-item-left">
                  <Languages size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">{t('settings.language')}</span>
                    <span className="settings-list-item-subtitle">
                      {SUPPORTED_LOCALES.find(l => l.code === locale)?.nativeName || locale}
                    </span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>
`
if (!s.includes("setActiveBottomSheet('language')")) {
  s = s.replace(
    `<div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">{t('settings.haptic')}</span>`,
    langRow + `
              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">{t('settings.haptic')}</span>`
  )
  // if haptic wasn't translated yet
  if (!s.includes("setActiveBottomSheet('language')")) {
    s = s.replace(
      `<div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">Feedback Háptico</span>`,
      langRow + `
              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">Feedback Háptico</span>`
    )
  }
}

// Language bottom sheet after font bottom sheet
const langSheet = `
      {activeBottomSheet === 'language' && (
        <div className="bottom-sheet-overlay" onClick={() => setActiveBottomSheet(null)}>
          <div className="bottom-sheet-container" onClick={(e) => e.stopPropagation()}>
            <div className="bottom-sheet-header">
              <span className="bottom-sheet-title">{t('settings.languageTitle')}</span>
              <button
                style={{ padding: '6px', borderRadius: '50%', background: 'var(--surface-soft)' }}
                onClick={() => setActiveBottomSheet(null)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="bottom-sheet-options">
              {SUPPORTED_LOCALES.map((opt) => (
                <div
                  key={opt.code}
                  className={\`bottom-sheet-option \${locale === opt.code ? 'active' : ''}\`}
                  onClick={() => {
                    handleLocaleChange(opt.code)
                    triggerHaptic(15)
                    setActiveBottomSheet(null)
                  }}
                >
                  <div className="bottom-sheet-option-left">
                    <Languages size={16} />
                    <span>{opt.nativeName}</span>
                  </div>
                  {locale === opt.code && <Check size={16} />}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
`

if (!s.includes("activeBottomSheet === 'language'")) {
  // insert before closing of mobile return - after font bottom sheet
  const fontSheetEnd = `      {/* Font Bottom Sheet */}
      {activeBottomSheet === 'font' && (`
  // find end of font sheet - look for pattern after font sheet closes
  // Insert before the last closing of AdminPanelMobile - after theme/font sheets
  s = s.replace(
    `      {/* Font Bottom Sheet */}
      {activeBottomSheet === 'font' && (`,
    langSheet + `
      {/* Font Bottom Sheet */}
      {activeBottomSheet === 'font' && (`
  )
}

// Desktop language selector after appearance section
const desktopLang = `
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--ink)' }}>{t('settings.language')}</h4>
                    <p style={{ fontSize: '12px', color: 'var(--muted)' }}>{t('settings.languageDesc')}</p>
                  </div>
                  <select
                    style={{
                      padding: '6px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--hairline)',
                      background: 'var(--surface-card)',
                      color: 'var(--ink)',
                      outline: 'none',
                      fontSize: '13px',
                      maxWidth: '220px'
                    }}
                    value={locale}
                    onChange={(e) => handleLocaleChange(e.target.value)}
                  >
                    {SUPPORTED_LOCALES.map((l) => (
                      <option key={l.code} value={l.code}>{l.nativeName}</option>
                    ))}
                  </select>
                </div>
`
if (!s.includes("value={locale}") && !s.includes('handleLocaleChange(e.target.value)')) {
  // insert before font section or after appearance theme buttons block ends (before Fonte do chat)
  if (s.includes('Fonte do chat')) {
    s = s.replace(
      /<div style=\{\{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' \}\}>\s*<div>\s*<h4[^>]*>Fonte do chat<\/h4>/,
      desktopLang + `
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--ink)' }}>Fonte do chat</h4>`
    )
  } else if (s.includes("Ordenação de Modelos")) {
    s = s.replace(
      /<div style=\{\{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' \}\}>\s*<div>\s*<h4[^>]*>Ordenação de Modelos<\/h4>/,
      desktopLang + `
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--ink)' }}>Ordenação de Modelos</h4>`
    )
  }
}

// confirm dialogs
s = s.replace(
  /window\.confirm\("Confirmar este modelo como gratuito\? O sistema passar[áa] a trata-lo como livre\."\)/g,
  "window.confirm(t('settings.confirmFreePrompt'))"
)
s = s.replace(
  /alert\('Erro ao confirmar modelo'\)/g,
  "alert(t('settings.confirmModelError'))"
)
s = s.replace(
  /alert\('Não foi possível excluir o usuário\.'\)/g,
  "alert(t('settings.deleteUserFail'))"
)
s = s.replace(
  /window\.confirm\(`Tem certeza que deseja excluir o usuário "\$\{username\}"\? Todos os seus chats e chaves de API serão removidos permanentemente\.`\)/g,
  "window.confirm(t('settings.deleteUserConfirm', { username }))"
)
s = s.replace(
  /window\.confirm\('Tem certeza que deseja excluir sua conta\? Todos os seus chats salvos serão deletados permanentemente\.'\)/g,
  "window.confirm(t('settings.deleteAccountConfirm'))"
)
s = s.replace(
  /window\.confirm\('Tem certeza de que deseja limpar todos os dados em cache do localStorage\? Você será deslogado\.'\)/g,
  "window.confirm(t('settings.clearCacheConfirm'))"
)
s = s.replace(
  /alert\('Parabéns pelo interesse! A versão Pro estará disponível em breve\.'\)/g,
  "alert(t('settings.proInterest'))"
)

// general desc
s = s.replace(
  'Gerencie as informações do seu perfil e preferências de aparência do sistema.',
  "{t('settings.generalDesc')}"
)
// if that put braces wrong inside JSX text - fix
s = s.replace(
  /\{t\('settings\.generalDesc'\)\}/g,
  "{t('settings.generalDesc')}"
)

// instructions hint paragraph
s = s.replace(
  'Essas diretrizes serão levadas em consideração nas conversas locais e interações de agente.',
  "{t('settings.instructionsHint')}"
)

// capabilities desc
s = s.replace(
  'Gerencie seus Provedores de modelos locais e configure suas chaves de API para servidores na nuvem.',
  "{t('settings.capabilitiesDesc')}"
)

// permissions desc
s = s.replace(
  'Gerencie o acesso do NexusLocal às APIs de hardware e notificações do seu navegador e sistema móvel.',
  "{t('settings.permissionsDesc')}"
)

// activated counts
s = s.replace(
  /\{activeModelsCount\} ativados/g,
  "{t('settings.activatedCount', { count: activeModelsCount })}"
)
s = s.replace(
  /\{toolsCount\} ativos/g,
  "{t('settings.activeToolsCount', { count: toolsCount })}"
)

fs.writeFileSync(path, s)
console.log('AdminPanel wired, length', s.length)
