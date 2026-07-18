import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { PanelLeftOpen, Code2, BookOpen, Pencil, Lightbulb, Dna, X, ChevronRight, MoreVertical, Folder } from 'lucide-react'
import { BuyCoffeeIcon } from './BuyCoffeeIcon'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { MessageBubble, StreamingBubble } from './MessageBubble'
import { MessageInput } from './MessageInput'
import { ProviderSelector } from './ProviderSelector'
import { FusionStatusCard } from './FusionStatusCard'
import { useChatContext } from '../context/ChatContext'
import { Button } from './ui/Button'
import { BottomSheet } from './ui/BottomSheet'
import { useIsMobile } from '../hooks/useIsMobile'
import { NexusLogoIcon } from './NexusLogoIcon'

import { SUPPORT_URL } from '../config/support'

// Saudações dinâmicas via i18n
function getRandomGreeting(name: string, t: (key: string, opts?: Record<string, unknown>) => string): string {
  const hour = new Date().getHours()
  const timeKey =
    hour >= 5 && hour < 12
      ? 'chat.greetingMorning'
      : hour >= 12 && hour < 18
        ? 'chat.greetingAfternoon'
        : 'chat.greetingEvening'
  const timeBased = t(timeKey)

  const greetings = [
    t('chat.greetingTimeName', { time: timeBased, name, defaultValue: `${timeBased}, ${name}.` }),
    t('chat.greetingWelcomeBack', { name, defaultValue: `Welcome back, ${name}!` }),
    t('chat.greetingGoodToSee', { name, defaultValue: `Good to see you, ${name}.` }),
    t('chat.greetingHelloHelp', { name, defaultValue: `Hi ${name}! How can I help?` }),
    t('chat.greetingReady', { name, defaultValue: `All set? Let's go, ${name}!` }),
    t('chat.greetingThinking', { name, defaultValue: `What are you thinking about today, ${name}?` }),
    t('chat.greetingExplore', { name, defaultValue: `Ready to explore new ideas, ${name}?` }),
  ]

  return greetings[Math.floor(Math.random() * greetings.length)]
}

type ChipKey = 'write' | 'learn' | 'code' | 'brainstorm'

interface SuggestionItem {
  display: string
  fullPrompt: string
}

interface ChipItem {
  key: ChipKey
  label: string
  Icon: React.ElementType
}

interface KeywordTailor {
  regex: RegExp
  category: ChipKey
  display: string
  fullPrompt: string
}

// Sugestões Elaboradas Estáticas
const SUGGESTIONS_WRITE: SuggestionItem[] = [
  {
    display: 'Escrever propostas de financiamento',
    fullPrompt: 'Gostaria que você me ajudasse a redigir uma proposta de financiamento clara, detalhada e persuasiva para um projeto. O documento deve incluir uma introdução atraente, a descrição do problema, a solução proposta, a estimativa de custos/benefícios e um fechamento formal. Use um tom profissional de negócios.',
  },
  {
    display: 'Compare meu estilo de escrita com autores famosos',
    fullPrompt: 'Gostaria de analisar um trecho do meu texto e compará-lo com o estilo de escrita de autores consagrados. Indique quais semelhanças e diferenças você percebe em termos de vocabulário, ritmo, estrutura de frases e tom, e sugira caminhos para eu polir meu estilo pessoal.',
  },
  {
    display: 'Escrever descrições de eventos',
    fullPrompt: 'Me ajude a criar uma descrição curta, engajadora e focada em conversão para um evento profissional. O texto deve incluir o objetivo do evento, quem deve participar, os principais benefícios e uma chamada para ação (CTA) irresistível. Mantenha um tom dinâmico e convidativo.',
  },
  {
    display: 'Desenvolver modelos de conteúdo',
    fullPrompt: 'Crie um template estruturado e reutilizável para a criação de conteúdo regular (como posts de blog, newsletters ou atualizações semanais). O modelo deve conter cabeçalho, corpo estruturado por tópicos e seção de call-to-action para otimizar meu tempo de escrita.',
  },
  {
    display: 'Desenvolver conteúdo instrucional',
    fullPrompt: 'Gostaria de estruturar um guia passo a passo instrucional focado em ensinar um conceito prático para iniciantes. Divida o conteúdo em objetivos de aprendizagem, introdução conceitual, passos práticos detalhados, erros comuns a evitar e um exercício rápido de fixação.',
  },
]

