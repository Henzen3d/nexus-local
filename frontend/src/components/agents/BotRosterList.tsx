/**
 * BotRosterList.tsx — Lista e Seleção do Roster de Bots Especialistas (F8.3.2)
 */
import React from 'react'
import { Plus, Bot, Radio, Shield, Check, Trash2 } from 'lucide-react'
import { PetAvatar } from '../mascot/PetAvatar'
import type { ProactiveBot, MascotId } from '../../types'

interface BotRosterListProps {
  bots: ProactiveBot[]
  selectedBotId: string | null
  onSelectBot: (bot: ProactiveBot) => void
  onOpenCreateModal: () => void
  onDeleteBot?: (botId: string) => void
}

export const BotRosterList: React.FC<BotRosterListProps> = ({
  bots,
  selectedBotId,
  onSelectBot,
  onOpenCreateModal,
  onDeleteBot,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        borderRight: '1px solid var(--hairline)',
        background: 'var(--surface)',
      }}
    >
      {/* Header do Roster */}
      <div
        style={{
          padding: '1rem',
          borderBottom: '1px solid var(--hairline)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600 }}>
            Especialistas ({bots.length})
          </h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
            Bots com sandbox e escuta ativa
          </span>
        </div>
        <button
          type="button"
          onClick={onOpenCreateModal}
          className="settings-primary-btn"
          style={{
            padding: '6px 10px',
            fontSize: '0.78rem',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
          title="Criar novo bot especialista"
        >
          <Plus size={14} />
          <span>Novo</span>
        </button>
      </div>

      {/* Lista de Bots */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '0.75rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
        }}
      >
        {bots.map((bot) => {
          const isSelected = selectedBotId === bot.id
          return (
            <div
              key={bot.id}
              onClick={() => onSelectBot(bot)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '0.65rem 0.75rem',
                borderRadius: 10,
                border: isSelected ? `2px solid ${bot.color_hex}` : '1px solid var(--hairline)',
                background: isSelected ? 'var(--surface-soft)' : 'transparent',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                position: 'relative',
              }}
            >
              {/* Avatar do Bot */}
              <div
                style={{
                  width: 42,
                  height: 42,
                  borderRadius: 10,
                  backgroundColor: `${bot.color_hex}20`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  overflow: 'hidden',
                }}
              >
                {bot.mascot_id ? (
                  <PetAvatar
                    mascotId={bot.mascot_id as MascotId}
                    size={38}
                    state="idle"
                    trackPointer={false}
                  />
                ) : (
                  <Bot size={22} color={bot.color_hex} />
                )}
              </div>

              {/* Informações */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span
                    style={{
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      color: 'var(--ink)',
                    }}
                  >
                    {bot.name}
                  </span>
                  {isSelected && (
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        backgroundColor: bot.color_hex,
                      }}
                    />
                  )}
                </div>
                <div
                  style={{
                    fontSize: '0.75rem',
                    color: 'var(--ink-muted)',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {bot.title || bot.description || 'Especialista Nexus'}
                </div>

                {/* Badges de Recurso */}
                <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                  {bot.ambient_enabled && (
                    <span
                      style={{
                        fontSize: '0.65rem',
                        padding: '1px 5px',
                        borderRadius: 4,
                        background: 'rgba(16, 185, 129, 0.15)',
                        color: '#10B981',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 3,
                      }}
                      title="Escuta ativa em conversas"
                    >
                      <Radio size={9} />
                      Ouvindo
                    </span>
                  )}
                  {bot.computer_mode === 'sandbox' && (
                    <span
                      style={{
                        fontSize: '0.65rem',
                        padding: '1px 5px',
                        borderRadius: 4,
                        background: 'rgba(59, 130, 246, 0.15)',
                        color: '#3B82F6',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 3,
                      }}
                      title="Container isolado nexus_computer"
                    >
                      <Shield size={9} />
                      Sandbox
                    </span>
                  )}
                </div>
              </div>

              {/* Ação de Excluir */}
              {onDeleteBot && !bot.id.startsWith('tpl-') && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    if (window.confirm(`Deseja excluir o bot "${bot.name}"?`)) {
                      onDeleteBot(bot.id)
                    }
                  }}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--ink-muted)',
                    cursor: 'pointer',
                    padding: 4,
                    opacity: 0.6,
                  }}
                  title="Excluir bot"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
