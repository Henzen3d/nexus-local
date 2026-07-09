import fs from 'fs'

function wireConversations() {
  const path = 'src/components/ConversationsPanel.tsx'
  let s = fs.readFileSync(path, 'utf8')
  if (!s.includes('useTranslation')) {
    s = s.replace(
      "import { useStore } from '../store/useStore'",
      "import { useTranslation } from 'react-i18next'\nimport { useStore } from '../store/useStore'"
    )
    s = s.replace(
      'export function ConversationsPanel() {\n  const {',
      'export function ConversationsPanel() {\n  const { t, i18n } = useTranslation()\n  const {'
    )
  }

  const pairs = [
    ['title="Abrir menu"', 'title={t("common.openMenu")}'],
    ['aria-label="Abrir menu"', 'aria-label={t("common.openMenu")}'],
    ['aria-label="Filtrar conversas"', 'aria-label={t("conversations.filterConversations")}'],
    ['placeholder="Pesquisar conversas"', "placeholder={t('conversations.searchPlaceholder')}"],
    ['>Conversas</h1>', '>{t("conversations.title")}</h1>'],
    ['>Todos</button>', '>{t("conversations.all")}</button>'],
    ['>Favoritos</button>', '>{t("conversations.favorites")}</button>'],
    [
      "title={isSelectMode ? 'Cancelar seleção' : 'Selecionar chats'}",
      "title={isSelectMode ? t('conversations.cancelSelection') : t('conversations.selectChats')}",
    ],
    [
      "aria-label={isSelectMode ? 'Cancelar seleção' : 'Selecionar chats'}",
      "aria-label={isSelectMode ? t('conversations.cancelSelection') : t('conversations.selectChats')}",
    ],
    ['>Alternar Favoritos</span>', '>{t("conversations.toggleFavorites")}</span>'],
    ['>Apagar</span>', '>{t("conversations.delete")}</span>'],
    ['>Nenhuma conversa encontrada</h3>', '>{t("conversations.emptyTitle")}</h3>'],
    [
      "? 'Tente ajustar sua busca ou limpar os filtros.'",
      "? t('conversations.emptySearch')",
    ],
    [
      ": 'Inicie um novo bate-papo para ver suas conversas aqui.'",
      ": t('conversations.emptyHint')",
    ],
  ]
  for (const [a, b] of pairs) {
    if (s.includes(a)) s = s.split(a).join(b)
    else console.log('Conversations MISS', a.slice(0, 70))
  }

  s = s.replace(
    /window\.confirm\(`Tem certeza que deseja apagar \$\{selectedIds\.length\} conversa\(s\)\? Esta ação é irreversível\.`\)/,
    "window.confirm(t('conversations.bulkDeleteConfirm', { count: selectedIds.length }))"
  )
  s = s.replace(
    /\{selectedIds\.length\} selecionado\(s\)/,
    "{t('conversations.selected', { count: selectedIds.length })}"
  )
  s = s.replace(
    /title=\{`Filtrar por: \$\{filter === 'all' \? 'Todos' : 'Favoritos'\}`\}/,
    "title={t('conversations.filterBy', { filter: filter === 'all' ? t('conversations.all') : t('conversations.favorites') })}"
  )

  s = s.replace(
    /const getRelativeTime = \(dateString: string\) => \{[\s\S]*?return d\.toLocaleDateString\('pt-BR', \{ day: 'numeric', month: 'short' \}\)\n\s*\}/,
    `const getRelativeTime = (dateString: string) => {
    const d = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 60) {
      return diffMins <= 1 ? t('time.justNow') : t('time.minutesAgo', { count: diffMins })
    } else if (diffHours < 24) {
      return t(diffHours === 1 ? 'time.hoursAgo_one' : 'time.hoursAgo_other', { count: diffHours })
    } else if (diffDays === 1) {
      return t('time.yesterday')
    } else if (diffDays < 7) {
      return t('time.daysAgo', { count: diffDays })
    } else {
      return d.toLocaleDateString(i18n.language, { day: 'numeric', month: 'short' })
    }
  }`
  )

  // Favorite/Desfavoritar in context menus if present
  s = s.replace(/\{menuState\.isFavorite \? 'Desfavoritar' : 'Favoritar'\}/g, "{menuState.isFavorite ? t('sidebar.unfavorite') : t('sidebar.favorite')}")
  s = s.replace(/>Desfavoritar</g, ">{t('sidebar.unfavorite')}<")
  s = s.replace(/>Favoritar</g, ">{t('sidebar.favorite')}<")
  s = s.replace(/>Mudar o nome</g, ">{t('sidebar.rename')}<")
  s = s.replace(/>Apagar</g, ">{t('sidebar.delete')}<")
  s = s.replace(/>Cancelar</g, ">{t('common.cancel')}<")

  fs.writeFileSync(path, s)
  console.log('ConversationsPanel OK')
}