const SUGGESTIONS_LEARN: SuggestionItem[] = [
  {
    display: 'Desenvolver objetivos de aprendizagem',
    fullPrompt: 'Gostaria de traçar um plano de estudos estruturado para dominar uma nova habilidade ou tecnologia do zero. Por favor, crie uma trilha dividida em semanas ou módulos, indicando conceitos-chave, exercícios recomendados e critérios claros para eu avaliar se de fato dominei cada etapa.',
  },
  {
    display: 'Criar currículo com estética cultural',
    fullPrompt: 'Crie uma trilha de estudos ou currículo acadêmico com base estética, filosófica e metodológica inspirada em um movimento cultural ou artístico marcante. Explique como os valores desse movimento se aplicam às matérias e formas de aprendizado.',
  },
  {
    display: 'Criar boas anotações de aula',
    fullPrompt: 'Forneça um modelo e um método eficiente para fazer anotações de alto impacto durante palestras, aulas ou reuniões (como o Método Cornell). Explique como estruturar palavras-chave, resumos rápidos e ações futuras de forma prática.',
  },
  {
    display: 'Encontrar os melhores livros sobre um assunto',
    fullPrompt: 'Gostaria de receber uma curadoria refinada de livros essenciais sobre uma determinada área do conhecimento. Para cada indicação, descreva o foco principal da obra, por que ela é considerada referência e qual o principal aprendizado prático que o leitor extrai dela.',
  },
  {
    display: 'Encontre padrões em minha pesquisa',
    fullPrompt: 'Ajude-me a analisar dados brutos ou anotações de uma pesquisa de campo para identificar tendências comuns, dores dos usuários, padrões recorrentes e ideias-chave que possam ser transformadas em insights acionáveis de produto.',
  },
]

const SUGGESTIONS_CODE: SuggestionItem[] = [
  {
    display: 'Desenvolver soluções algorítmicas',
    fullPrompt: 'Crie uma solução algorítmica otimizada para resolver um desafio lógico comum em programação. Explique detalhadamente o raciocínio por trás da escolha da estrutura de dados, analise a complexidade de tempo e espaço (Big O) e apresente o código comentado.',
  },
  {
    display: 'Me desafie com quebra-cabeças de programação',
    fullPrompt: 'Apresente-me um desafio ou quebra-cabeça de lógica de programação de nível intermediário para que eu possa resolver. Inclua o enunciado do problema, exemplos de entrada e saída esperados, e dicas sutis para me guiar sem revelar a resposta imediatamente.',
  },
  {
    display: 'Depure meu código e me dê dicas',
    fullPrompt: 'Aja como um revisor de código experiente. Gostaria de enviar um trecho de código com bugs ou problemas de performance para que você analise, aponte os erros lógicos, sugira correções de segurança e refatore o código seguindo as melhores práticas da linguagem.',
  },
  {
    display: 'Jogo para ensinar conceitos de código',
    fullPrompt: 'Estruture a lógica e o código-fonte de um jogo de texto ou jogo web super simples focado em ensinar conceitos fundamentais de desenvolvimento (como loops, condicionais ou escopo) de forma interativa e divertida para iniciantes.',
  },
  {
    display: 'Criar trechos de código úteis',
    fullPrompt: 'Crie um trecho de código (boilerplate) extremamente limpo, moderno e modular para resolver uma necessidade técnica comum em projetos web, usando boas práticas de tipagem, tratamento de erros robusto e exportações organizadas.',
  },
]

const SUGGESTIONS_BRAINSTORM: SuggestionItem[] = [
  {
    display: 'Monetizar minhas habilidades digitais',
    fullPrompt: 'Gostaria de fazer um brainstorm estruturado de ideias práticas para monetizar minhas habilidades técnicas ou criativas na internet. Sugira modelos de negócios viáveis, canais de distribuição recomendados e um plano simplificado para lançar o primeiro produto viável (MVP).',
  },
  {
    display: 'Melhorar produtividade de equipe remota',
    fullPrompt: 'Gostaria de coletar ideias inovadoras e metodologias ágeis para aumentar o engajamento e a produtividade de uma equipe de desenvolvimento remoto. Foque em rituais de comunicação eficientes, ferramentas de colaboração e formas de evitar o esgotamento profissional.',
  },
  {
    display: 'Ideias de automação local com IA',
    fullPrompt: 'Me ajude a fazer um brainstorm de projetos práticos de automação e inteligência artificial que eu possa construir localmente. Sugira ideias focadas em otimização de tempo, organização de arquivos ou processamento automático de dados.',
  },
  {
    display: 'Estratégias de marketing digital para negócios',
    fullPrompt: 'Proponha ideias criativas e estratégias de marketing digital para promover e vender produtos físicos ou serviços de maneira inovadora, destacando canais de tráfego orgânico, produção de conteúdo envolvente e funis de venda diretos.',
  },
  {
    display: 'Calendário de ideias de conteúdo inovador',
    fullPrompt: 'Gostaria de criar um calendário editorial de ideias de conteúdo inovadoras e de alto engajamento para minhas redes. As sugestões devem focar em contar histórias reais, ensinar conceitos rápidos e incentivar a interação dos seguidores.',
  },
]

// Mapeamento de Palavras-Chave para Injetar Sugestões Contextuais Personalizadas
const TAILORED_SUGGESTIONS: KeywordTailor[] = [
  {
    regex: /react|typescript|frontend|front|vite|desenvolver/i,
    category: 'code',
    display: '✨ Arquitetura limpa e performance em React',
    fullPrompt: 'Elabore um guia completo sobre boas práticas de arquitetura, estruturação de componentes reutilizáveis, gerenciamento de estado global/local e otimização de performance para aplicações modernas de frontend com React e TypeScript.',
  },
  {
    regex: /python|django|fastapi|backend|back|csv|pandas/i,
    category: 'code',
    display: '✨ Processamento assíncrono de dados em Python',
    fullPrompt: 'Crie um guia técnico contendo estratégias para ler, processar e estruturar grandes volumes de dados (como arquivos CSV/JSON) de forma altamente eficiente e assíncrona usando Python e boas práticas de concorrência.',
  },
  {
    regex: /fix|serviço|servico/i,
    category: 'write',
    display: '✨ Modelo de e-mail comercial para Fix Serviços',
    fullPrompt: 'Redija um e-mail de prospecção comercial altamente profissional, breve e convincente focado em oferecer os serviços de excelência da Fix Serviços para empresas parceiras, destacando nossa agilidade, qualidade e valor agregado.',
  },
  {
    regex: /aumento|salário|promocao|promoção|carreira/i,
    category: 'write',
    display: '✨ Pitch estratégico de promoção e progresso de carreira',
    fullPrompt: 'Estruture um plano estratégico estruturado com metas tangíveis e competências que eu possa apresentar à minha liderança para demonstrar meu crescimento profissional recente e embasar um pedido de promoção ou aumento salarial.',
  },
  {
    regex: /mcp|protocol|anthropic|server/i,
    category: 'learn',
    display: '✨ Integração avançada de servidores customizados MCP',
    fullPrompt: 'Explique em detalhes como construir um servidor local customizado baseado no Model Context Protocol (MCP) da Anthropic, conectando APIs locais ou bancos de dados para estender os recursos do assistente de IA.',
  },
]