function wireArtifacts() {
  const path = 'src/components/ArtifactsPanel.tsx'
  let s = fs.readFileSync(path, 'utf8')
  if (!s.includes('useTranslation')) {
    s = s.replace(
      "import { useStore } from '../store/useStore'",
      "import { useTranslation } from 'react-i18next'\nimport { useStore } from '../store/useStore'"
    )
    s = s.replace(
      'export function ArtifactsPanel() {\n  const {',
      'export function ArtifactsPanel() {\n  const { t, i18n } = useTranslation()\n  const {'
    )
  }

  const pairs = [
    ['title="Abrir menu"', 'title={t("common.openMenu")}'],
    ['aria-label="Abrir menu"', 'aria-label={t("common.openMenu")}'],
    ['placeholder="Pesquisar artefatos..."', "placeholder={t('artifacts.searchPlaceholder')}"],
    ['>Artefatos</h1>', '>{t("artifacts.title")}</h1>'],
    ['>Novo artefato</span>', '>{t("artifacts.newArtifact")}</span>'],
    ['>Nenhum artefato encontrado</h3>', '>{t("artifacts.emptyTitle")}</h3>'],
    ["? 'Tente ajustar sua busca para encontrar o artefato.'", "? t('artifacts.emptySearch')"],
    [
      ": 'Os artefatos que você gerar nas conversas com IA aparecerão aqui.'",
      ": t('artifacts.emptyHint')",
    ],
    [
      "window.confirm('Deseja iniciar um novo chat com o assistente local para criar novos artefatos?')",
      "window.confirm(t('artifacts.newChatConfirm'))",
    ],
    [
      'title={`${art.view_count} visualizações`}',
      "title={t('common.views', { count: art.view_count })}",
    ],
    ['title={`Versão ${art.version}`}', "title={t('common.version', { version: art.version })}"],
    [
      '<span>Editado {getRelativeTime(art.created_at)}</span>',
      "<span>{t('artifacts.edited', { time: getRelativeTime(art.created_at) })}</span>",
    ],
  ]
  for (const [a, b] of pairs) {
    if (s.includes(a)) s = s.split(a).join(b)
    else console.log('Artifacts MISS', a.slice(0, 70))
  }

  // visibility label
  s = s.replace(
    "{art.visibility || 'Privado'}",
    "{art.visibility === 'Publicado' ? t('artifacts.published') : t('artifacts.private')}"
  )

  s = s.replace(
    /const getRelativeTime = \(dateString: string\) => \{[\s\S]*?return d\.toLocaleDateString\('pt-BR', \{ day: 'numeric', month: 'short' \}\)\n\s*\}/,
    `const getRelativeTime = (dateString: string) => {
    const d = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 60) {
      return diffMins <= 1 ? t('time.justNow') : t('time.minutesAgo', { count: diffMins })
    } else if (diffHours < 24) {
      return t(diffHours === 1 ? 'time.hoursAgo_one' : 'time.hoursAgo_other', { count: diffHours })
    } else if (diffDays === 1) {
      return t('time.yesterday')
    } else if (diffDays < 7) {
      return t('time.daysAgo', { count: diffDays })
    } else {
      return d.toLocaleDateString(i18n.language, { day: 'numeric', month: 'short' })
    }
  }`
  )

  fs.writeFileSync(path, s)
  console.log('ArtifactsPanel OK')
}

wireConversations()
wireArtifacts()