// Analisador de Histórico de Conversas para Categorias e Sugestões Dinâmicas
function getScoresAndTailored(conversations: any[]) {
  let code = 0
  let write = 0
  let learn = 0
  let brainstorm = 0
  const matchedTailored: KeywordTailor[] = []

  const codeKw = /react|typescript|frontend|front|vite|python|django|fastapi|backend|back|csv|pandas|code|código|api|git|docker|html|css|js/i
  const writeKw = /escrever|email|e-mail|texto|carta|bio|linkedin|apresentação|redigir|contrato|fix|serviço|servico|aumento|salário|promocao|promoção/i
  const learnKw = /aprender|explique|como funciona|o que é|ensine|livros|conceito|história|mcp|protocol|anthropic|server/i
  const brainstormKw = /ideias|brainstorm|criar|criativo|monetizar|dicas|sugestões/i

  // Analisa as últimas 15 conversas para capturar padrões de interesse
  conversations.slice(0, 15).forEach((c) => {
    const title = c.title || ''
    if (codeKw.test(title)) code++
    if (writeKw.test(title)) write++
    if (learnKw.test(title)) learn++
    if (brainstormKw.test(title)) brainstorm++

    // Captura palavras-chave específicas e mapeia sugestões personalizadas
    TAILORED_SUGGESTIONS.forEach((ts) => {
      if (ts.regex.test(title) && !matchedTailored.some(m => m.display === ts.display)) {
        matchedTailored.push(ts)
      }
    })
  })

  return {
    scores: { code, write, learn, brainstorm },
    matchedTailored,
  }
}

export function ChatWindow() {
  const { t } = useTranslation()
  const {
    messages,
    conversations,
    streamingContent,
    isStreaming,
    sidebarOpen,
    setSidebarOpen,
    fusionMode,
    setFusionMode,
    fusionActive,
    displayName,
    activeConversationId,
    activeConversation,
    activeProjectId,
    projectNameById,
    setProjectName,
    setView,
    setActiveProjectId,
  } = useStore()
  const { sendMessage } = useChatContext()
  const isMobile = useIsMobile()
  const messagesAreaRef = useRef<HTMLDivElement>(null)
  const bottomSentinelRef = useRef<HTMLDivElement>(null)
  const prevMessagesLength = useRef(messages.length)
  const headerMenuRef = useRef<HTMLDivElement>(null)

  const name = displayName || t('common.user')

  // Saudação aleatória — gerada uma única vez por sessão (ao montar o componente)
  const [greeting] = useState(() => getRandomGreeting(name, t))

  // Estado do chip de sugestões aberto
  const [openChip, setOpenChip] = useState<ChipKey | null>(null)
  const [headerMenuOpen, setHeaderMenuOpen] = useState(false)

  // Project relationship for the open chat (Claude-style breadcrumb)
  const chatProjectId =
    activeConversation?.project_id ||
    conversations.find((c) => c.id === activeConversationId)?.project_id ||
    activeProjectId ||
    null
  const chatTitle =
    activeConversation?.title ||
    conversations.find((c) => c.id === activeConversationId)?.title ||
    ''
  const projectLabel = chatProjectId ? projectNameById[chatProjectId] : undefined

  useEffect(() => {
    if (!chatProjectId || projectNameById[chatProjectId]) return
    let cancelled = false
    ;(async () => {
      try {
        const p = await api.getProject(chatProjectId)
        if (!cancelled) setProjectName(p.id, p.name)
      } catch {
        /* project may have been deleted */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [chatProjectId, projectNameById, setProjectName])

  useEffect(() => {
    if (!headerMenuOpen) return
    const handler = (e: MouseEvent) => {
      if (headerMenuRef.current && !headerMenuRef.current.contains(e.target as Node)) {
        setHeaderMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [headerMenuOpen])

  // Project detail composer → open chat view and send first message
  useEffect(() => {
    const handler = (e: Event) => {
      const text = (e as CustomEvent<{ text?: string }>).detail?.text
      if (text?.trim()) sendMessage(text.trim())
    }
    window.addEventListener('nexus:send-project-message', handler)
    return () => window.removeEventListener('nexus:send-project-message', handler)
  }, [sendMessage])

  // Analisa o histórico dinamicamente para obter a relevância das categorias
  const { scores, matchedTailored } = useMemo(() => {
    return getScoresAndTailored(conversations)
  }, [conversations])

  // Ordena os botões de chips baseado no score de interesse histórico
  const orderedChips = useMemo(() => {
    const baseChips: ChipItem[] = [
      { key: 'write', label: t('chat.chipWrite'), Icon: Pencil },
      { key: 'learn', label: t('chat.chipLearn'), Icon: BookOpen },
      { key: 'code', label: t('chat.chipCode'), Icon: Code2 },
      { key: 'brainstorm', label: t('chat.chipBrainstorm'), Icon: Lightbulb },
    ]

    return baseChips.sort((a, b) => {
      const scoreA = scores[a.key] || 0
      const scoreB = scores[b.key] || 0
      return scoreB - scoreA
    })
  }, [scores, t])

  // Retorna a lista combinada de sugestões (estáticas + dinâmicas customizadas no topo)
  const activeSuggestions = useMemo(() => {
    if (!openChip) return []

    let base: SuggestionItem[] = []
    if (openChip === 'write') base = [...SUGGESTIONS_WRITE]
    else if (openChip === 'learn') base = [...SUGGESTIONS_LEARN]
    else if (openChip === 'code') base = [...SUGGESTIONS_CODE]
    else if (openChip === 'brainstorm') base = [...SUGGESTIONS_BRAINSTORM]

    // Filtra sugestões adaptativas geradas a partir do histórico correspondentes a esta categoria
    const custom = matchedTailored
      .filter(m => m.category === openChip)
      .map(m => ({ display: m.display, fullPrompt: m.fullPrompt }))

    // Agrupa (priorizando personalizadas no topo) e remove possíveis duplicados
    const merged = [...custom, ...base]
    const seen = new Set<string>()
    return merged.filter((item) => {
      if (seen.has(item.display)) return false
      seen.add(item.display)
      return true
    }).slice(0, 5)
  }, [openChip, matchedTailored])

  const activeChipIcon = useMemo(() => {
    if (!openChip) return null
    if (openChip === 'write') return Pencil
    if (openChip === 'learn') return BookOpen
    if (openChip === 'code') return Code2
    return Lightbulb
  }, [openChip])

  const activeChipLabel = useMemo(() => {
    if (!openChip) return ''
    if (openChip === 'write') return t('chat.chipWrite')
    if (openChip === 'learn') return t('chat.chipLearn')
    if (openChip === 'code') return t('chat.chipCode')
    return t('chat.chipBrainstorm')
  }, [openChip, t])

  useEffect(() => {
    const container = messagesAreaRef.current
    if (!container) return

    const messageCountChanged = messages.length !== prevMessagesLength.current
    prevMessagesLength.current = messages.length

    if (messageCountChanged) {
      container.scrollTop = container.scrollHeight
      return
    }

    const threshold = 180
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold

    if (isNearBottom && bottomSentinelRef.current) {
      bottomSentinelRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [messages, streamingContent])

  // Fecha submenu ao clicar fora
  const handleOverlayClick = useCallback(() => setOpenChip(null), [])

  const isEmpty = messages.length === 0 && !isStreaming

  const handleSuggestion = (fullPrompt: string) => {
    setOpenChip(null)
    sendMessage(fullPrompt)
  }

  return (
    <main className={`chat-window ${isEmpty ? 'is-empty' : ''}`}>
      <header className="chat-header">
        {/* Esquerda: menu + seletor de modelo (padrão dos chats online) */}
        <div className="chat-header-left">
          {/* Desktop: rail de ícones na sidebar; mobile: botão no header */}
          {!sidebarOpen && isMobile && (
            <Button
              variant="ghost"
              size="icon"
              className="touch-target"
              onClick={() => setSidebarOpen(true)}
              tooltip={t('chat.openSidebar')}
              aria-label={t('chat.openSidebar')}
            >
              <PanelLeftOpen size={18} />
            </Button>
          )}
          <ProviderSelector />

          {/* Fusion ao lado do seletor de provedores */}
          <Button
            variant={fusionMode ? 'primary' : 'secondary'}
            size="icon"
            className={`fusion-header-btn ${fusionMode ? 'is-active' : ''}`}
            onClick={() => setFusionMode(!fusionMode)}
            disabled={fusionActive}
            tooltip={fusionMode ? t('chat.deactivateFusion') : t('chat.activateFusion')}
            aria-label={fusionMode ? t('chat.deactivateFusion') : t('chat.activateFusion')}
            aria-pressed={fusionMode}
          >
            <Dna size={15} strokeWidth={2} />
          </Button>

          {/* Breadcrumb de projeto ao lado do seletor (Claude: Projeto / Título) */}
          {chatProjectId && !isEmpty && (
            <nav className="chat-project-breadcrumb" aria-label={t('projects.breadcrumb', { defaultValue: 'Projeto' })}>
              <button
                type="button"
                className="chat-project-crumb custom-tooltip-trigger"
                onClick={() => {
                  setActiveProjectId(chatProjectId)
                  setView('projects')
                  try {
                    const url = new URL(window.location.href)
                    url.searchParams.set('project', chatProjectId)
                    window.history.replaceState({}, '', url.toString())
                  } catch {
                    /* ignore */
                  }
                }}
                data-tooltip={t('projects.openProject', { defaultValue: 'Abrir projeto' })}
              >
                <Folder size={14} strokeWidth={1.8} />
                <span className="chat-project-crumb-name">
                  {projectLabel || t('sidebar.projects', { defaultValue: 'Projeto' })}
                </span>
              </button>
              {chatTitle && (
                <>
                  <span className="chat-project-sep" aria-hidden>
                    /
                  </span>
                  <span className="chat-project-chat-title" title={chatTitle}>
                    {chatTitle}
                  </span>
                </>
              )}
            </nav>
          )}
        </div>

        {/* Tela inicial: Apoiar centralizado no header */}
        {isEmpty && !isMobile && (
          <a
            href={SUPPORT_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="support-btn support-btn--home"
          >
            <BuyCoffeeIcon size={20} className="support-btn-icon" />
            <span>{t('chat.supportNexus', { defaultValue: 'Apoiar o NexusLocal' })}</span>
          </a>
        )}

        <div className="chat-header-spacer" />

        {/* Direita: ações secundárias */}
        <div className="chat-header-right">
          {/* Chat ativo: Apoiar na lateral direita */}
          {!isEmpty && !isMobile && (
            <a
              href={SUPPORT_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="support-btn support-btn--chat"
            >
              <BuyCoffeeIcon size={20} className="support-btn-icon" />
              <span>{t('chat.supportNexus', { defaultValue: 'Apoiar o NexusLocal' })}</span>
            </a>
          )}

          {isMobile && (
            <div className="chat-header-overflow" ref={headerMenuRef}>
              <Button
                variant="ghost"
                size="icon"
                className="touch-target"
                onClick={() => setHeaderMenuOpen((o) => !o)}
                aria-label={t('chat.moreOptions', { defaultValue: 'Mais opções' })}
                aria-expanded={headerMenuOpen}
              >
                <MoreVertical size={18} />
              </Button>
              {headerMenuOpen && (
                <div className="chat-header-menu" role="menu">
                  {chatProjectId && (
                    <button
                      type="button"
                      className="chat-header-menu-item"
                      role="menuitem"
                      onClick={() => {
                        setHeaderMenuOpen(false)
                        setActiveProjectId(chatProjectId)
                        setView('projects')
                        try {
                          const url = new URL(window.location.href)
                          url.searchParams.set('project', chatProjectId)
                          window.history.replaceState({}, '', url.toString())
                        } catch {
                          /* ignore */
                        }
                      }}
                    >
                      <Folder size={15} />
                      <span>
                        {t('sidebar.viewProject', { defaultValue: 'Ver projeto' })}
                        {projectLabel ? `: ${projectLabel}` : ''}
                      </span>
                    </button>
                  )}
                  <a
                    href={SUPPORT_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="chat-header-menu-item support-menu-item"
                    role="menuitem"
                    onClick={() => setHeaderMenuOpen(false)}
                  >
                    <BuyCoffeeIcon size={20} className="support-btn-icon" />
                    <span>{t('chat.supportNexus', { defaultValue: 'Apoiar o NexusLocal' })}</span>
                  </a>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      <div className="layout-spacer top">
        {isEmpty && (
          <div className="welcome">
            <div className="welcome-brand">
              <NexusLogoIcon className="welcome-mark-img" />
              <h1 className="welcome-greeting">
                {greeting}
              </h1>
            </div>

            <p className="welcome-sub">
              {t('chat.welcomeSub')}
            </p>
          </div>
        )}
      </div>

      <div className="messages-area" ref={messagesAreaRef}>
        {!isEmpty && (
          <>
            {messages.map((m) => {
              if (m.role === 'fusion_status') {
                return (
                  <FusionStatusCard
                    key={m.id}
                    fusionStatuses={m.fusion_statuses || []}
                    fusionJudgeModelId={m.fusion_judge_model_id || null}
                    fusionGrounding={m.fusion_grounding || null}
                    fusionRefinedPrompt={m.fusion_refined_prompt || null}
                  />
                )
              }
              return <MessageBubble key={m.id} message={m} />
            })}
            {isStreaming && <StreamingBubble content={streamingContent} />}
          </>
        )}
        <div ref={bottomSentinelRef} style={{ height: 0, flexShrink: 0 }} aria-hidden="true" />
      </div>

      <MessageInput onSend={sendMessage} isEmpty={isEmpty} />

      {/* Chips de sugestão — empty state */}
      {isEmpty && (
        <div className="welcome-chips-bar">
          {!isMobile && openChip && (
            <div className="chip-overlay" onClick={handleOverlayClick} />
          )}

          <div
            className="welcome-chips-row"
            style={
              !isMobile && openChip
                ? {
                    opacity: 0,
                    pointerEvents: 'none',
                    visibility: 'hidden',
                  }
                : undefined
            }
            aria-hidden={!isMobile && !!openChip}
          >
            {orderedChips.map((chip) => (
              <button
                key={chip.key}
                type="button"
                className={`welcome-chip-btn ${openChip === chip.key ? 'active' : ''}`}
                onClick={() => setOpenChip((prev) => (prev === chip.key ? null : chip.key))}
              >
                <chip.Icon size={18} strokeWidth={1.75} />
                {chip.label}
              </button>
            ))}
          </div>

          {/* Desktop floating submenu */}
          {!isMobile && openChip && (() => {
            const IconComponent = activeChipIcon
            return (
              <div className="chip-submenu-full">
                <div
                  className="chip-submenu-header"
                  role="button"
                  tabIndex={0}
                  onClick={() => setOpenChip(null)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      setOpenChip(null)
                    }
                  }}
                  aria-label={t('common.close')}
                >
                  {IconComponent && <IconComponent size={14} />}
                  <span>{activeChipLabel}</span>
                  <button
                    type="button"
                    className="chip-submenu-close custom-tooltip-trigger"
                    onClick={(e) => {
                      e.stopPropagation()
                      setOpenChip(null)
                    }}
                    data-tooltip={t('common.close')}
                    aria-label={t('common.close')}
                  >
                    <X size={16} />
                  </button>
                </div>
                <div className="chip-submenu-list">
                  {activeSuggestions.map((sug, i) => (
                    <button
                      key={i}
                      type="button"
                      className="chip-submenu-item"
                      onClick={() => handleSuggestion(sug.fullPrompt)}
                    >
                      <span>{sug.display}</span>
                      <ChevronRight size={14} className="chip-submenu-arrow" />
                    </button>
                  ))}
                </div>
              </div>
            )
          })()}
        </div>
      )}

      {/* Mobile: chip suggestions as bottom sheet */}
      <BottomSheet
        open={isMobile && isEmpty && !!openChip}
        onClose={() => setOpenChip(null)}
        title={activeChipLabel}
      >
        <div className="nl-sheet-list">
          {activeSuggestions.map((sug, i) => (
            <button
              key={i}
              type="button"
              className="nl-sheet-option"
              onClick={() => handleSuggestion(sug.fullPrompt)}
            >
              <div className="nl-sheet-option-body">
                <span className="nl-sheet-option-name">{sug.display}</span>
              </div>
              <ChevronRight size={16} className="nl-sheet-option-check" style={{ color: 'var(--muted-soft)' }} />
            </button>
          ))}
        </div>
      </BottomSheet>

      <div className="layout-spacer bottom" />
    </main>
  )
}
